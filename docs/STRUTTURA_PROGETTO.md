# Struttura Progetto

## Obiettivo della riorganizzazione

Il progetto era quasi interamente appiattito in root. Ora la cartella distingue in modo esplicito:

- codice applicativo
- script eseguibili
- dati di input
- output generati
- documentazione

## Cartelle principali

- `src/finder_clienti_varesotto/`: logica Python del progetto.
- `scripts/`: entrypoint eseguibili e setup locale.
- `data/input/linkedin/`: file di lavoro per il flusso LinkedIn.
- `data/output/osm/`: export prodotti dal finder OSM.
- `data/output/linkedin/`: export prodotti dall'import LinkedIn.
- `docs/`: spiegazioni funzionali e struttura del progetto.

## Convenzioni adottate

- Gli script in `scripts/` importano il package da `src/`, cosi la root resta pulita.
- I path principali sono centralizzati in `src/finder_clienti_varesotto/paths.py`.
- Gli output OSM e LinkedIn sono separati per evitare sovrascritture accidentali.

## Eccezioni lasciate in root

- `.venv`: ambiente virtuale principale.
- `venv`: ambiente virtuale legacy lasciato fermo per non rompere path interni.
- `__pycache__`: cache Python generata automaticamente.

Questi elementi non sono parte della struttura logica del progetto e non vanno usati per organizzare il lavoro.
