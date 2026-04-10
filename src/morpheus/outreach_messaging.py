#!/usr/bin/env python3
"""
Genera analisi commerciali e messaggi mirati per il contatto delle attivita'.

Il flusso e' pensato per lavorare bene con:
- dati strutturati gia' presenti nel CSV OSM
- note e recensioni raccolte manualmente in un file di insights

Lo script non inventa recensioni: se non ci sono note manuali, genera una base
commerciale prudente usando solo segnali oggettivi del dataset.
"""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from .paths import (
    DEFAULT_OSM_OUTPUT,
    DEFAULT_OUTREACH_INSIGHTS,
    DEFAULT_OUTREACH_OUTPUT,
    DEFAULT_OUTREACH_SUMMARY,
    ensure_parent_dir,
    project_relative,
)


PRIORITY_ORDER = {
    "ALTISSIMA": 0,
    "ALTA": 1,
    "MEDIA": 2,
    "BASSA": 3,
    "MOLTO BASSA": 4,
}

INSIGHT_FIELDNAMES = [
    "Nome Attivita",
    "Comune",
    "Categoria",
    "Sottocategoria",
    "Distanza KM",
    "Telefono",
    "Email",
    "Sito Web",
    "Cosa Fanno",
    "Recensioni Positive",
    "Recensioni Critiche",
    "Punti Deboli Osservati",
    "Proposta Preferita",
    "Canale Preferito",
    "Note Libere",
    "Fonte Note",
]

OUTPUT_FIELDNAMES = [
    "Nome Attivita",
    "Comune",
    "Categoria",
    "Sottocategoria",
    "Priorita Distanza",
    "Distanza KM",
    "Telefono",
    "Email",
    "Sito Web",
    "OSM URL",
    "Stato Personalizzazione",
    "Cosa Fanno",
    "Segnali Utili",
    "Punto Debole Principale",
    "Leva Commerciale",
    "Proposta Mirata",
    "Apertura Messaggio",
    "Messaggio WhatsApp",
    "Messaggio Email",
    "Punti Da Verificare",
    "Fonte Note",
    "Recensioni Positive",
    "Recensioni Critiche",
]

REVIEW_THEME_RULES = [
    {
        "name": "menu_listino",
        "label": "menu o listino poco chiaro online",
        "keywords": ("menu", "listino", "prezzi", "piatti", "carta", "trattamenti", "servizi"),
        "proposal": "una pagina mobile con menu, listino o servizi spiegati bene",
        "benefit": "chi vi trova capisce subito cosa fate e cosa puo' chiedere",
    },
    {
        "name": "booking",
        "label": "prenotazione o richiesta info poco fluida",
        "keywords": (
            "prenot",
            "booking",
            "tavolo",
            "appunt",
            "disponibil",
            "riserv",
            "richiesta",
        ),
        "proposal": "un flusso semplice per prenotazioni o richieste via WhatsApp e modulo rapido",
        "benefit": "riduci attrito e fai arrivare piu' contatti pronti",
    },
    {
        "name": "orari_contatti",
        "label": "orari e contatti poco immediati",
        "keywords": ("orari", "aperto", "chiuso", "telefono", "contatto", "chiamare", "numero"),
        "proposal": "una scheda chiara con orari, mappa e contatti aggiornati",
        "benefit": "eviti chiamate perse e domande ripetitive",
    },
    {
        "name": "gallery",
        "label": "presentazione visiva debole o poco aggiornata",
        "keywords": ("foto", "immagini", "ambiente", "camera", "camere", "locale", "galleria"),
        "proposal": "una vetrina visiva semplice con foto, punti forti e call to action",
        "benefit": "aumenti fiducia e invogli il primo contatto",
    },
    {
        "name": "delivery_order",
        "label": "ordine, asporto o consegna poco chiari",
        "keywords": ("asporto", "delivery", "consegna", "ordine", "ordinare"),
        "proposal": "una pagina rapida per ordini, asporto o istruzioni operative",
        "benefit": "rendi piu' facile l'acquisto immediato",
    },
    {
        "name": "preventivo",
        "label": "richiesta preventivo o spiegazione servizi poco semplice",
        "keywords": ("preventivo", "sopralluogo", "intervento", "riparazione", "urgenza", "stima"),
        "proposal": "una pagina servizi con richiesta preventivo guidata",
        "benefit": "qualifichi meglio i contatti e riduci messaggi dispersivi",
    },
    {
        "name": "attesa",
        "label": "gestione attese o code da alleggerire",
        "keywords": ("attesa", "coda", "tempo", "lento", "aspettare", "ritardo"),
        "proposal": "un sistema semplice per prenotare, chiedere disponibilita o preparare la visita",
        "benefit": "sposti parte del carico informativo prima del contatto diretto",
    },
    {
        "name": "trust",
        "label": "mancano elementi di fiducia e prova sociale",
        "keywords": ("professional", "cortesia", "competenza", "consigliato", "serieta", "accoglienza"),
        "proposal": "una pagina essenziale che valorizzi punti forti, casi reali e rassicurazioni utili",
        "benefit": "chi vi scopre ha piu' motivi per scegliere voi",
    },
    {
        "name": "location",
        "label": "raggiungibilita o informazioni pratiche non immediate",
        "keywords": ("parcheggio", "indirizzo", "dove", "raggiungere", "zona", "mappa"),
        "proposal": "una pagina con indicazioni pratiche, parcheggio e contatti immediati",
        "benefit": "abbassi l'incertezza prima della visita",
    },
]

CATEGORY_PLAYBOOK = {
    "Ristorazione": {
        "focus": "un locale food dove le persone vogliono capire subito menu, atmosfera e contatti",
        "lever": "rendere immediati menu, orari, mappa e prenotazione",
        "proposal": "una mini presenza web con menu, orari, mappa e bottone WhatsApp",
        "verify": "controllare se esiste gia' un menu social o una pagina Google ben aggiornata",
    },
    "Beauty & Benessere": {
        "focus": "un'attivita' che vive di fiducia, servizi chiari e appuntamenti veloci",
        "lever": "far vedere trattamenti, prezzi indicativi e prenotazione",
        "proposal": "una pagina servizi con listino essenziale, gallery e richiesta appuntamento",
        "verify": "verificare se prenotano gia' da Instagram o WhatsApp",
    },
    "Sanita'": {
        "focus": "un servizio dove contano chiarezza, orari e informazioni pratiche",
        "lever": "ridurre dubbi su servizi, disponibilita' e contatti",
        "proposal": "una pagina informativa con orari, servizi, mappa e contatto rapido",
        "verify": "controllare precisione di orari, turni e servizi realmente offerti",
    },
    "Ospitalita'": {
        "focus": "una struttura dove contano fiducia, foto, disponibilita' e richiesta rapida",
        "lever": "portare piu' richieste dirette senza passare solo da portali",
        "proposal": "una mini presenza con camere, servizi, foto e richiesta disponibilita'",
        "verify": "capire se dipendono gia' da Booking o portali simili",
    },
    "Fitness & Sport": {
        "focus": "un'attivita' che deve spiegare corsi, orari e prova iniziale",
        "lever": "trasformare curiosita' in richiesta prova o primo contatto",
        "proposal": "una pagina corsi con orari, prova gratuita e form rapido",
        "verify": "controllare se il calendario e' gia' gestito via social o app esterna",
    },
    "Servizi Professionali": {
        "focus": "un servizio dove contano chiarezza, competenza e richiesta contatto",
        "lever": "far capire subito servizi, casi d'uso e modalita' di contatto",
        "proposal": "una pagina servizi chiara con call to action e contatto qualificato",
        "verify": "verificare se hanno gia' sito ma poco orientato al lead",
    },
    "Artigiani": {
        "focus": "un'attivita' che puo' convertire meglio se spiega servizi e tempi di risposta",
        "lever": "facilitare richiesta preventivo e fiducia iniziale",
        "proposal": "una scheda servizi con portfolio, zona coperta e preventivo rapido",
        "verify": "controllare le aree servite e il tipo di intervento principale",
    },
    "Negozi": {
        "focus": "un punto vendita che deve farsi trovare e spiegare cosa offre",
        "lever": "mostrare assortimento, utilita' pratica e contatto veloce",
        "proposal": "una pagina vetrina con categorie prodotto, mappa e contatto rapido",
        "verify": "capire se il negozio lavora su brand specifici o servizi aggiuntivi",
    },
}

SUBCATEGORY_FOCUS = {
    "Bar": "un bar dove chi cerca vuole capire al volo dove siete, cosa trovano e come contattarvi",
    "Caffetteria": "una caffetteria dove contano atmosfera, orari e punto di riferimento locale",
    "Ristorante": "un ristorante dove menu, orari e prenotazione devono essere immediati",
    "Pizzeria": "una pizzeria dove menu, asporto e contatto rapido sono decisivi",
    "Gelateria": "una gelateria dove gusti, orari e posizione fanno la differenza",
    "Pub": "un pub dove eventi, atmosfera e contatto rapido aiutano il passaparola",
    "Parrucchiere": "un salone dove trattamenti, stile e appuntamenti devono essere chiari",
    "Centro Estetico": "un centro estetico dove listino, servizi e fiducia contano molto",
    "Farmacia": "una farmacia dove servizi, orari e indicazioni pratiche devono essere chiari",
    "Hotel": "una struttura dove camere, servizi e richiesta diretta devono essere semplici",
    "Affittacamere": "una struttura ricettiva dove foto, contatto diretto e disponibilita' contano",
    "Centro Sportivo": "un centro sportivo dove orari, corsi e richiesta prova devono essere veloci",
    "Agenzia Immobiliare": "un servizio dove fiducia e chiarezza dell'offerta guidano il contatto",
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_value.lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def clean_value(value: str | None) -> str:
    if value is None:
        return ""
    cleaned = value.strip()
    if cleaned in {"", "N/D"}:
        return ""
    return cleaned


def row_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = clean_value(row.get(key))
        if value:
            return value
    return ""


def row_key(name: str, city: str) -> str:
    return f"{normalize_text(name)}|{normalize_text(city)}"


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    output_path = ensure_parent_dir(path)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sort_candidates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            PRIORITY_ORDER.get(row.get("Priorita'", ""), 99),
            float(row.get("Distanza da Vedano Olona (km)", "9999") or "9999"),
            normalize_text(row.get("Nome Attivita'", "")),
        ),
    )


def select_candidates(
    rows: list[dict[str, str]],
    limit: int,
    include_with_website: bool,
) -> list[dict[str, str]]:
    filtered = []
    for row in sort_candidates(rows):
        if not include_with_website and row.get("Ha Sito Web") != "NO":
            continue
        filtered.append(row)
        if limit > 0 and len(filtered) >= limit:
            break
    return filtered


def detect_review_themes(text: str) -> list[dict[str, str]]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    themes = []
    for rule in REVIEW_THEME_RULES:
        if any(keyword in normalized for keyword in rule["keywords"]):
            themes.append(rule)
    return themes


def category_playbook(row: dict[str, str]) -> dict[str, str]:
    category = row_value(row, "Categoria")
    subtype = row_value(row, "Sottocategoria")
    base = CATEGORY_PLAYBOOK.get(category, CATEGORY_PLAYBOOK["Negozi"]).copy()
    if subtype in SUBCATEGORY_FOCUS:
        base["focus"] = SUBCATEGORY_FOCUS[subtype]
    return base


def automatic_gaps(row: dict[str, str]) -> list[str]:
    gaps = []
    if row.get("Ha Sito Web") == "NO":
        gaps.append("non risulta un sito o una pagina proprietaria dove spiegare bene l'offerta")
    if not row_value(row, "Email"):
        gaps.append("non risulta un canale email chiaro")
    if not row_value(row, "Telefono"):
        gaps.append("non risulta un contatto rapido immediato")
    if not row_value(row, "Indirizzo") or not row_value(row, "Comune"):
        gaps.append("le informazioni pratiche online sembrano incomplete")
    return gaps


def summarize_positive(insight: dict[str, str]) -> str:
    positive = row_value(insight, "Recensioni Positive")
    if positive:
        return positive
    return ""


def business_focus(row: dict[str, str], insight: dict[str, str]) -> str:
    custom = row_value(insight, "Cosa Fanno")
    if custom:
        return custom
    playbook = category_playbook(row)
    return playbook["focus"]


def choose_primary_issue(
    row: dict[str, str],
    insight: dict[str, str],
    themes: list[dict[str, str]],
) -> str:
    manual = row_value(insight, "Punti Deboli Osservati")
    if manual:
        return manual
    if themes:
        return themes[0]["label"]
    gaps = automatic_gaps(row)
    if gaps:
        return gaps[0]
    return "va capita meglio la presenza digitale attuale prima del contatto"


def choose_proposal(
    row: dict[str, str],
    insight: dict[str, str],
    themes: list[dict[str, str]],
) -> str:
    manual = row_value(insight, "Proposta Preferita")
    if manual:
        return manual
    if themes:
        return themes[0]["proposal"]
    return category_playbook(row)["proposal"]


def commercial_lever(
    row: dict[str, str],
    themes: list[dict[str, str]],
) -> str:
    if themes:
        return themes[0]["benefit"]
    return category_playbook(row)["lever"]


def personalization_state(insight: dict[str, str]) -> str:
    if row_value(insight, "Recensioni Positive", "Recensioni Critiche", "Punti Deboli Osservati", "Cosa Fanno"):
        return "ARRICCHITA_CON_NOTE"
    return "BASE_DA_DATI"


def useful_signals(
    row: dict[str, str],
    insight: dict[str, str],
    themes: list[dict[str, str]],
) -> str:
    parts = []
    positive = summarize_positive(insight)
    if positive:
        parts.append(f"punto forte emerso: {positive}")
    critical = row_value(insight, "Recensioni Critiche")
    if critical:
        parts.append(f"criticita osservata: {critical}")
    if themes:
        parts.append(f"tema prioritario: {themes[0]['label']}")
    if row.get("Ha Sito Web") == "NO":
        parts.append("assenza sito")
    if not row_value(row, "Telefono"):
        parts.append("telefono non presente nel dataset")
    if not row_value(row, "Email"):
        parts.append("email non presente nel dataset")
    return "; ".join(parts)


def points_to_verify(row: dict[str, str], insight: dict[str, str]) -> str:
    checks = []
    playbook = category_playbook(row)
    checks.append(playbook["verify"])
    if row_value(insight, "Note Libere"):
        checks.append(f"rileggere note: {row_value(insight, 'Note Libere')}")
    if not row_value(row, "Comune"):
        checks.append("verificare comune corretto prima del contatto")
    return "; ".join(checks)


def message_opening(row: dict[str, str], insight: dict[str, str], focus: str) -> str:
    name = row_value(row, "Nome Attivita'", "Nome Attivita")
    city = row_value(row, "Comune") or "zona Varese"
    positive = summarize_positive(insight)

    if positive:
        return (
            f"Ho visto {name} a {city} e dalle note emerge che viene apprezzato soprattutto {positive}."
        )
    return f"Ho visto {name} a {city} e il tipo di proposta che portate sul territorio."


def inline_clause(text: str) -> str:
    if not text:
        return text
    return text[:1].lower() + text[1:]


def whatsapp_message(
    row: dict[str, str],
    opening: str,
    issue: str,
    proposal: str,
    lever: str,
    focus: str,
) -> str:
    name = row_value(row, "Nome Attivita'", "Nome Attivita")
    return (
        f"Ciao, {inline_clause(opening)} Mi sembra che oggi il punto da migliorare sia {issue}. "
        f"Secondo me per {name} avrebbe senso {proposal}, cosi da {lever}. "
        "Se vuoi ti preparo un esempio pratico, molto semplice, da vedere in 2 minuti."
    )


def email_message(
    row: dict[str, str],
    opening: str,
    issue: str,
    proposal: str,
    lever: str,
    focus: str,
) -> str:
    name = row_value(row, "Nome Attivita'", "Nome Attivita")
    return (
        f"{opening}\n\n"
        f"Analizzando la presenza digitale di {name}, il margine principale mi sembra {issue}. "
        f"Per questo proporrei {proposal}, cosi da {lever}.\n\n"
        "Se ti va, posso preparare una bozza mirata sul vostro caso e fartela vedere senza impegno."
    )


def sync_insights_template(
    candidates: list[dict[str, str]],
    insights_path: Path,
) -> dict[str, dict[str, str]]:
    existing_rows = load_csv(insights_path) if insights_path.exists() else []
    existing_map = {
        row_key(row_value(row, "Nome Attivita"), row_value(row, "Comune")): row for row in existing_rows
    }

    merged_rows = []
    seen_keys = set()
    for row in candidates:
        name = row_value(row, "Nome Attivita'")
        city = row_value(row, "Comune")
        key = row_key(name, city)
        seen_keys.add(key)
        existing = existing_map.get(key, {})
        merged_rows.append(
            {
                "Nome Attivita": name,
                "Comune": city or "N/D",
                "Categoria": row_value(row, "Categoria"),
                "Sottocategoria": row_value(row, "Sottocategoria"),
                "Distanza KM": row_value(row, "Distanza da Vedano Olona (km)"),
                "Telefono": row_value(row, "Telefono") or "N/D",
                "Email": row_value(row, "Email") or "N/D",
                "Sito Web": row_value(row, "Sito Web") or "N/D",
                "Cosa Fanno": row_value(existing, "Cosa Fanno"),
                "Recensioni Positive": row_value(existing, "Recensioni Positive"),
                "Recensioni Critiche": row_value(existing, "Recensioni Critiche"),
                "Punti Deboli Osservati": row_value(existing, "Punti Deboli Osservati"),
                "Proposta Preferita": row_value(existing, "Proposta Preferita"),
                "Canale Preferito": row_value(existing, "Canale Preferito"),
                "Note Libere": row_value(existing, "Note Libere"),
                "Fonte Note": row_value(existing, "Fonte Note"),
            }
        )

    for key, existing in existing_map.items():
        if key in seen_keys:
            continue
        merged_rows.append(
            {
                "Nome Attivita": row_value(existing, "Nome Attivita") or "N/D",
                "Comune": row_value(existing, "Comune") or "N/D",
                "Categoria": row_value(existing, "Categoria") or "N/D",
                "Sottocategoria": row_value(existing, "Sottocategoria") or "N/D",
                "Distanza KM": row_value(existing, "Distanza KM") or "N/D",
                "Telefono": row_value(existing, "Telefono") or "N/D",
                "Email": row_value(existing, "Email") or "N/D",
                "Sito Web": row_value(existing, "Sito Web") or "N/D",
                "Cosa Fanno": row_value(existing, "Cosa Fanno"),
                "Recensioni Positive": row_value(existing, "Recensioni Positive"),
                "Recensioni Critiche": row_value(existing, "Recensioni Critiche"),
                "Punti Deboli Osservati": row_value(existing, "Punti Deboli Osservati"),
                "Proposta Preferita": row_value(existing, "Proposta Preferita"),
                "Canale Preferito": row_value(existing, "Canale Preferito"),
                "Note Libere": row_value(existing, "Note Libere"),
                "Fonte Note": row_value(existing, "Fonte Note"),
            }
        )

    write_csv(insights_path, INSIGHT_FIELDNAMES, merged_rows)
    return {
        row_key(row_value(row, "Nome Attivita"), row_value(row, "Comune")): row for row in merged_rows
    }


def build_output_rows(
    candidates: list[dict[str, str]],
    insights_map: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    output_rows = []
    for row in candidates:
        name = row_value(row, "Nome Attivita'")
        city = row_value(row, "Comune")
        insight = insights_map.get(row_key(name, city), {})
        text_blob = " ".join(
            [
                row_value(insight, "Recensioni Positive"),
                row_value(insight, "Recensioni Critiche"),
                row_value(insight, "Punti Deboli Osservati"),
                row_value(insight, "Note Libere"),
            ]
        )
        themes = detect_review_themes(text_blob)
        focus = business_focus(row, insight)
        issue = choose_primary_issue(row, insight, themes)
        proposal = choose_proposal(row, insight, themes)
        lever = commercial_lever(row, themes)
        opening = message_opening(row, insight, focus)

        output_rows.append(
            {
                "Nome Attivita": name,
                "Comune": city or "N/D",
                "Categoria": row_value(row, "Categoria"),
                "Sottocategoria": row_value(row, "Sottocategoria"),
                "Priorita Distanza": row_value(row, "Priorita'"),
                "Distanza KM": row_value(row, "Distanza da Vedano Olona (km)"),
                "Telefono": row_value(row, "Telefono") or "N/D",
                "Email": row_value(row, "Email") or "N/D",
                "Sito Web": row_value(row, "Sito Web") or "N/D",
                "OSM URL": row_value(row, "OSM URL") or "N/D",
                "Stato Personalizzazione": personalization_state(insight),
                "Cosa Fanno": focus,
                "Segnali Utili": useful_signals(row, insight, themes),
                "Punto Debole Principale": issue,
                "Leva Commerciale": lever,
                "Proposta Mirata": proposal,
                "Apertura Messaggio": opening,
                "Messaggio WhatsApp": whatsapp_message(row, opening, issue, proposal, lever, focus),
                "Messaggio Email": email_message(row, opening, issue, proposal, lever, focus),
                "Punti Da Verificare": points_to_verify(row, insight),
                "Fonte Note": row_value(insight, "Fonte Note"),
                "Recensioni Positive": row_value(insight, "Recensioni Positive"),
                "Recensioni Critiche": row_value(insight, "Recensioni Critiche"),
            }
        )
    return output_rows


def write_summary(
    path: Path,
    output_rows: list[dict[str, str]],
    insights_path: Path,
) -> None:
    status_counter = Counter(row["Stato Personalizzazione"] for row in output_rows)
    category_counter = Counter(row["Categoria"] for row in output_rows)

    lines = [
        "# Analisi Messaggi Mirati",
        "",
        f"- Totale attivita analizzate: {len(output_rows)}",
        f"- Base dati usata: `{project_relative(DEFAULT_OSM_OUTPUT)}`",
        f"- File insights sincronizzato: `{project_relative(insights_path)}`",
        f"- Attivita con note/recensioni manuali: {status_counter.get('ARRICCHITA_CON_NOTE', 0)}",
        f"- Attivita solo con dati strutturati: {status_counter.get('BASE_DA_DATI', 0)}",
        "",
        "## Categorie piu presenti",
        "",
    ]

    for category, count in category_counter.most_common(8):
        lines.append(f"- {category}: {count}")

    lines.extend(
        [
            "",
            "## Come usarlo",
            "",
            "- Compila o arricchisci il file insights con note reali, recensioni e osservazioni.",
            "- Riesegui lo script per rigenerare i messaggi con una base piu mirata.",
            "- Prima di contattare, verifica sempre che le osservazioni siano corrette e attuali.",
        ]
    )

    summary_path = ensure_parent_dir(path)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera analisi e messaggi mirati a partire dal CSV delle attivita."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_OSM_OUTPUT),
        help=f"CSV sorgente delle attivita. Default: {project_relative(DEFAULT_OSM_OUTPUT)}.",
    )
    parser.add_argument(
        "--insights",
        default=str(DEFAULT_OUTREACH_INSIGHTS),
        help=(
            "CSV con note manuali, recensioni e osservazioni. "
            f"Default: {project_relative(DEFAULT_OUTREACH_INSIGHTS)}."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTREACH_OUTPUT),
        help=f"CSV finale con analisi e messaggi. Default: {project_relative(DEFAULT_OUTREACH_OUTPUT)}.",
    )
    parser.add_argument(
        "--summary",
        default=str(DEFAULT_OUTREACH_SUMMARY),
        help=f"Report markdown finale. Default: {project_relative(DEFAULT_OUTREACH_SUMMARY)}.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Numero massimo di attivita da analizzare. 0 = nessun limite. Default: 50.",
    )
    parser.add_argument(
        "--include-with-website",
        action="store_true",
        help="Include anche attivita che hanno gia' un sito web.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    insights_path = Path(args.insights)
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    rows = load_csv(input_path)
    candidates = select_candidates(
        rows=rows,
        limit=args.limit,
        include_with_website=args.include_with_website,
    )
    insights_map = sync_insights_template(candidates, insights_path)
    output_rows = build_output_rows(candidates, insights_map)

    write_csv(output_path, OUTPUT_FIELDNAMES, output_rows)
    write_summary(summary_path, output_rows, insights_path)

    print("\nANALISI MESSAGGI MIRATI")
    print("=" * 72)
    print(f"Attivita analizzate: {len(output_rows)}")
    print(f"Insights sincronizzati: {project_relative(insights_path)}")
    print(f"Output CSV: {project_relative(output_path)}")
    print(f"Report markdown: {project_relative(summary_path)}")
    print(
        "Nota: le recensioni vengono usate solo se presenti nel file insights; "
        "altrimenti il messaggio resta prudente e basato sui dati oggettivi."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
