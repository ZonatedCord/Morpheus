# Flusso LinkedIn

## Script coinvolti

- `scripts/varesotto_linkedin.py`: genera i link e il template di input.
- `scripts/varesotto_linkedin_import.py`: converte l'input compilato in CSV.
- `src/finder_clienti_varesotto/varesotto_linkedin.py`: logica di generazione.
- `src/finder_clienti_varesotto/varesotto_linkedin_import.py`: logica di import.

## File di lavoro

- `data/input/linkedin/linkedin_links.txt`: elenco dei link di ricerca per categoria.
- `data/input/linkedin/input.txt`: template da compilare manualmente.
- `data/output/linkedin/clienti_varesotto_linkedin.csv`: output finale del flusso LinkedIn.

## Sequenza operativa

1. Esegui `python3 scripts/varesotto_linkedin.py`.
2. Apri `data/input/linkedin/linkedin_links.txt`.
3. Copia i risultati in `data/input/linkedin/input.txt`.
4. Esegui `python3 scripts/varesotto_linkedin_import.py`.
5. Lavora sul CSV finale in `data/output/linkedin/`.

## Perche e separato da OSM

Il flusso LinkedIn e manuale e non deve sovrascrivere gli export del flusso OSM. Per questo usa cartelle e nomi file dedicati.
