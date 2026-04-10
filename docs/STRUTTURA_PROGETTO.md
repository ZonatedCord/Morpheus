# Struttura Progetto

## Quadro attuale

Il progetto non e' piu solo una pipeline Python che produce CSV.

Dal 2026-04-08 la struttura reale e':

- pipeline dati Python in `src/` e `scripts/`
- backend Flask in `app.py`
- database SQLite locale in `data/leads.db`
- frontend React/Vite in `frontend/`
- dataset multipli salvati sia nel DB sia come CSV in `data/output/osm/runs/`

## Cartelle principali

- `src/finder_clienti_varesotto/`: logica applicativa Python.
- `scripts/`: entrypoint CLI e script operativi.
- `frontend/`: interfaccia React moderna con Vite e Leaflet.
- `data/input/`: input manuali e template.
- `data/output/`: output CSV della pipeline.
- `docs/`: documentazione funzionale e handoff.

## Root

- `app.py`: server Flask e API per dataset, lead e statistiche.
- `README.md`: panoramica rapida aggiornata.
- `requirements.txt`: dipendenze Python.
- `.venv/`: ambiente virtuale principale.

## Backend Python

In `src/finder_clienti_varesotto/` i file chiave oggi sono:

- `paths.py`: path centralizzati.
- `varesotto_osm.py`: estrazione da Overpass/OSM e generazione CSV.
- `db.py`: backend SQLite multi-dataset.
- `online_research.py`, `outreach_messaging.py`, `outreach_ready_total.py`, `outreach_hotlist.py`: pipeline a valle gia' esistente.

## Scripts

Gli script piu importanti sono:

- `scripts/varesotto_osm.py`: rigenera il CSV OSM di default.
- `scripts/importa_db.py`: importa un CSV nel DB e gestisce metadati dataset.
- `scripts/cerca_lead.py`: query CLI sul DB.
- `scripts/run_map.sh`: avvia Flask.

Regola: gli script devono restare wrapper sottili; la logica va in `src/`.

## Frontend

`frontend/` contiene:

- `package.json`: dipendenze React/Vite/Leaflet.
- `vite.config.js`: dev server con proxy verso Flask.
- `src/App.jsx`: UI principale.
- `src/styles.css`: stile della web app.

Il frontend non possiede dati propri. Consuma solo le API del backend.

## Dati

### Database

- `data/leads.db`: archivio locale condiviso da web, CLI e scoring.

Contiene:

- tabella `attivita`
- tabella `dataset_runs`

### CSV OSM

- `data/output/osm/clienti_varesotto.csv`: dataset di default.
- `data/output/osm/runs/`: CSV generati da popolamenti aggiuntivi.

### CSV ricerca/outreach

- `data/output/research/clienti_varesotto_outreach_hotlist.csv`: hotlist arricchita usata nel join verso SQLite.
- gli altri CSV in `data/output/research/` restano parte della pipeline commerciale esistente.

## Significato della nuova struttura multi-dataset

Prima:

- un solo CSV base
- un solo snapshot operativo nel DB

Ora:

- piu dataset distinti, uno per punto di riferimento
- ogni dataset ha il proprio `dataset_id`
- un nuovo popolamento non distrugge quelli precedenti
- la UI permette di selezionare il dataset attivo o crearne uno nuovo

## Convenzioni da mantenere

- Nessun path hardcoded fuori da `paths.py`.
- Non sostituire la pipeline CSV esistente: va estesa, non riscritta.
- La UI React e' un client del backend Flask, non una seconda fonte dati.
- La parte LLM va trattata come ultimo strato opzionale.
