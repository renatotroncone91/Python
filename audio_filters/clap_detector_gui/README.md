# Clap Detector GUI

Applicativo Python con interfaccia grafica per:

- Analizzare uno o più file video (`.mp4`, `.qt`, `.mov`, `.mkv`, `.avi`).
- Estrarre l'audio e rilevare i battiti di mani (clap).
- Mostrare una preview per ogni segmento rilevato in una finestra dedicata.
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

Le preview vengono generate in memoria e non vengono salvate su disco.

## Flusso di utilizzo

1. Seleziona i file video.
2. Avvia l'analisi e attendi l'apertura della finestra di preview.
3. Ordina le colonne **Inizio**, **Fine** o **Durata** cliccando sull'intestazione.
4. Usa i pulsanti **Salva**/**Scarta** nella tabella oppure **Seleziona tutti**/**Deseleziona tutti**.
5. Premi **Esporta selezionati** per salvare in batch.

## Note

- Il rilevamento clap è basato sull'energia RMS. Puoi regolare la soglia se hai molti falsi positivi o pochi rilevamenti.
- Per file rumorosi, prova ad aumentare la **Soglia** o il **Gap minimo**.
