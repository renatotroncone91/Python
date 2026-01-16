import base64
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import tempfile
import wave
import subprocess

import numpy as np

PREVIEW_WIDTH = 360


@dataclass
class DetectionConfig:
    window_ms: float = 20.0
    hop_ms: float = 10.0
    threshold_ratio: float = 0.6
    min_gap_s: float = 0.25
    merge_gap_s: float = 2.0
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
        self.segments: dict[str, Segment] = {}
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.preview_images: dict[str, tk.PhotoImage] = {}
        self.preview_window: tk.Toplevel | None = None
        self.preview_tree: ttk.Treeview | None = None
        self.preview_label: ttk.Label | None = None
        self.preview_sort_reverse: dict[str, bool] = {}

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
        self.merge_gap_var = tk.DoubleVar(value=2.0)
        self.margin_before_var = tk.DoubleVar(value=0.5)
        self.margin_after_var = tk.DoubleVar(value=0.8)

        self._add_labeled_entry(settings_frame, "Finestra (ms)", self.window_ms_var, 0, 0)
        self._add_labeled_entry(settings_frame, "Hop (ms)", self.hop_ms_var, 0, 2)
        self._add_labeled_entry(settings_frame, "Soglia (0-1)", self.threshold_ratio_var, 1, 0)
        self._add_labeled_entry(settings_frame, "Gap minimo (s)", self.min_gap_var, 1, 2)
        self._add_labeled_entry(settings_frame, "Gap unione (s)", self.merge_gap_var, 2, 0)
        self._add_labeled_entry(settings_frame, "Margine inizio (s)", self.margin_before_var, 2, 2)
        self._add_labeled_entry(settings_frame, "Margine fine (s)", self.margin_after_var, 3, 0)

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
        self.export_button = ttk.Button(
            action_frame, text="Esporta selezionati", command=self._export_selected, state=tk.DISABLED
        )
        self.export_button.pack(side=tk.LEFT, padx=6)

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
            merge_gap_s=self.merge_gap_var.get(),
            margin_before_s=self.margin_before_var.get(),
            margin_after_s=self.margin_after_var.get(),
        )

        self.run_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        self.preview_images.clear()
        self.segments.clear()
        if self.preview_window is not None:
            self.preview_window.destroy()
            self.preview_window = None
            self.preview_tree = None
            self.preview_label = None
        worker = threading.Thread(
            target=self._analyze_files,
            args=(self.file_list.copy(), detection_config),
            daemon=True,
        )
        worker.start()

    def _analyze_files(
        self, files: list[Path], detection_config: DetectionConfig
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
                    self._log(f"Rilevati {len(clap_times)} clap. Generazione preview...")
                    self._build_segments(file_path, clap_times, detection_config)
        except Exception as exc:
            self._log(f"Errore: {exc}")
        finally:
            self._log("Analisi completata.")
            self.run_button.config(state=tk.NORMAL)
            if self.segments:
                self.export_button.config(state=tk.NORMAL)
                self._open_preview_window()

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

    def _build_segments(
        self,
        video_path: Path,
        clap_times: list[float],
        config: DetectionConfig,
    ) -> None:
        base_name = video_path.stem
        grouped = group_clap_segments(clap_times, config.merge_gap_s)
        for index, (start_clap, end_clap) in enumerate(grouped, start=1):
            start_time = max(0.0, start_clap - config.margin_before_s)
            end_time = end_clap + config.margin_after_s
            duration = max(0.1, end_time - start_time)

            segment_id = f"{base_name}-{index:02d}"
            segment = Segment(
                id=segment_id,
                video_path=video_path,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                selected=True,
            )
            self.segments[segment_id] = segment
        if self.preview_tree is not None:
            for segment in self.segments.values():
                self._add_preview_row(segment)

    def _toggle_segment_selection(self, event: tk.Event) -> None:
        if self.preview_tree is None:
            return
        column = self.preview_tree.identify_column(event.x)
        row_id = self.preview_tree.identify_row(event.y)
        if not row_id:
            return
        if column in {"#5", "#6", "#7"}:
            self._handle_preview_action(row_id, column)
            return
        segment = self.segments.get(row_id)
        if segment is None:
            return
        if column == "#5":
            segment.selected = not segment.selected
            self.preview_tree.set(row_id, "selected", "Sì" if segment.selected else "No")

    def _on_segment_select(self, _event: tk.Event) -> None:
        if self.preview_tree is None or self.preview_label is None:
            return
        selected = self.preview_tree.selection()
        if not selected:
            return
        segment = self.segments.get(selected[0])
        if segment is None:
            return
        image = self.preview_images.get(segment.id)
        if image is None:
            image = create_preview_image(segment.video_path, segment.start_time)
            self.preview_images[segment.id] = image
        self.preview_label.config(image=image)

    def _handle_preview_action(self, row_id: str, column: str) -> None:
        segment = self.segments.get(row_id)
        if segment is None or self.preview_tree is None:
            return
        if column == "#6":
            export_config = ExportConfig(output_dir=Path(self.output_dir_var.get()).expanduser())
            try:
                export_video_clip(segment, export_config)
                self._log(f"Esportato {segment.id}")
                segment.selected = False
                self.preview_tree.set(row_id, "selected", "No")
            except Exception as exc:
                self._log(f"Errore export: {exc}")
        elif column == "#7":
            segment.selected = False
            self.preview_tree.set(row_id, "selected", "No")

    def _export_selected(self) -> None:
        selected_segments = [segment for segment in self.segments.values() if segment.selected]
        if not selected_segments:
            messagebox.showwarning("Attenzione", "Nessun segmento selezionato per l'export.")
            return
        export_config = ExportConfig(output_dir=Path(self.output_dir_var.get()).expanduser())
        self.run_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        worker = threading.Thread(
            target=self._export_worker,
            args=(selected_segments, export_config),
            daemon=True,
        )
        worker.start()

    def _export_worker(self, segments: list["Segment"], export_config: ExportConfig) -> None:
        try:
            for segment in segments:
                export_video_clip(segment, export_config)
                self._log(f"Esportato {segment.id}")
        except Exception as exc:
            self._log(f"Errore export: {exc}")
        finally:
            self._log("Export completato.")
            self.run_button.config(state=tk.NORMAL)
            self.export_button.config(state=tk.NORMAL)

    def _open_preview_window(self) -> None:
        if self.preview_window is not None:
            self.preview_window.deiconify()
            return
        self.preview_window = tk.Toplevel(self)
        self.preview_window.title("Preview segmenti")
        self.preview_window.geometry("980x520")

        segment_frame = ttk.Frame(self.preview_window, padding=12)
        segment_frame.pack(fill=tk.BOTH, expand=True)

        self.preview_tree = ttk.Treeview(
            segment_frame,
            columns=("file", "start", "end", "duration", "selected", "save", "discard"),
            show="headings",
        )
        self.preview_tree.heading("file", text="File")
        self.preview_tree.heading("start", text="Inizio (s)", command=lambda: self._sort_preview("start"))
        self.preview_tree.heading("end", text="Fine (s)", command=lambda: self._sort_preview("end"))
        self.preview_tree.heading("duration", text="Durata (s)", command=lambda: self._sort_preview("duration"))
        self.preview_tree.heading("selected", text="Seleziona")
        self.preview_tree.heading("save", text="Salva")
        self.preview_tree.heading("discard", text="Scarta")
        self.preview_tree.column("file", width=260, anchor=tk.W)
        self.preview_tree.column("start", width=80, anchor=tk.E)
        self.preview_tree.column("end", width=80, anchor=tk.E)
        self.preview_tree.column("duration", width=90, anchor=tk.E)
        self.preview_tree.column("selected", width=90, anchor=tk.CENTER)
        self.preview_tree.column("save", width=70, anchor=tk.CENTER)
        self.preview_tree.column("discard", width=70, anchor=tk.CENTER)
        self.preview_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.preview_tree.bind("<<TreeviewSelect>>", self._on_segment_select)
        self.preview_tree.bind("<ButtonRelease-1>", self._toggle_segment_selection)

        preview_frame = ttk.Frame(segment_frame)
        preview_frame.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)
        ttk.Label(preview_frame, text="Preview").pack()
        self.preview_label = ttk.Label(preview_frame)
        self.preview_label.pack(pady=6)

        action_frame = ttk.Frame(self.preview_window, padding=12)
        action_frame.pack(fill=tk.X)
        ttk.Button(action_frame, text="Esporta selezionati", command=self._export_selected).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="Seleziona tutti", command=self._select_all_segments).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(action_frame, text="Deseleziona tutti", command=self._deselect_all_segments).pack(
            side=tk.LEFT
        )

        for segment in self.segments.values():
            self._add_preview_row(segment)

    def _add_preview_row(self, segment: "Segment") -> None:
        if self.preview_tree is None:
            return
        self.preview_tree.insert(
            "",
            tk.END,
            iid=segment.id,
            values=(
                segment.video_path.name,
                f"{segment.start_time:.2f}",
                f"{segment.end_time:.2f}",
                f"{segment.duration:.2f}",
                "Sì" if segment.selected else "No",
                "Salva",
                "Scarta",
            ),
        )

    def _select_all_segments(self) -> None:
        for segment in self.segments.values():
            segment.selected = True
            if self.preview_tree is not None:
                self.preview_tree.set(segment.id, "selected", "Sì")

    def _deselect_all_segments(self) -> None:
        for segment in self.segments.values():
            segment.selected = False
            if self.preview_tree is not None:
                self.preview_tree.set(segment.id, "selected", "No")

    def _sort_preview(self, key: str) -> None:
        if self.preview_tree is None:
            return
        reverse = self.preview_sort_reverse.get(key, False)
        items = list(self.preview_tree.get_children(""))
        items.sort(
            key=lambda item: float(self.preview_tree.set(item, key)),
            reverse=reverse,
        )
        for index, item in enumerate(items):
            self.preview_tree.move(item, "", index)
        self.preview_sort_reverse[key] = not reverse

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


def group_clap_segments(clap_times: list[float], merge_gap_s: float) -> list[tuple[float, float]]:
    if not clap_times:
        return []
    sorted_times = sorted(clap_times)
    segments: list[tuple[float, float]] = []
    segment_start = sorted_times[0]
    last_time = sorted_times[0]

    for time in sorted_times[1:]:
        if time - last_time <= merge_gap_s:
            last_time = time
            continue
        segments.append((segment_start, last_time))
        segment_start = time
        last_time = time

    segments.append((segment_start, last_time))
    return segments


@dataclass
class Segment:
    id: str
    video_path: Path
    start_time: float
    end_time: float
    duration: float
    selected: bool = True


def create_preview_image(video_path: Path, timestamp: float) -> tk.PhotoImage:
    cmd = [
        "ffmpeg",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(video_path),
        "-vf",
        f"scale={PREVIEW_WIDTH}:-1",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True)
    encoded = base64.b64encode(result.stdout).decode("ascii")
    return tk.PhotoImage(data=encoded)


def export_video_clip(segment: Segment, export: ExportConfig) -> None:
    base_name = segment.video_path.stem
    output_dir = export.output_dir / base_name
    output_dir.mkdir(parents=True, exist_ok=True)

    clip_name = f"{base_name}_clap_{segment.id.split('-')[-1]}"
    video_out = output_dir / f"{clip_name}.mp4"

    video_cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{segment.start_time:.3f}",
        "-i",
        str(segment.video_path),
        "-t",
        f"{segment.duration:.3f}",
        "-c:v",
        export.video_codec,
        "-c:a",
        export.audio_codec,
        str(video_out),
    ]

    subprocess.run(video_cmd, check=True, capture_output=True)


if __name__ == "__main__":
    app = ClapDetectorApp()
    app.mainloop()
