"""Applause detector GUI for video files."""

from __future__ import annotations

import dataclasses
import json
import math
import pathlib
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly, stft


@dataclasses.dataclass
class Segment:
    start: float
    end: float
    score: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclasses.dataclass
class PreviewItem:
    segment: Segment
    thumbnail_path: pathlib.Path


def run_ffmpeg(args: list[str]) -> None:
    completed = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", *args],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )


def extract_audio_to_wav(video_path: pathlib.Path, wav_path: pathlib.Path) -> None:
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-ac",
            "1",
            "-ar",
            "22050",
            str(wav_path),
        ]
    )


def extract_thumbnail(
    video_path: pathlib.Path, output_path: pathlib.Path, timestamp: float
) -> None:
    run_ffmpeg(
        [
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-vf",
            "scale=320:-1",
            str(output_path),
        ]
    )


def export_segment(
    video_path: pathlib.Path, output_path: pathlib.Path, segment: Segment
) -> None:
    run_ffmpeg(
        [
            "-y",
            "-ss",
            f"{segment.start:.3f}",
            "-t",
            f"{segment.duration:.3f}",
            "-i",
            str(video_path),
            "-c",
            "copy",
            str(output_path),
        ]
    )


def load_audio(wav_path: pathlib.Path, target_rate: int = 22050) -> np.ndarray:
    sample_rate, data = wavfile.read(wav_path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32)
    if sample_rate != target_rate:
        data = resample_poly(data, target_rate, sample_rate)
    if np.max(np.abs(data)) > 0:
        data = data / np.max(np.abs(data))
    return data


def zscore(values: np.ndarray) -> np.ndarray:
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0:
        return np.zeros_like(values)
    return (values - mean) / std


def frames_to_segments(
    active: np.ndarray,
    times: np.ndarray,
    frame_duration: float,
    min_duration: float,
    min_gap: float,
) -> list[Segment]:
    segments: list[Segment] = []
    start_idx: int | None = None
    for idx, is_active in enumerate(active):
        if is_active and start_idx is None:
            start_idx = idx
        elif not is_active and start_idx is not None:
            segments.append((start_idx, idx - 1))
            start_idx = None
    if start_idx is not None:
        segments.append((start_idx, len(active) - 1))

    cleaned: list[Segment] = []
    for start_idx, end_idx in segments:
        start_time = max(0.0, times[start_idx] - frame_duration / 2)
        end_time = times[end_idx] + frame_duration / 2
        if end_time - start_time >= min_duration:
            cleaned.append(Segment(start=start_time, end=end_time, score=0.0))

    if not cleaned:
        return []

    merged: list[Segment] = [cleaned[0]]
    for segment in cleaned[1:]:
        previous = merged[-1]
        if segment.start - previous.end <= min_gap:
            merged[-1] = Segment(
                start=previous.start, end=segment.end, score=0.0
            )
        else:
            merged.append(segment)
    return merged


def detect_applause_segments(
    wav_path: pathlib.Path,
    min_duration: float = 0.3,
    min_gap: float = 0.2,
) -> list[Segment]:
    data = load_audio(wav_path)
    if data.size == 0:
        return []

    frame_size = 1024
    hop_length = 512
    _, times, spectrum = stft(
        data,
        fs=22050,
        nperseg=frame_size,
        noverlap=frame_size - hop_length,
    )
    magnitude = np.abs(spectrum)
    rms = np.sqrt(np.mean(magnitude**2, axis=0))
    flux = np.sum(np.maximum(0.0, np.diff(magnitude, axis=1)), axis=0)
    flux = np.concatenate([[0.0], flux])

    score = zscore(rms) + zscore(flux)
    threshold = float(np.median(score) + 1.5 * np.std(score))
    active = score > threshold

    frame_duration = frame_size / 22050.0
    segments = frames_to_segments(active, times, frame_duration, min_duration, min_gap)
    for segment in segments:
        segment.score = float(
            np.mean(score[(times >= segment.start) & (times <= segment.end)])
        )
    return segments


def build_previews(
    video_path: pathlib.Path, segments: list[Segment], temp_dir: pathlib.Path
) -> list[PreviewItem]:
    previews: list[PreviewItem] = []
    for idx, segment in enumerate(segments, start=1):
        thumbnail_path = temp_dir / f"thumb_{idx:02d}.png"
        extract_thumbnail(video_path, thumbnail_path, segment.start)
        previews.append(PreviewItem(segment=segment, thumbnail_path=thumbnail_path))
    return previews


def format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    remainder = seconds % 60
    return f"{minutes:02d}:{remainder:05.2f}"


class ScrollableFrame(ttk.Frame):
    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master)
        self.canvas = tk.Canvas(self, borderwidth=0, height=420)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.container = ttk.Frame(self.canvas)

        self.container.bind(
            "<Configure>",
            lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas.create_window((0, 0), window=self.container, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")


class ApplauseDetectorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Applause Detector")

        self.video_path: pathlib.Path | None = None
        self.temp_dir = tempfile.TemporaryDirectory()
        self.preview_images: list[tk.PhotoImage] = []
        self.preview_vars: list[tk.BooleanVar] = []
        self.preview_items: list[PreviewItem] = []

        self.status_var = tk.StringVar(value="Seleziona un file video per iniziare.")

        self._build_ui()

    def _build_ui(self) -> None:
        controls = ttk.Frame(self.root, padding=10)
        controls.pack(fill="x")

        ttk.Button(controls, text="Apri video", command=self.select_video).pack(
            side="left"
        )
        ttk.Button(
            controls, text="Analizza", command=self.analyze_video
        ).pack(side="left", padx=8)
        ttk.Button(
            controls, text="Esporta selezionati", command=self.export_selected
        ).pack(side="left")

        status = ttk.Label(self.root, textvariable=self.status_var, padding=10)
        status.pack(fill="x")

        self.preview_area = ScrollableFrame(self.root)
        self.preview_area.pack(fill="both", expand=True, padx=10, pady=10)

    def select_video(self) -> None:
        filename = filedialog.askopenfilename(
            title="Seleziona video",
            filetypes=[
                ("Video", "*.mp4 *.mov *.mkv *.avi"),
                ("Tutti i file", "*.*"),
            ],
        )
        if filename:
            self.video_path = pathlib.Path(filename)
            self.status_var.set(f"Video selezionato: {self.video_path.name}")

    def analyze_video(self) -> None:
        if not self.video_path:
            messagebox.showwarning("Attenzione", "Seleziona un file video prima.")
            return

        self.status_var.set("Estrazione audio in corso...")
        self.root.update_idletasks()

        temp_dir = pathlib.Path(self.temp_dir.name)
        wav_path = temp_dir / "audio.wav"

        try:
            extract_audio_to_wav(self.video_path, wav_path)
        except RuntimeError as error:
            messagebox.showerror("Errore", str(error))
            return

        self.status_var.set("Analisi applausi in corso...")
        self.root.update_idletasks()

        segments = detect_applause_segments(wav_path)
        if not segments:
            self.status_var.set("Nessun applauso rilevato.")
            self.clear_previews()
            return

        self.status_var.set(f"Trovati {len(segments)} segmenti di applausi.")
        self.preview_items = build_previews(self.video_path, segments, temp_dir)
        self.render_previews()

    def clear_previews(self) -> None:
        for widget in self.preview_area.container.winfo_children():
            widget.destroy()
        self.preview_images.clear()
        self.preview_vars.clear()
        self.preview_items.clear()

    def render_previews(self) -> None:
        self.clear_previews()
        for idx, preview in enumerate(self.preview_items, start=1):
            row = ttk.Frame(self.preview_area.container, padding=8)
            row.pack(fill="x", pady=4)

            image = tk.PhotoImage(file=str(preview.thumbnail_path))
            self.preview_images.append(image)
            image_label = ttk.Label(row, image=image)
            image_label.pack(side="left")

            info = ttk.Frame(row)
            info.pack(side="left", padx=10, fill="x", expand=True)

            segment = preview.segment
            ttk.Label(
                info,
                text=f"Applauso {idx}",
                font=("Helvetica", 12, "bold"),
            ).pack(anchor="w")
            ttk.Label(
                info,
                text=(
                    f"Inizio: {format_time(segment.start)} | "
                    f"Fine: {format_time(segment.end)} | "
                    f"Durata: {segment.duration:.2f}s"
                ),
            ).pack(anchor="w", pady=2)

            var = tk.BooleanVar(value=True)
            self.preview_vars.append(var)
            ttk.Checkbutton(row, text="Esporta", variable=var).pack(side="right")

    def export_selected(self) -> None:
        if not self.video_path or not self.preview_items:
            messagebox.showwarning(
                "Attenzione", "Nessun segmento disponibile per l'esportazione."
            )
            return

        output_dir = filedialog.askdirectory(title="Scegli cartella di output")
        if not output_dir:
            return
        output_dir_path = pathlib.Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        exported = 0
        errors: list[str] = []
        for idx, (preview, selected) in enumerate(
            zip(self.preview_items, self.preview_vars), start=1
        ):
            if not selected.get():
                continue
            output_path = output_dir_path / f"applause_{idx:02d}.mp4"
            try:
                export_segment(self.video_path, output_path, preview.segment)
                exported += 1
            except RuntimeError as error:
                errors.append(str(error))

        summary = f"Segmenti esportati: {exported}."
        if errors:
            summary += "\n\n" + "\n".join(errors)
        messagebox.showinfo("Esportazione completata", summary)


def write_config(output_path: pathlib.Path) -> None:
    config = {
        "audio": {"sample_rate": 22050, "frame_size": 1024, "hop_length": 512},
        "detection": {"min_duration": 0.3, "min_gap": 0.2},
    }
    output_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def main() -> None:
    root = tk.Tk()
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    app = ApplauseDetectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
