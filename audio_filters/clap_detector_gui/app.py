import os
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
import wave
import subprocess
import tempfile


@dataclass
class DetectionConfig:
    window_ms: float = 20.0
    hop_ms: float = 10.0
    threshold_ratio: float = 0.6
    min_gap_s: float = 0.25
    margin_before_s: float = 0.5
    margin_after_s: float = 0.8


@dataclass
class ExportConfig:
    output_dir: Path
    video_codec: str = "libx264"
    audio_codec: str = "aac"


class ClapDetectorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Clap Detector - Estrazione clip audio/video")
        self.geometry("920x600")

        self.file_list: list[Path] = []
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self._poll_log()

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        file_frame = ttk.LabelFrame(main, text="File video")
        file_frame.pack(fill=tk.X, pady=6)

        self.file_listbox = tk.Listbox(file_frame, height=5)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)

        button_frame = ttk.Frame(file_frame)
        button_frame.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)

        ttk.Button(button_frame, text="Aggiungi file", command=self._add_files).pack(fill=tk.X)
        ttk.Button(button_frame, text="Rimuovi selezionato", command=self._remove_selected).pack(
            fill=tk.X, pady=4
        )
        ttk.Button(button_frame, text="Pulisci lista", command=self._clear_files).pack(fill=tk.X)

        settings_frame = ttk.LabelFrame(main, text="Parametri di analisi")
        settings_frame.pack(fill=tk.X, pady=6)

        self.window_ms_var = tk.DoubleVar(value=20.0)
        self.hop_ms_var = tk.DoubleVar(value=10.0)
        self.threshold_ratio_var = tk.DoubleVar(value=0.6)
        self.min_gap_var = tk.DoubleVar(value=0.25)
        self.margin_before_var = tk.DoubleVar(value=0.5)
        self.margin_after_var = tk.DoubleVar(value=0.8)

        self._add_labeled_entry(settings_frame, "Finestra (ms)", self.window_ms_var, 0, 0)
        self._add_labeled_entry(settings_frame, "Hop (ms)", self.hop_ms_var, 0, 2)
        self._add_labeled_entry(settings_frame, "Soglia (0-1)", self.threshold_ratio_var, 1, 0)
        self._add_labeled_entry(settings_frame, "Gap minimo (s)", self.min_gap_var, 1, 2)
        self._add_labeled_entry(settings_frame, "Margine inizio (s)", self.margin_before_var, 2, 0)
        self._add_labeled_entry(settings_frame, "Margine fine (s)", self.margin_after_var, 2, 2)

        output_frame = ttk.LabelFrame(main, text="Output")
        output_frame.pack(fill=tk.X, pady=6)

        self.output_dir_var = tk.StringVar(value=str(Path.cwd() / "clap_output"))
        ttk.Label(output_frame, text="Cartella output").grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(output_frame, textvariable=self.output_dir_var).grid(
            row=0, column=1, sticky=tk.EW, padx=6, pady=6
        )
        ttk.Button(output_frame, text="Scegli", command=self._choose_output_dir).grid(
            row=0, column=2, padx=6, pady=6
        )
        output_frame.columnconfigure(1, weight=1)

        action_frame = ttk.Frame(main)
        action_frame.pack(fill=tk.X, pady=6)
        self.run_button = ttk.Button(action_frame, text="Avvia analisi", command=self._run_analysis)
        self.run_button.pack(side=tk.LEFT)

        log_frame = ttk.LabelFrame(main, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        self.log_text = tk.Text(log_frame, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _add_labeled_entry(
        self, parent: ttk.LabelFrame, label: str, variable: tk.DoubleVar, row: int, column: int
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(parent, textvariable=variable, width=10).grid(
            row=row, column=column + 1, sticky=tk.W, padx=6, pady=4
        )

    def _add_files(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="Seleziona file video",
            filetypes=[("Video", "*.mp4 *.mov *.m4v *.qt *.avi *.mkv"), ("Tutti", "*.*")],
        )
        for path in file_paths:
            file_path = Path(path)
            if file_path not in self.file_list:
                self.file_list.append(file_path)
                self.file_listbox.insert(tk.END, str(file_path))

    def _remove_selected(self) -> None:
        selected = list(self.file_listbox.curselection())
        for index in reversed(selected):
            self.file_listbox.delete(index)
            del self.file_list[index]

    def _clear_files(self) -> None:
        self.file_listbox.delete(0, tk.END)
        self.file_list.clear()

    def _choose_output_dir(self) -> None:
        folder = filedialog.askdirectory(title="Seleziona cartella output")
        if folder:
            self.output_dir_var.set(folder)

    def _run_analysis(self) -> None:
        if not self.file_list:
            messagebox.showwarning("Attenzione", "Seleziona almeno un file video.")
            return

        output_dir = Path(self.output_dir_var.get()).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        detection_config = DetectionConfig(
            window_ms=self.window_ms_var.get(),
            hop_ms=self.hop_ms_var.get(),
            threshold_ratio=self.threshold_ratio_var.get(),
            min_gap_s=self.min_gap_var.get(),
            margin_before_s=self.margin_before_var.get(),
            margin_after_s=self.margin_after_var.get(),
        )

        export_config = ExportConfig(output_dir=output_dir)

        self.run_button.config(state=tk.DISABLED)
        worker = threading.Thread(
            target=self._analyze_files,
            args=(self.file_list.copy(), detection_config, export_config),
            daemon=True,
        )
        worker.start()

    def _analyze_files(
        self, files: list[Path], detection_config: DetectionConfig, export_config: ExportConfig
    ) -> None:
        try:
            for file_path in files:
                self._log(f"Analisi di {file_path}...")
                with tempfile.TemporaryDirectory() as tmpdir:
                    audio_path = Path(tmpdir) / "audio.wav"
                    self._extract_audio(file_path, audio_path)
                    clap_times = detect_claps(audio_path, detection_config)
                    if not clap_times:
                        self._log("Nessun clap rilevato.")
                        continue
                    self._log(f"Rilevati {len(clap_times)} clap. Export clip...")
                    export_clips(file_path, clap_times, detection_config, export_config)
        except Exception as exc:
            self._log(f"Errore: {exc}")
        finally:
            self._log("Analisi completata.")
            self.run_button.config(state=tk.NORMAL)

    def _extract_audio(self, input_path: Path, output_path: Path) -> None:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-f",
            "wav",
            str(output_path),
        ]
        self._log("Estrazione audio con ffmpeg...")
        self._run_cmd(cmd)

    def _run_cmd(self, cmd: list[str]) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Errore durante l'esecuzione di ffmpeg")

    def _log(self, message: str) -> None:
        self.log_queue.put(message)

    def _poll_log(self) -> None:
        while not self.log_queue.empty():
            message = self.log_queue.get_nowait()
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.after(200, self._poll_log)


def detect_claps(audio_path: Path, config: DetectionConfig) -> list[float]:
    with wave.open(str(audio_path), "rb") as wav:
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)

    if samples.size == 0:
        return []

    samples /= np.max(np.abs(samples))
    window_size = max(1, int(sample_rate * config.window_ms / 1000.0))
    hop_size = max(1, int(sample_rate * config.hop_ms / 1000.0))

    energies = []
    times = []
    for start in range(0, len(samples) - window_size, hop_size):
        window = samples[start : start + window_size]
        energy = np.sqrt(np.mean(window**2))
        energies.append(energy)
        times.append(start / sample_rate)

    if not energies:
        return []

    energies = np.array(energies)
    threshold = np.max(energies) * config.threshold_ratio
    above = energies > threshold

    clap_times: list[float] = []
    current_start = None
    for idx, is_above in enumerate(above):
        if is_above and current_start is None:
            current_start = idx
        if not is_above and current_start is not None:
            segment = energies[current_start:idx]
            peak_idx = current_start + int(np.argmax(segment))
            clap_times.append(times[peak_idx])
            current_start = None

    if current_start is not None:
        segment = energies[current_start:]
        peak_idx = current_start + int(np.argmax(segment))
        clap_times.append(times[peak_idx])

    filtered_times: list[float] = []
    last_time = -np.inf
    for t in clap_times:
        if t - last_time >= config.min_gap_s:
            filtered_times.append(t)
            last_time = t

    return filtered_times


def export_clips(
    video_path: Path, clap_times: list[float], config: DetectionConfig, export: ExportConfig
) -> None:
    base_name = video_path.stem
    output_dir = export.output_dir / base_name
    output_dir.mkdir(parents=True, exist_ok=True)

    for index, clap_time in enumerate(clap_times, start=1):
        start_time = max(0.0, clap_time - config.margin_before_s)
        end_time = clap_time + config.margin_after_s
        duration = max(0.1, end_time - start_time)

        clip_name = f"{base_name}_clap_{index:02d}"
        video_out = output_dir / f"{clip_name}.mp4"
        audio_out = output_dir / f"{clip_name}.wav"

        video_cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_time:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration:.3f}",
            "-c:v",
            export.video_codec,
            "-c:a",
            export.audio_codec,
            str(video_out),
        ]

        audio_cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_time:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-f",
            "wav",
            str(audio_out),
        ]

        subprocess.run(video_cmd, check=True)
        subprocess.run(audio_cmd, check=True)


if __name__ == "__main__":
    app = ClapDetectorApp()
    app.mainloop()
