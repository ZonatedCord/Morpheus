# Flusso Ricerca Online

## Obiettivo

Partire dal CSV delle attivita e costruire una scheda ricerca per ogni azienda, prima ancora di scrivere il messaggio commerciale.

## Cosa cerca lo script

- sito ufficiale
- descrizione attivita
- telefono ed email trovati online
- social collegati dal sito
- directory terze parti con dati strutturati utili
- rating, numero recensioni e sintesi recensioni quando la fonte e' accessibile
- snippet utili per capire cosa fanno e come si presentano

## Comando base

```bash
python3 scripts/ricerca_aziende_online.py --limit 10
```

## Output

- `data/output/research/attivita_ricerca_online.csv`
- `data/output/research/attivita_ricerca_online_merged.csv`
- `data/output/research/attivita_ricerca_online.md`

## Colonne utili nuove

- `Directory Fonte`, `Directory Telefono`, `Directory Indirizzo`, `Directory Sito`
- `Review Fonte`, `Review Rating`, `Review Count`
- `Review Keywords`: temi positivi e critici ricorrenti
- `Review Summary`: estratti recensioni utili per preparare il messaggio
- `Confidenza Match`: stima sintetica di affidabilita'

## Uso corretto

1. Genera la scheda ricerca.
2. Leggi prima `Review Rating`, `Review Count`, `Review Keywords`, `Review Summary`.
3. Poi leggi `Cosa Fanno`, `Snippet Ricerca`, `Link Utili`, `Pagine Terze Parti`.
4. Incrocia `Directory Telefono`, `Directory Indirizzo` e `Sito Ufficiale Trovato`.
5. Verifica i dubbi in `Elementi Da Verificare`.
6. Solo dopo passa alla costruzione del messaggio.

## Limiti

- Dipende dalla rete e dai risultati del motore di ricerca.
- Le fonti tipo `Tripadvisor`, `TheFork`, `Facebook`, `Google Maps` possono bloccare il fetch con anti-bot.
- Le recensioni complete oggi sono piu affidabili su fonti accessibili come `Restaurant Guru`; non tutte le aziende avranno rating e review.
- Va usato a piccoli batch con pausa, per evitare blocchi della SERP.
