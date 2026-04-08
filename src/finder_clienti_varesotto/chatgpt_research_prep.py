#!/usr/bin/env python3
"""
Prepara una shortlist CSV da dare a ChatGPT / Deep Research.

Genera:
- un CSV leggero da caricare nel browser/agente
- un template CSV con le colonne risultato da riempire
- un report markdown con istruzioni operative
"""

from __future__ import annotations

import argparse
import csv
import unicodedata
from collections import Counter
from pathlib import Path

from .paths import (
    DEFAULT_DEEP_RESEARCH_SHORTLIST,
    DEFAULT_DEEP_RESEARCH_SUMMARY,
    DEFAULT_DEEP_RESEARCH_TEMPLATE,
    DEFAULT_OSM_OUTPUT,
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

REVIEW_FRIENDLY_CATEGORY_ORDER = {
    "Ristorazione": 0,
    "Beauty & Benessere": 1,
    "Ospitalita'": 2,
    "Sanita'": 3,
    "Fitness & Sport": 4,
    "Negozi": 5,
    "Servizi Professionali": 6,
    "Artigiani": 7,
}

SHORTLIST_FIELDNAMES = [
    "Target ID",
    "Nome Attivita",
    "Comune",
    "Indirizzo",
    "Provincia",
    "Categoria",
    "Sottocategoria",
    "Priorita Distanza",
    "Distanza KM",
    "Ha Sito Web",
    "Opportunita Web",
    "Telefono",
    "Email",
    "Sito Web",
    "OSM URL",
    "Motivo Shortlist",
    "Brief Ricerca",
]

RESULT_FIELDNAMES = [
    "Stato Verifica",
    "Match Confidence",
    "Sito Ufficiale Verificato",
    "Review Fonte Principale",
    "Rating Verificato",
    "Numero Recensioni Verificato",
    "Cosa Fanno Verificato",
    "Punti Forti Ricorrenti",
    "Criticita Ricorrenti",
    "Proposta Mirata",
    "Fonti Verificate",
    "Note Finali",
]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_value.lower().strip()
    return " ".join(lowered.split())


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    output_path = ensure_parent_dir(path)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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


def review_brief(row: dict[str, str]) -> str:
    category = row_value(row, "Categoria")
    subtype = row_value(row, "Sottocategoria")
    common = [
        "verifica il match con nome, comune e indirizzo",
        "trova sito ufficiale e social reali",
        "trova rating, numero recensioni e fonte recensioni principale",
        "sintetizza cosa fa davvero l'attivita",
        "estrai punti forti, criticita e un angolo commerciale concreto",
    ]

    if category == "Ristorazione":
        specific = [
            "cerca menu, fascia prezzo, servizio, atmosfera, tempi di attesa",
            "usa soprattutto Google Maps, RestaurantGuru, Tripadvisor, TheFork e sito ufficiale",
        ]
    elif category == "Beauty & Benessere":
        specific = [
            "cerca servizi reali, recensioni su puntualita, risultati, prezzo e accoglienza",
            "usa sito ufficiale, Google Maps, Facebook e Instagram quando servono",
        ]
    elif category == "Sanita'":
        specific = [
            "cerca servizi reali, orari, recensioni su professionalita, tempi e chiarezza",
            "usa sito ufficiale, Google Maps e directory affidabili solo come supporto",
        ]
    else:
        specific = [
            f"conferma cosa fa davvero come {subtype or category}",
            "usa sito ufficiale, Google Maps e directory locali solo se coerenti",
        ]

    return "; ".join(common + specific)


def shortlist_reason(row: dict[str, str]) -> str:
    reasons = []
    if row.get("Ha Sito Web") == "NO":
        reasons.append("senza sito")
    opportunity = row_value(row, "Opportunita' Web")
    if opportunity:
        reasons.append(f"opportunita web {opportunity.lower()}")
    if row_value(row, "Categoria") in {"Ristorazione", "Beauty & Benessere", "Ospitalita'", "Sanita'"}:
        reasons.append("categoria adatta a ricerca recensioni")
    priority = row_value(row, "Priorita'")
    if priority:
        reasons.append(f"priorita {priority.lower()}")
    distance = row_value(row, "Distanza da Vedano Olona (km)")
    if distance:
        reasons.append(f"distanza {distance} km")
    return " | ".join(reasons[:4])


def candidate_sort_key(row: dict[str, str]) -> tuple[float, int, int, float, str]:
    priority_score = PRIORITY_ORDER.get(row.get("Priorita'", ""), 99)
    category_score = REVIEW_FRIENDLY_CATEGORY_ORDER.get(row.get("Categoria", ""), 99)
    distance = float(row.get("Distanza da Vedano Olona (km)", "9999") or "9999")
    missing_site_penalty = 0 if row.get("Ha Sito Web") == "NO" else 1
    name = normalize_text(row.get("Nome Attivita'", ""))
    return (missing_site_penalty, priority_score, category_score, distance, name)


def build_shortlist_rows(
    source_rows: list[dict[str, str]],
    limit: int,
    include_with_website: bool,
) -> list[dict[str, str]]:
    candidates = []
    for row in sorted(source_rows, key=candidate_sort_key):
        if not include_with_website and row.get("Ha Sito Web") != "NO":
            continue
        candidates.append(row)
        if limit > 0 and len(candidates) >= limit:
            break

    shortlist_rows = []
    for index, row in enumerate(candidates, start=1):
        shortlist_rows.append(
            {
                "Target ID": f"DR-{index:03d}",
                "Nome Attivita": row_value(row, "Nome Attivita'"),
                "Comune": row_value(row, "Comune") or "N/D",
                "Indirizzo": row_value(row, "Indirizzo") or "N/D",
                "Provincia": row_value(row, "Provincia") or "N/D",
                "Categoria": row_value(row, "Categoria") or "N/D",
                "Sottocategoria": row_value(row, "Sottocategoria") or "N/D",
                "Priorita Distanza": row_value(row, "Priorita'") or "N/D",
                "Distanza KM": row_value(row, "Distanza da Vedano Olona (km)") or "N/D",
                "Ha Sito Web": row_value(row, "Ha Sito Web") or "N/D",
                "Opportunita Web": row_value(row, "Opportunita' Web") or "N/D",
                "Telefono": row_value(row, "Telefono") or "N/D",
                "Email": row_value(row, "Email") or "N/D",
                "Sito Web": row_value(row, "Sito Web") or "N/D",
                "OSM URL": row_value(row, "OSM URL") or "N/D",
                "Motivo Shortlist": shortlist_reason(row),
                "Brief Ricerca": review_brief(row),
            }
        )
    return shortlist_rows


def build_template_rows(shortlist_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for row in shortlist_rows:
        template_row = dict(row)
        for field in RESULT_FIELDNAMES:
            template_row[field] = ""
        rows.append(template_row)
    return rows


def write_summary(
    path: Path,
    shortlist_rows: list[dict[str, str]],
    shortlist_output: Path,
    template_output: Path,
    include_with_website: bool,
) -> None:
    categories = Counter(row["Categoria"] for row in shortlist_rows)
    missing_site = sum(1 for row in shortlist_rows if row["Ha Sito Web"] == "NO")

    lines = [
        "# Shortlist ChatGPT Deep Research",
        "",
        f"- Attivita in shortlist: {len(shortlist_rows)}",
        f"- Attivita senza sito: {missing_site}",
        f"- Include attivita con sito gia presente: {'SI' if include_with_website else 'NO'}",
        f"- CSV da caricare in ChatGPT: `{project_relative(shortlist_output)}`",
        f"- Template risultati: `{project_relative(template_output)}`",
        "",
        "## Categorie nel batch",
        "",
    ]
    for category, count in categories.most_common():
        lines.append(f"- {category}: {count}")

    lines.extend(
        [
            "",
            "## Uso consigliato",
            "",
            "1. Carica il CSV shortlist in ChatGPT Deep Research / agent mode.",
            "2. Usa il prompt dedicato in `docs/PROMPT_CHATGPT_DEEP_RESEARCH.md`.",
            "3. Lavora per batch piccoli, idealmente 15-30 attivita alla volta.",
            "4. Chiedi un output CSV con le stesse colonne del template.",
            "5. Reimporta poi i risultati nel flusso commerciale.",
        ]
    )

    ensure_parent_dir(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepara una shortlist CSV da dare a ChatGPT / Deep Research."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_OSM_OUTPUT),
        help=f"CSV sorgente. Default: {project_relative(DEFAULT_OSM_OUTPUT)}.",
    )
    parser.add_argument(
        "--shortlist-output",
        default=str(DEFAULT_DEEP_RESEARCH_SHORTLIST),
        help=f"CSV shortlist da caricare. Default: {project_relative(DEFAULT_DEEP_RESEARCH_SHORTLIST)}.",
    )
    parser.add_argument(
        "--template-output",
        default=str(DEFAULT_DEEP_RESEARCH_TEMPLATE),
        help=f"Template risultati. Default: {project_relative(DEFAULT_DEEP_RESEARCH_TEMPLATE)}.",
    )
    parser.add_argument(
        "--summary",
        default=str(DEFAULT_DEEP_RESEARCH_SUMMARY),
        help=f"Riepilogo markdown. Default: {project_relative(DEFAULT_DEEP_RESEARCH_SUMMARY)}.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Numero massimo di attivita in shortlist. Default: 30.",
    )
    parser.add_argument(
        "--include-with-website",
        action="store_true",
        help="Include anche attivita che hanno gia un sito nel CSV base.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    shortlist_output = Path(args.shortlist_output)
    template_output = Path(args.template_output)
    summary_path = Path(args.summary)

    source_rows = load_csv(input_path)
    shortlist_rows = build_shortlist_rows(
        source_rows=source_rows,
        limit=args.limit,
        include_with_website=args.include_with_website,
    )
    template_rows = build_template_rows(shortlist_rows)

    write_csv(shortlist_output, SHORTLIST_FIELDNAMES, shortlist_rows)
    write_csv(template_output, SHORTLIST_FIELDNAMES + RESULT_FIELDNAMES, template_rows)
    write_summary(
        path=summary_path,
        shortlist_rows=shortlist_rows,
        shortlist_output=shortlist_output,
        template_output=template_output,
        include_with_website=args.include_with_website,
    )

    print("\nSHORTLIST CHATGPT PRONTA")
    print("=" * 72)
    print(f"Attivita in shortlist: {len(shortlist_rows)}")
    print(f"CSV shortlist: {project_relative(shortlist_output)}")
    print(f"Template risultati: {project_relative(template_output)}")
    print(f"Report markdown: {project_relative(summary_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
