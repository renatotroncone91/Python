# Applause Detector GUI

GUI per analizzare video e individuare segmenti con applausi, con anteprima e selezione per esportare i tagli.

## Requisiti

- `ffmpeg` disponibile nel PATH.
- Dipendenze Python: `numpy`.

## Avvio

```bash
python audio_filters/applause_detector_app/app.py
```

1. **Apri video**: seleziona il file.
2. **Analizza**: estrae l'audio e individua i segmenti di applausi.
3. **Esporta selezionati**: salva i segmenti selezionati in una cartella.
