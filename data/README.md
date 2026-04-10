# Dati

Questa cartella contiene solo file operativi del progetto.

## Input

- `input/linkedin/`: file usati per preparare e compilare il flusso LinkedIn.
- `input/research/`: file con note manuali, recensioni e osservazioni per i messaggi mirati.

## Output

- `output/osm/`: CSV e spreadsheet generati dal finder OpenStreetMap.
- `output/linkedin/`: CSV generati dall'import dei risultati LinkedIn.
- `output/outreach/`: analisi commerciali e bozze di messaggio generate dallo script di outreach.
- `output/research/`: file di ricerca e selezione commerciale.
  Oggi i file piu utili sono `clienti_varesotto_outreach_ready.csv` e `clienti_varesotto_outreach_hotlist.csv`.

## Regola pratica

Se devi cercare un file, prima identifica il flusso:

- OSM automatico -> `data/output/osm/`
- LinkedIn manuale -> `data/input/linkedin/` e `data/output/linkedin/`
- Ricerca online aziende -> `data/output/research/`
- Messaggi mirati -> `data/input/research/` e `data/output/outreach/`
