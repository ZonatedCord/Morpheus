# Riepilogo Completo Progetto

## 1. Scopo

`FinderClientiVaresotto` e' una pipeline locale per:

1. estrarre attivita da OSM / Overpass
2. ordinarle per priorita commerciale e distanza
3. arricchirle con segnali digitali e contatti
4. costruire viste operative per outreach
5. consultare il tutto da database, CLI e interfaccia web

Il progetto non e' una riscrittura del flusso storico.  
La pipeline CSV continua a esistere; SQLite e React la estendono.

## 2. Architettura attuale

Dal 2026-04-08 l'architettura reale e' questa:

- `src/`: logica Python
- `scripts/`: entrypoint CLI
- `data/output/*.csv`: interfaccia operativa tra i flussi
- `data/leads.db`: archivio SQLite locale
- `app.py`: backend Flask con API
- `frontend/`: UI React/Vite con Leaflet

Questa separazione serve a evitare due errori opposti:

- continuare a rileggere i CSV ad ogni request
- buttare via la pipeline CSV che gia' funziona

## 3. Scelte chiave

### 3.1 CSV-first, ma non CSV-only

I CSV restano importanti per:

- audit
- passaggi semi-manuali
- controllo umano
- export leggibili

Ma la consultazione applicativa ora passa da SQLite.

### 3.2 SQLite locale

La scelta del DB resta SQLite perche':

- uso personale locale
- zero overhead
- query veloci
- nessuna infrastruttura esterna

### 3.3 Frontend React sopra API Flask

La UI moderna non parla direttamente con i CSV.  
Parla con Flask, che interroga SQLite.

### 3.4 LLM per ultimo

La parte LLM non e' il cuore del sistema.  
Prima devono funzionare bene:

- estrazione OSM
- import nel DB
- filtri
- mappa
- lista
- gestione dei dataset

## 4. Nuovo concetto: dataset multipli

Il cambiamento architetturale piu importante e' questo:

- il punto di riferimento non e' piu fisso e unico
- ogni popolamento genera un dataset distinto

Un dataset e' definito da:

- `dataset_id`
- `label`
- `reference_query`
- `reference_name`
- `reference_lat`
- `reference_lon`
- `province_query`

I metadati vivono in `dataset_runs`.  
I lead vivono in `attivita` e sono collegati al relativo `dataset_id`.

## 5. Stato operativo dei dati

### Dataset OSM di default

- file: `data/output/osm/clienti_varesotto.csv`
- riferimento storico: `Vedano Olona`

### Dataset aggiuntivi

- cartella: `data/output/osm/runs/`
- ogni file rappresenta un popolamento da un altro punto di partenza

### Hotlist

- file: `data/output/research/clienti_varesotto_outreach_hotlist.csv`

La hotlist viene unita in import per marcare lead arricchiti e portare nel DB:

- `stato`
- `proposta`
- `criticita`
- `rating`
- `email`
- `in_hotlist`

## 6. Interfacce attive

### Web

`app.py` espone:

- `GET /api/datasets`
- `POST /api/datasets`
- `GET /api/leads`
- `GET /api/stats`

Se `frontend/dist` esiste, Flask serve la build React su `/`.

### CLI

`scripts/cerca_lead.py` permette:

- elenco dataset
- filtri per categoria, priorita, comune
- solo senza sito
- solo hotlist
- scelta del dataset attivo

### Import

`scripts/importa_db.py` permette:

- import standard del dataset di default
- import legato a un nuovo `--reference`
- override di `--dataset-id` e `--label`

## 7. Flusso base consigliato

1. Genera o aggiorna il CSV OSM:

```bash
.venv/bin/python3 scripts/varesotto_osm.py
```

2. Importa nel database:

```bash
.venv/bin/python3 scripts/importa_db.py
```

3. Avvia la web app:

```bash
bash scripts/run_map.sh
```

4. Se vuoi creare un altro popolamento:

```bash
.venv/bin/python3 scripts/importa_db.py --reference "Busto Arsizio, Varese, Lombardia, Italia"
```

Oppure usa la sezione `Nuovo popolamento` nella UI.

## 8. Cosa e' stato aggiunto in questa fase

- supporto `Lat/Lon` end-to-end nel dataset operativo
- backend SQLite con tabella `dataset_runs`
- import dataset-aware che non cancella gli altri popolamenti
- query API e CLI dataset-aware
- lista laterale collegata alla mappa
- frontend React moderno in `frontend/`
- fallback Flask legacy se la build React non esiste

## 9. Cosa non va rotto

- La pipeline CSV storica.
- Il join hotlist best-effort per nome normalizzato.
- L'uso di `paths.py` come unico posto canonico per i path.
- L'idea che il DB sia un layer di consultazione persistente, non un sostituto della pipeline.

## 10. Stato LLM

La parte LLM e' intenzionalmente posticipata.

I file `src/finder_clienti_varesotto/llm_filter.py` e `scripts/scorizza_lead.py` vanno considerati separati dal flusso base e non devono guidare le scelte architetturali correnti.

## 11. TL;DR per un altro modello

Leggi in quest'ordine:

1. `README.md`
2. `docs/STRUTTURA_PROGETTO.md`
3. `src/finder_clienti_varesotto/paths.py`
4. `src/finder_clienti_varesotto/db.py`
5. `app.py`
6. `frontend/src/App.jsx`

Regola pratica:

- se lavori sui dati, parti da `src/` e `scripts/`
- se lavori sulla UI, parti da `frontend/`
- se cambi architettura o flussi, aggiorna i `.md`
