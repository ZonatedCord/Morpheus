# Handoff Operativo

## Contesto rapido

Questo repo contiene una pipeline Python gia' funzionante per trovare lead locali, arricchirli e portarli fino a una hotlist commerciale.

Dal 2026-04-08 il progetto ha anche:

- backend Flask
- database SQLite multi-dataset
- frontend React/Vite

La parte LLM locale esiste come work in progress, ma non e' il centro del sistema.

## Cosa leggere per primi

1. [README.md](/Users/marcobarlera/Documents/02_PROGETTI/DataBase%20B2B/README.md)
2. [docs/STRUTTURA_PROGETTO.md](/Users/marcobarlera/Documents/02_PROGETTI/DataBase%20B2B/docs/STRUTTURA_PROGETTO.md)
3. [src/finder_clienti_varesotto/paths.py](/Users/marcobarlera/Documents/02_PROGETTI/DataBase%20B2B/src/finder_clienti_varesotto/paths.py)
4. [src/finder_clienti_varesotto/db.py](/Users/marcobarlera/Documents/02_PROGETTI/DataBase%20B2B/src/finder_clienti_varesotto/db.py)
5. [app.py](/Users/marcobarlera/Documents/02_PROGETTI/DataBase%20B2B/app.py)
6. [frontend/src/App.jsx](/Users/marcobarlera/Documents/02_PROGETTI/DataBase%20B2B/frontend/src/App.jsx)

## Stato reale del sistema

- Il CSV OSM di default continua a esistere.
- Il DB SQLite e' ora la source of truth applicativa per web e CLI.
- Il DB supporta piu dataset tramite `dataset_runs`.
- Ogni dataset corrisponde a un punto di riferimento geografico.
- La hotlist viene fusa in import, non viene persa.
- Flask espone API e puo' servire anche la build React.
- La UI React ha pannelli laterali collassabili, quindi la mappa puo' occupare quasi tutto lo spazio utile.
- La UI React avvia i popolamenti in background con job polling e progress bar.
- Se l'utente attiva l'append, una nuova area viene unita al dataset attivo senza cancellare i lead gia' presenti.

## Dataset e popolamenti

Punto importante: non c'e' piu un solo snapshot.

Ora esistono:

- dataset di default da `Vedano Olona`
- dataset aggiuntivi creati da nuovi `reference_query`

I CSV dei popolamenti aggiuntivi finiscono in:

- `data/output/osm/runs/`

I metadati vivono in:

- tabella `dataset_runs` di `data/leads.db`

## Comandi principali

Import standard:

```bash
.venv/bin/python3 scripts/importa_db.py
```

Import da un nuovo riferimento:

```bash
.venv/bin/python3 scripts/importa_db.py --reference "Busto Arsizio, Varese, Lombardia, Italia"
```

Elenco dataset:

```bash
.venv/bin/python3 scripts/cerca_lead.py --list-datasets
```

Web app:

```bash
bash scripts/run_map.sh
```

Frontend React in sviluppo:

```bash
cd frontend
npm install
npm run dev
```

## File dati da conoscere

- [clienti_varesotto.csv](/Users/marcobarlera/Documents/02_PROGETTI/DataBase%20B2B/data/output/osm/clienti_varesotto.csv)
- [clienti_varesotto_outreach_hotlist.csv](/Users/marcobarlera/Documents/02_PROGETTI/DataBase%20B2B/data/output/research/clienti_varesotto_outreach_hotlist.csv)
- [leads.db](/Users/marcobarlera/Documents/02_PROGETTI/DataBase%20B2B/data/leads.db)

## Vincoli da rispettare

1. Non riscrivere la pipeline storica se non serve.
2. Non distribuire path hardcoded fuori da `paths.py`.
3. Non trattare la parte LLM come prerequisito.
4. Non trasformare il DB in qualcosa che cancella gli altri dataset a ogni import.
5. Se cambi flussi o architettura, aggiorna anche i `.md`.

## Dove intervenire

Se il problema e' dati / import:

- `src/finder_clienti_varesotto/db.py`
- `scripts/importa_db.py`
- `src/finder_clienti_varesotto/varesotto_osm.py`

Se il problema e' UI:

- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- `app.py` solo per routing/API

Se il problema e' query terminale:

- `scripts/cerca_lead.py`

## Cosa e' stato appena fatto

- introdotto supporto multi-dataset nel DB
- aggiunta creazione di nuovi popolamenti da reference
- aggiunta UI React moderna in `frontend/`
- mantenuto fallback Flask legacy
- aggiornata la documentazione di architettura e handoff
