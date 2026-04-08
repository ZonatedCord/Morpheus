# Handoff Per Claude Code

## 1. Cosa e' questo progetto

`FinderClientiVaresotto` e' una pipeline Python per:

1. estrarre attivita locali dall'area Varese
2. ordinarle per priorita commerciale
3. arricchirle con segnali digitali e contatti
4. trasformarle in file `outreach-ready`
5. estrarre hotlist su cui scrivere messaggi mirati

Non e' un singolo scraper.  
E' una pipeline a piu stadi, con output intermedi che diventano input del passo successivo.

## 2. Obiettivo operativo attuale

Lo stato attuale del progetto non e' "trovare tutte le aziende del mondo", ma:

- avere un dataset base affidabile da OSM
- distinguere tra lead verificati e lead solo plausibili
- non inventare recensioni o dati mancanti
- lavorare in modo commerciale su shortlist e hotlist, non su tutto il dataset indistintamente

## 3. File da leggere per primi

Se devi entrare operativo subito, leggi in questo ordine:

1. [docs/RIEPILOGO_PROGETTO.md](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/docs/RIEPILOGO_PROGETTO.md)
2. [src/finder_clienti_varesotto/paths.py](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/src/finder_clienti_varesotto/paths.py)
3. [src/finder_clienti_varesotto/varesotto_osm.py](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/src/finder_clienti_varesotto/varesotto_osm.py)
4. [src/finder_clienti_varesotto/outreach_messaging.py](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/src/finder_clienti_varesotto/outreach_messaging.py)
5. [src/finder_clienti_varesotto/outreach_ready_total.py](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/src/finder_clienti_varesotto/outreach_ready_total.py)
6. [src/finder_clienti_varesotto/outreach_hotlist.py](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/src/finder_clienti_varesotto/outreach_hotlist.py)

## 4. File dati oggi piu importanti

### Dataset base

- [clienti_varesotto.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/osm/clienti_varesotto.csv)

Questo e' il dataset grezzo principale da OSM.  
Contiene `6645` righe e va considerato incompleto e a volte ambiguo.

### CSV totale commerciale

- [clienti_varesotto_outreach_ready.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/research/clienti_varesotto_outreach_ready.csv)

Questo e' il file totale attualmente piu utile per lavorare a valle.

Contiene:

- righe fuse dalla shortlist gia' arricchita
- tutto il resto del dataset trasformato in forma commerciale prudente
- stati `OK`, `PARZIALE`, `DA_VERIFICARE`

### Hotlist operative

- [clienti_varesotto_outreach_ok.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/research/clienti_varesotto_outreach_ok.csv)
- [clienti_varesotto_outreach_parziali_contattabili.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/research/clienti_varesotto_outreach_parziali_contattabili.csv)
- [clienti_varesotto_outreach_hotlist.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/research/clienti_varesotto_outreach_hotlist.csv)

Se devi lavorare sull'outreach, di solito non partire dal CSV da `6645` righe.  
Parti dalla `hotlist`.

### Batch piccolo curato

- [attivita_shortlist_outreach_ready.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/research/attivita_shortlist_outreach_ready.csv)

Questo e' il batch piccolo dove i dati sono stati curati piu a fondo.  
E' utile come riferimento di qualita per capire il formato desiderato.

## 5. Stato attuale dei dati

### Fonte della verita'

La "source of truth" operativa oggi e':

- base territoriale: [clienti_varesotto.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/osm/clienti_varesotto.csv)
- vista commerciale completa: [clienti_varesotto_outreach_ready.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/research/clienti_varesotto_outreach_ready.csv)
- vista azionabile: [clienti_varesotto_outreach_hotlist.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/research/clienti_varesotto_outreach_hotlist.csv)

### Significato degli stati

- `OK`: match credibile e abbastanza dati per lavorare commercialmente
- `PARZIALE`: lead plausibile ma con contatti, recensioni o anagrafica ancora sporchi
- `DA_VERIFICARE`: nome vecchio, attivita forse rinominata o dati troppo poveri

Non trattare mai un `PARZIALE` come se fosse gia' un `OK`.

## 6. Pipeline reale

### A. Estrazione OSM

Comando:

```bash
python3 scripts/varesotto_osm.py
```

Produce il dataset base da OSM / Overpass.

### B. Ricerca online best-effort

Comando:

```bash
python3 scripts/ricerca_aziende_online.py --limit 10
```

Serve ad arricchire piccoli batch.  
Non e' affidabile come unica base per il dataset totale.

### C. Shortlist per Deep Research

Comando:

```bash
python3 scripts/prepara_shortlist_chatgpt.py --limit 30
```

Serve quando si vuole usare ChatGPT / Deep Research su batch ridotti.

### D. Messaggi mirati

Comando:

```bash
python3 scripts/genera_messaggi_mirati.py --limit 30
```

Usa dati strutturati + note manuali.  
Non deve inventare recensioni o criticita.

### E. CSV totale outreach-ready

Comando:

```bash
python3 scripts/genera_outreach_ready_totale.py
```

Trasforma il CSV OSM completo in un file commerciale unico.

### F. Estrazione hotlist

Comando:

```bash
python3 scripts/estrai_hotlist_outreach.py \
  --input data/output/research/clienti_varesotto_outreach_ready.csv \
  --output-ok data/output/research/clienti_varesotto_outreach_ok.csv \
  --output-parziali data/output/research/clienti_varesotto_outreach_parziali_contattabili.csv \
  --output-hotlist data/output/research/clienti_varesotto_outreach_hotlist.csv \
  --summary data/output/research/clienti_varesotto_outreach_hotlist.md
```

## 7. Vincoli logici da rispettare

1. Non inventare dati

Se non esistono recensioni o contatti credibili, non aggiungerli "per plausibilita'".

2. OSM prima del motore di ricerca

Per i nomi ambigui, il riferimento corretto e' l'`OSM URL`, non il nome da solo.

3. Il dataset base e' rumoroso

Molti limiti a valle dipendono dal fatto che il CSV OSM non ha comune, indirizzo, email o sito.

4. La ricerca online e' best-effort

Google Maps, Tripadvisor, TheFork, Facebook e alcune SERP possono bloccare o dare dati sporchi.

5. La hotlist e' il punto di lavoro

Non usare tutto il dataset come se fosse gia' pronto per outreach.

## 8. Scelte implementative da non rompere

### Path centralizzati

Non distribuire nuovi path hardcoded nel codice.  
Usa [paths.py](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/src/finder_clienti_varesotto/paths.py).

### `scripts/` come wrapper sottili

Gli script in `scripts/` devono restare leggeri e delegare la logica a `src/`.

### CSV come interfaccia tra stadi

La pipeline e' basata su file CSV leggibili e riusabili.  
Non sostituire questa scelta con formati piu complessi senza motivo forte.

### `.venv` come ambiente principale

`.venv` e' l'ambiente da usare.  
`venv` esiste come legacy e non va considerato il default.

## 9. Cosa puoi migliorare senza rompere il progetto

- migliorare filtri e classificazione dei `PARZIALI`
- aumentare la qualita dei `OK`
- raffinare la generazione messaggi a partire dalla hotlist
- migliorare i parser di fonti locali accessibili
- aggiornare la documentazione quando cambia il flusso

## 10. Cosa non devi assumere

- che tutti i file in `research/` abbiano la stessa affidabilita
- che tutti i nomi siano univoci
- che le fonti review siano fetchabili in modo stabile
- che il CSV totale sia gia' "pronto vendita" senza filtro
- che un sito trovato automaticamente sia sempre il sito giusto

## 11. Strategia consigliata per entrare nel team

Se devi contribuire in modo utile:

1. leggi il `RIEPILOGO_PROGETTO`
2. apri il CSV `outreach_ready` totale
3. apri la `hotlist`
4. capisci come sono stati costruiti `OK` e `PARZIALI`
5. lavora su un miglioramento circoscritto, non su tutto il sistema insieme

## 12. TL;DR per Claude Code

Questo progetto e' una pipeline commerciale locale.

Il cuore oggi non e' piu solo lo scraping OSM, ma la trasformazione progressiva da:

- dataset grezzo
- a dataset commerciale prudente
- a hotlist operativa

Se devi essere utile rapidamente:

- usa [clienti_varesotto_outreach_ready.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/research/clienti_varesotto_outreach_ready.csv) come vista completa
- usa [clienti_varesotto_outreach_hotlist.csv](/Users/marcobarlera/Documents/02_PROGETTI/FinderClientiVaresotto/data/output/research/clienti_varesotto_outreach_hotlist.csv) come vista di lavoro
- non alzare a `OK` quello che e' solo plausibile
- non inventare review o dati mancanti
