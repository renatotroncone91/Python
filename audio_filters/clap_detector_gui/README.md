# Clap Detector GUI

Applicativo Python con interfaccia grafica per:

- Analizzare uno o più file video (`.mp4`, `.qt`, `.mov`, `.mkv`, `.avi`).
- Estrarre l'audio e rilevare i battiti di mani (clap).
- Mostrare una preview per ogni segmento rilevato.
- Salvare solo clip video (con audio incluso) con margini configurabili prima/dopo il clap.

## Requisiti

- Python 3.10+
- `ffmpeg` disponibile nel PATH
- `numpy`

Installazione dipendenze:

```bash
pip install numpy
```

## Avvio

```bash
python app.py
```

## Parametri disponibili

- **Finestra (ms)**: dimensione finestra per l'energia RMS.
- **Hop (ms)**: passo tra finestre.
- **Soglia (0-1)**: rapporto rispetto al picco massimo dell'energia (es. 0.6).
- **Gap minimo (s)**: distanza minima tra clap consecutivi.
- **Gap unione (s)**: se due clap sono più vicini di questo valore, vengono uniti nello stesso segmento (utile per applausi lunghi).
- **Margine inizio (s)**: secondi aggiuntivi prima del clap.
- **Margine fine (s)**: secondi aggiuntivi dopo il clap.

## Output

Le clip vengono salvate in una sottocartella con il nome del file originale:

```
clap_output/
  nome_video/
    nome_video_clap_01.mp4
    ...
```

Le preview vengono salvate in:

```
clap_output/_preview/
  nome_video/
    nome_video-01.png
```

## Flusso di utilizzo

1. Seleziona i file video.
2. Avvia l'analisi e attendi la generazione delle preview.
3. Spunta i segmenti che vuoi esportare (colonna **Seleziona**).
4. Premi **Esporta selezionati**.

## Note

- Il rilevamento clap è basato sull'energia RMS. Puoi regolare la soglia se hai molti falsi positivi o pochi rilevamenti.
- Per file rumorosi, prova ad aumentare la **Soglia** o il **Gap minimo**.
