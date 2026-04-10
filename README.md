# FinderClientiVaresotto

Pipeline Python per trovare lead B2B locali nell'area di Varese, arricchirli e consultarli tramite SQLite, CLI e interfaccia web.

## Stato attuale

Dal 2026-04-08 il progetto ha due livelli distinti:

- backend Flask + SQLite in root e `src/`
- frontend React/Vite in `frontend/`

Il backend resta la source of truth operativa.  
Il frontend React consuma solo le API Flask e non sostituisce la pipeline CSV esistente.

## Architettura operativa

```text
DataBase B2B/
├── app.py                                  # backend Flask + API
├── frontend/                               # UI React/Vite
├── scripts/
│   ├── varesotto_osm.py                    # genera CSV OSM
│   ├── importa_db.py                       # importa CSV nel DB SQLite
│   ├── cerca_lead.py                       # query CLI sul DB
│   └── run_map.sh                          # avvia Flask
├── src/finder_clienti_varesotto/
│   ├── paths.py                            # path centralizzati
│   ├── varesotto_osm.py                    # estrazione OSM / Overpass
│   ├── db.py                               # SQLite multi-dataset
│   └── ...
└── data/
    ├── leads.db                            # database locale condiviso
    └── output/
        └── osm/
            ├── clienti_varesotto.csv       # dataset OSM di default
            └── runs/                       # CSV dei popolamenti aggiuntivi
```

## Concetti chiave

- Un `dataset` rappresenta un popolamento OSM relativo a un punto di riferimento.
- Il dataset di default resta `Vedano Olona`.
- Nuovi popolamenti non cancellano gli altri dataset: vengono salvati in SQLite e anche in `data/output/osm/runs/`.
- La hotlist viene fusa in import per marcare i lead arricchiti.
- La parte LLM resta opzionale e viene per ultima.

## Setup

```bash
bash scripts/setup.sh
.venv/bin/python3 --version
```

## Flusso base consigliato

1. Rigenera il CSV OSM di default, se serve:

```bash
.venv/bin/python3 scripts/varesotto_osm.py
```

2. Importa il dataset nel database:

```bash
.venv/bin/python3 scripts/importa_db.py
```

3. Avvia l'interfaccia web:

```bash
bash scripts/run_map.sh
```

4. Apri:

```text
http://127.0.0.1:5000
```

Se `frontend/dist` esiste, Flask serve la build React.  
Se la build non esiste ancora, Flask mostra il fallback HTML inline legacy.

## Frontend React

Il frontend moderno vive in `frontend/` e usa Vite con proxy verso Flask.

La UI React attuale include:

- pannello sinistro richiudibile per dataset, popolamento e filtri
- pannello destro richiudibile per la lista lead
- mappa centrale che si allarga quando chiudi uno o entrambi i pannelli
- progress bar del popolamento con polling su job backend
- modalita' `append` per aggiungere una nuova area al dataset attivo senza cancellare i lead esistenti
- ripresa del monitoraggio del popolamento dopo refresh della pagina

Installazione dipendenze:

```bash
cd frontend
npm install
```

Sviluppo:

```bash
npm run dev
```

Build produzione locale:

```bash
npm run build
```

Dopo `npm run build`, `bash scripts/run_map.sh` serve la UI React direttamente da Flask.

## Database e dataset multipli

In `src/finder_clienti_varesotto/db.py` il database SQLite ora gestisce:

- tabella `attivita`
- tabella `dataset_runs`

Ogni dataset ha:

- `dataset_id`
- `label`
- `reference_query`
- `reference_name`
- `reference_lat`
- `reference_lon`
- `province_query`
- contatori aggregati

Questo permette di mantenere più popolamenti separati senza perdere quello già esistente.

## Popolare da un altro punto di partenza

Da terminale puoi creare o aggiornare un dataset specifico:

```bash
.venv/bin/python3 scripts/importa_db.py \
  --reference "Busto Arsizio, Varese, Lombardia, Italia"
```

Oppure forzare metadati/dataset:

```bash
.venv/bin/python3 scripts/importa_db.py \
  --reference "Saronno, Varese, Lombardia, Italia" \
  --dataset-id "saronno-varese-lombardia-italia" \
  --label "Saronno"
```

Dalla UI React puoi fare lo stesso nella sezione `Nuovo popolamento`.

Se attivi `Unisci i nuovi risultati all'archivio attivo`:

- il dataset esistente non viene cancellato
- i nuovi lead vengono aggiunti
- i duplicati vengono aggiornati
- la UI mostra il progresso della scansione e riprende a monitorarla dopo un refresh

## CLI

Elenca i dataset:

```bash
.venv/bin/python3 scripts/cerca_lead.py --list-datasets
```

Query su un dataset specifico:

```bash
.venv/bin/python3 scripts/cerca_lead.py \
  --dataset vedano-olona-varese-lombardia-italia \
  --categoria ristorazione \
  --senza-sito \
  --limit 10
```

Solo hotlist:

```bash
.venv/bin/python3 scripts/cerca_lead.py --hotlist --priorita ALTISSIMA
```

## API Flask

Endpoint principali:

- `GET /api/datasets`
- `POST /api/datasets`
- `GET /api/leads`
- `GET /api/stats`

Filtri utili per `GET /api/leads`:

- `dataset_id`
- `priorita`
- `categoria`
- `solo_senza_sito`
- `solo_hotlist`
- `comune`
- `limit`

## File dati principali

- `data/output/osm/clienti_varesotto.csv`: dataset OSM di default
- `data/output/osm/runs/*.csv`: dataset generati da altri punti di riferimento
- `data/output/research/clienti_varesotto_outreach_hotlist.csv`: hotlist arricchita
- `data/leads.db`: archivio SQLite condiviso da web, CLI e scoring

## LLM

La parte LLM locale resta deliberatamente l'ultimo step.

- Non e' necessaria per usare mappa, lista, filtri, dataset multipli o CLI.
- I file `src/finder_clienti_varesotto/llm_filter.py` e `scripts/scorizza_lead.py` vanno considerati work in progress separato.

## Note operative

- Usa `.venv/bin/python3` invece di affidarti all'attivazione shell.
- Non distribuire path hardcoded: usa sempre `paths.py`.
- La pipeline CSV originale non va riscritta: il database e il frontend la estendono.
- Se aggiorni l'architettura, aggiorna anche i file in `docs/`.
