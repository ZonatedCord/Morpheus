# Riepilogo Completo Progetto

## 1. Scopo del progetto

`FinderClientiVaresotto` e' un progetto Python orientato alla ricerca e preparazione commerciale di attivita locali nell'area Varese / Vedano Olona.

L'obiettivo non e' solo estrarre un elenco di attivita, ma costruire una pipeline che porti da:

1. dataset grezzo di aziende
2. arricchimento e verifica
3. analisi commerciale
4. shortlist contattabile
5. bozza di messaggio o hotlist per outreach

Il progetto quindi unisce:

- estrazione automatica dati da OpenStreetMap / Overpass
- flusso alternativo manuale assistito da LinkedIn
- ricerca online best-effort
- preparazione batch per ChatGPT / Deep Research
- costruzione di file `outreach-ready`
- filtraggio finale in hotlist operative

## 2. Idea architetturale di fondo

La scelta architetturale principale e' stata separare il progetto in livelli chiari:

- `src/` contiene la logica applicativa
- `scripts/` contiene solo entrypoint eseguibili
- `data/` contiene input e output operativi
- `docs/` contiene la documentazione

Questo evita che la root diventi una cartella piatta con script, CSV e appunti tutti mescolati.

### Scelte architetturali principali

1. `src` + `scripts`

La logica vive nel package `src/finder_clienti_varesotto/` e gli script in `scripts/` fanno solo bootstrap e chiamata a `main()`.  
Questo rende il codice riusabile e piu facile da mantenere.

2. Path centralizzati

I path principali sono centralizzati in `src/finder_clienti_varesotto/paths.py`.  
La logica non usa path sparsi hardcoded in ogni modulo.

3. CSV-first

La pipeline usa CSV come formato operativo principale, perche':

- e' leggibile in spreadsheet
- e' facile da versionare
- e' facile da usare in passaggi semi-manuali
- si presta bene al lavoro con ChatGPT / Deep Research

4. Automazione prudente, non "magica"

Il progetto evita di inventare dati quando le fonti sono incomplete.  
Se non ci sono recensioni affidabili, il sistema genera output prudenti e segnala cosa verificare.

5. Human-in-the-loop

Non tutto e' completamente automatico per scelta:

- LinkedIn richiede passaggi manuali
- ChatGPT / Deep Research lavora meglio su shortlist ridotte
- messaggi mirati seri richiedono fonti credibili o note umane

## 3. Scelte logiche del dominio

### 3.1 Punto di riferimento geografico

Il progetto usa `Vedano Olona` come riferimento principale per distanza e priorita territoriale.

La logica base e':

- cercare attivita nella provincia di Varese
- calcolare la distanza dal riferimento
- dare priorita alle attivita piu vicine
- dare ancora piu peso a quelle senza sito o con presenza digitale debole

### 3.2 Priorita commerciali

Le priorita usate nel dataset sono:

- `ALTISSIMA`
- `ALTA`
- `MEDIA`
- `BASSA`
- `MOLTO BASSA`

La priorita non e' solo geografica: incorpora anche opportunita commerciale, soprattutto nei flussi di shortlist e outreach.

### 3.3 Categorie

Il progetto raggruppa le attivita in macro-categorie coerenti con il lavoro commerciale:

- `Ristorazione`
- `Ospitalita'`
- `Beauty & Benessere`
- `Fitness & Sport`
- `Sanita'`
- `Servizi Professionali`
- `Artigiani`
- `Negozi`

Questa scelta semplifica:

- query OSM
- shortlist
- proposta commerciale
- template messaggi

### 3.4 Filosofia dell'outreach

La logica commerciale del progetto e':

- non contattare "a caso"
- partire dai gap reali o plausibili
- distinguere tra `OK`, `PARZIALE`, `DA_VERIFICARE`
- usare shortlist e hotlist per non lavorare su migliaia di righe indistinte

## 4. Organizzazione delle cartelle

Struttura attuale semplificata:

```text
FinderClientiVaresotto/
├── README.md
├── requirements.txt
├── docs/
├── data/
│   ├── input/
│   │   ├── linkedin/
│   │   └── research/
│   └── output/
│       ├── osm/
│       ├── linkedin/
│       ├── research/
│       └── outreach/
├── scripts/
└── src/
    └── finder_clienti_varesotto/
```

### Root

- `README.md`: panoramica rapida del progetto
- `requirements.txt`: dipendenze Python minime

### `src/finder_clienti_varesotto/`

Contiene la logica applicativa vera.

- `paths.py`: costanti e path canonici
- `varesotto_osm.py`: generazione dataset da OSM / Overpass
- `varesotto_client_finder.py`: entry logico storico verso il flusso OSM
- `varesotto_linkedin.py`: generazione dei link e template LinkedIn
- `varesotto_linkedin_import.py`: parser del file manuale LinkedIn
- `online_research.py`: arricchimento online best-effort
- `chatgpt_research_prep.py`: preparazione shortlist per ChatGPT / Deep Research
- `outreach_messaging.py`: logica per analisi commerciale e bozza messaggi
- `outreach_ready_total.py`: fusione del dataset completo in CSV `outreach-ready`
- `outreach_hotlist.py`: estrazione di hotlist operative dal CSV completo

### `scripts/`

Contiene i wrapper CLI, utili per eseguire i flussi senza import manuali.

- `_bootstrap.py`: aggiunge `src/` al `sys.path`
- `setup.sh`: setup iniziale ambiente e dipendenze
- `varesotto_client_finder.py`
- `varesotto_osm.py`
- `varesotto_linkedin.py`
- `varesotto_linkedin_import.py`
- `ricerca_aziende_online.py`
- `prepara_shortlist_chatgpt.py`
- `genera_messaggi_mirati.py`
- `genera_outreach_ready_totale.py`
- `estrai_hotlist_outreach.py`

### `data/input/`

Input modificabili dall'utente o usati come passaggi intermedi umani.

#### `data/input/linkedin/`

- `input.txt`: template da compilare con dati copiati da LinkedIn
- `linkedin_links.txt`: elenco link di ricerca generati automaticamente

#### `data/input/research/`

- `attivita_insights.csv`: note manuali per messaggi mirati
- `attivita_shortlist_chatgpt.csv`: shortlist ridotta da dare a ChatGPT / Deep Research
- `attivita_shortlist_chatgpt_template.csv`: template risultati attesi da ChatGPT

### `data/output/`

Output generati dai flussi.

#### `data/output/osm/`

- `clienti_varesotto.csv`: dataset base principale
- `clienti_varesotto.xlsx`: versione foglio di calcolo
- `clienti_varesotto_test.csv`: export di test

#### `data/output/linkedin/`

Output del flusso manuale LinkedIn.

#### `data/output/outreach/`

- `attivita_messaggi_mirati.csv`
- `attivita_messaggi_mirati.md`

#### `data/output/research/`

Qui oggi convivono due livelli:

1. batch piccoli e curati
- `attivita_shortlist_outreach_ready.csv`
- `attivita_shortlist_outreach_ready.md`

2. batch totale e filtri operativi
- `clienti_varesotto_outreach_ready.csv`
- `clienti_varesotto_outreach_ready.md`
- `clienti_varesotto_outreach_ok.csv`
- `clienti_varesotto_outreach_parziali_contattabili.csv`
- `clienti_varesotto_outreach_hotlist.csv`
- `clienti_varesotto_outreach_hotlist.md`

### `docs/`

Documentazione di flusso e struttura.

- `STRUTTURA_PROGETTO.md`
- `FLUSSO_OSM.md`
- `FLUSSO_LINKEDIN.md`
- `FLUSSO_RICERCA_ONLINE.md`
- `FLUSSO_MESSAGGI_MIRATI.md`
- `FLUSSO_CHATGPT_DEEP_RESEARCH.md`
- `PROMPT_CHATGPT_DEEP_RESEARCH.md`
- `STRATEGIA_ACQUISIZIONE.md`
- questo file: `RIEPILOGO_PROGETTO.md`

## 5. Pipeline logica completa

### Flusso 1: OSM / Overpass

Scopo: produrre il dataset base delle attivita locali.

Passi:

1. geocodifica provincia e punto di riferimento
2. interroga Overpass per gruppi di categoria
3. normalizza i risultati
4. calcola distanza da Vedano Olona
5. assegna priorita
6. salva `clienti_varesotto.csv`

Perche' e' stato fatto cosi:

- OSM e' gratuito e relativamente strutturato
- permette di partire da una base ampia
- non dipende da scraping diretto di piattaforme review

Limite:

- i dati OSM sono spesso incompleti o ambigui

### Flusso 2: LinkedIn manuale assistito

Scopo: avere un canale alternativo, meno automatico ma utile per certi business.

Passi:

1. generazione link di ricerca per macro-categorie
2. copia/incolla manuale dei risultati in `input.txt`
3. parsing del testo e generazione CSV LinkedIn

Perche' e' stato fatto cosi:

- LinkedIn non e' adatto a scraping semplice e stabile
- per certi business e' piu utile una ricerca manuale assistita

### Flusso 3: Ricerca online best-effort

Scopo: arricchire le aziende con segnali digitali e review.

Passi:

1. parte dal CSV OSM
2. usa OSM esatto quando possibile per comune e indirizzo
3. prova a trovare sito ufficiale e directory coerenti
4. tenta di recuperare rating, review count e testo utile
5. genera una scheda di ricerca

Perche' e' stato fatto cosi:

- serve una fase intermedia prima del messaggio
- molte aziende hanno dati online utili ma sparsi

Limite forte:

- la discovery online non e' totalmente stabile
- molte fonti review hanno anti-bot o dati sporchi

### Flusso 4: Shortlist ChatGPT / Deep Research

Scopo: ridurre il batch e far lavorare meglio ricerca assistita umana / AI.

Passi:

1. selezione dei target piu promettenti
2. generazione CSV leggero
3. generazione template risultati
4. uso di ChatGPT / Deep Research per verifica e arricchimento

Perche' e' stato fatto cosi:

- ChatGPT rende bene su batch piccoli
- non e' realistico usarlo bene su migliaia di righe tutte insieme

### Flusso 5: Messaggi mirati

Scopo: trasformare dati e note in proposte commerciali e bozze di messaggio.

Passi:

1. selezione prospect prioritari
2. sincronizzazione `attivita_insights.csv`
3. lettura dati strutturati + note manuali
4. generazione:
   - punto debole principale
   - leva commerciale
   - proposta mirata
   - messaggio WhatsApp
   - messaggio Email

Scelta importante:

lo script non inventa recensioni o criticita dove non ci sono fonti credibili.

### Flusso 6: CSV totale outreach-ready

Scopo: avere una vista unica commerciale su tutto il dataset.

Passi:

1. parte dal CSV OSM completo
2. ingloba i casi gia arricchiti della shortlist
3. per tutte le altre righe costruisce una base prudente
4. salva un CSV unico con stato, proposta base e note

Perche' e' stato fatto cosi:

- il dataset completo da 6645 righe era ingestibile in forma grezza
- serviva una rappresentazione commerciale unica

### Flusso 7: Hotlist

Scopo: estrarre i lead su cui lavorare davvero.

Passi:

1. separa gli `OK`
2. filtra i `PARZIALI` davvero contattabili
3. genera:
   - file `OK`
   - file `PARZIALI contattabili`
   - `HOTLIST` combinata

Scelta logica:

i `PARZIALI` vengono tenuti solo se hanno:

- priorita `ALTISSIMA` o `ALTA`
- almeno un contatto o sito
- almeno comune o indirizzo utile

## 6. Implementazioni chiave

### 6.1 `paths.py`

Ruolo:

- definire i path canonici
- evitare path hardcoded in tutto il codice
- semplificare output/input per i vari flussi

Questa e' una scelta importante di manutenibilita.

### 6.2 `scripts/_bootstrap.py`

Serve a eseguire gli script senza installare il package.  
Gli entrypoint possono importare da `src/` in modo pulito.

### 6.3 `varesotto_osm.py`

Implementa:

- query per gruppo categoria
- fallback su piu endpoint Overpass
- normalizzazione campi
- classificazione per categoria
- ranking per distanza e opportunita digitale

### 6.4 `online_research.py`

Implementa:

- fetch OSM di supporto
- query online
- scoring dei match
- parsing di directory e fonti verticali
- sintesi review e segnali digitali

Questo e' il modulo piu complesso del progetto lato rete.

### 6.5 `outreach_messaging.py`

Implementa la traduzione tra dati e messaggi:

- gap automatici
- playbook per categoria
- scelta del punto debole
- scelta della proposta commerciale
- generazione bozza messaggio

### 6.6 `outreach_ready_total.py`

Implementa il ponte tra:

- dataset totale OSM
- shortlist arricchita
- output commerciale unico

E' importante perche' evita di avere un piccolo file curato e un grande file inutilizzabile.

### 6.7 `outreach_hotlist.py`

Implementa il filtro operativo finale.  
Serve a non lavorare sulle 6645 righe tutte insieme, ma su un sottoinsieme realistico.

## 7. File oggi piu importanti

Se qualcuno dovesse capire il progetto in poco tempo, i file da leggere per primi sono:

1. `README.md`
2. `src/finder_clienti_varesotto/paths.py`
3. `src/finder_clienti_varesotto/varesotto_osm.py`
4. `src/finder_clienti_varesotto/outreach_messaging.py`
5. `src/finder_clienti_varesotto/outreach_ready_total.py`
6. `src/finder_clienti_varesotto/outreach_hotlist.py`
7. `data/output/osm/clienti_varesotto.csv`
8. `data/output/research/clienti_varesotto_outreach_ready.csv`
9. `data/output/research/clienti_varesotto_outreach_hotlist.csv`

## 8. Dipendenze e ambiente

Dipendenze minime:

- `requests`
- `beautifulsoup4`

Ambienti:

- `.venv` = ambiente consigliato
- `venv` = ambiente legacy, lasciato per compatibilita storica

Scelta pratica:

il progetto e' volutamente leggero lato dipendenze, per restare semplice da far girare.

## 9. Limiti e rischi strutturali

1. Dato di partenza incompleto

Molte attivita nel CSV OSM non hanno:

- comune
- indirizzo
- telefono
- email
- sito

Questo influenza tutto il resto della pipeline.

2. Match ambigui

Nomi generici come `San Rocco`, `Bar`, `Santa Teresa`, `Il Chiosco` possono creare collisioni.

3. Ricerca online instabile

Fonti come Google Maps, Tripadvisor, TheFork, Facebook e motori pubblici possono:

- bloccare il fetch
- cambiare markup
- restituire risultati rumorosi

4. Parte semi-manuale inevitabile

Per alcuni casi il miglior risultato si ottiene solo con:

- shortlist ridotte
- controllo umano
- verifica ChatGPT / Deep Research

5. Doppio livello di output

Esistono output molto curati su pochi casi e output prudenziali sul totale.  
Questo va capito bene per non trattare tutto come se avesse lo stesso livello di affidabilita.

## 10. Stato attuale del progetto

Oggi il progetto e' organizzato come una pipeline commerciale pragmatica:

- il dataset base viene da OSM
- i casi migliori possono essere arricchiti manualmente o con AI
- esiste un CSV totale `outreach-ready`
- esiste una hotlist finale per partire davvero con i contatti

Il progetto quindi non e' piu solo un "finder", ma una base operativa per:

- mappare il territorio
- scegliere i prospect
- prepararli commercialmente
- portarli a messaggio / contatto

## 11. Uso consigliato oggi

Se dovessi usare il progetto nel modo piu sensato oggi:

1. genera o aggiorna il dataset OSM
2. usa il CSV totale `outreach-ready`
3. apri la `hotlist`
4. parti dagli `OK`
5. poi lavora sui `PARZIALI contattabili`
6. usa `attivita_insights.csv` e `genera_messaggi_mirati.py` solo per i casi davvero promettenti

## 12. In sintesi

Questo progetto e' stato progettato per trasformare un territorio e un dataset grezzo in una macchina di selezione commerciale progressiva.

La logica chiave non e' "scrapare tutto", ma:

- raccogliere bene
- separare i livelli di affidabilita
- filtrare i lead utili
- preparare contatti concreti

Questa e' la ragione per cui il progetto e' organizzato in piu flussi e non in un solo script monolitico.
