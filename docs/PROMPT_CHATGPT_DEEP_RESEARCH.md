# Prompt ChatGPT Deep Research

Usa questo prompt dopo aver caricato `attivita_shortlist_chatgpt.csv`.

```text
Ti ho caricato un CSV con una shortlist di attivita locali.

Per ogni riga del CSV:
1. verifica che il match sia corretto usando nome attivita, comune, indirizzo, categoria e OSM URL come contesto
2. trova il sito ufficiale reale, se esiste
3. trova la fonte recensioni principale piu utile e affidabile
4. estrai rating e numero recensioni quando disponibili
5. sintetizza cosa fa davvero l'attivita in modo concreto
6. estrai punti forti ricorrenti e criticita ricorrenti dalle recensioni
7. proponi un angolo commerciale mirato per una proposta di miglioramento digitale / sito / presenza online

Fonti da privilegiare:
- sito ufficiale
- Google Maps
- RestaurantGuru
- Tripadvisor
- TheFork
- Facebook
- Instagram
- PagineGialle
- Virgilio

Regole:
- non inventare dati
- se il match non e' affidabile scrivi DA_VERIFICARE
- non usare directory generiche come fonte ufficiale se non c'e' conferma
- usa testo breve, concreto e operativo
- mantieni sempre il Target ID originale

Restituisci un CSV con ESATTAMENTE queste colonne:

Target ID
Nome Attivita
Comune
Indirizzo
Provincia
Categoria
Sottocategoria
Priorita Distanza
Distanza KM
Ha Sito Web
Opportunita Web
Telefono
Email
Sito Web
OSM URL
Motivo Shortlist
Brief Ricerca
Stato Verifica
Match Confidence
Sito Ufficiale Verificato
Review Fonte Principale
Rating Verificato
Numero Recensioni Verificato
Cosa Fanno Verificato
Punti Forti Ricorrenti
Criticita Ricorrenti
Proposta Mirata
Fonti Verificate
Note Finali

Formato desiderato per alcune colonne:
- Stato Verifica: OK / DA_VERIFICARE / NON_TROVATO
- Match Confidence: ALTA / MEDIA / BASSA
- Punti Forti Ricorrenti: max 3 punti separati da " | "
- Criticita Ricorrenti: max 3 punti separati da " | "
- Fonti Verificate: URL o nomi fonte separati da " | "

Prima di restituire il CSV:
- scarta i falsi positivi
- controlla che rating e numero recensioni siano coerenti con la fonte
- evita duplicati
```

## Variante breve

```text
Analizza questo CSV riga per riga, verifica il match reale dell'attivita, trova sito ufficiale, rating, numero recensioni, punti forti, criticita e proposta mirata. Non inventare dati. Se non sei sicuro scrivi DA_VERIFICARE. Restituisci un CSV con le stesse colonne del template che ti carico.
```
