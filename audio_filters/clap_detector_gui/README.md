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

## Parametri disponibili (spiegazione dettagliata)

- **Finestra (ms)**: durata della finestra su cui si calcola l'energia RMS. Valori più alti rendono il rilevamento più stabile ma meno reattivo ai clap molto rapidi.
- **Hop (ms)**: passo tra una finestra e l'altra. Valori più bassi aumentano la precisione temporale, ma richiedono più calcolo.
- **Soglia (0-1)**: percentuale del picco massimo di energia. Se alzi la soglia rilevi solo clap molto forti; se la abbassi aumentano i rilevamenti (anche falsi positivi).
- **Gap minimo (s)**: distanza minima tra due clap consecutivi per evitare doppie rilevazioni dello stesso evento.
- **Gap unione (s)**: se due clap sono più vicini di questo valore, vengono uniti nello stesso segmento (utile per applausi lunghi).
- **Margine inizio (s)**: secondi aggiuntivi inseriti prima dell'inizio del segmento.
- **Margine fine (s)**: secondi aggiuntivi inseriti dopo la fine del segmento.

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
