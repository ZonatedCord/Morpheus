#!/usr/bin/env python3
"""
Genera un CSV outreach-ready sull'intero dataset OSM.

Strategia:
- fonde dentro i casi gia' arricchiti della shortlist
- per tutte le altre righe crea una base utile e coerente
- non inventa recensioni dove non esistono
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from .outreach_messaging import (
    automatic_gaps,
    business_focus,
    category_playbook,
    choose_primary_issue,
    choose_proposal,
    commercial_lever,
    load_csv,
    points_to_verify,
    row_value,
)
from .paths import (
    DEFAULT_DEEP_RESEARCH_SHORTLIST,
    DEFAULT_OSM_OUTPUT,
    DEFAULT_SHORTLIST_OUTREACH_READY,
    DEFAULT_TOTAL_OUTREACH_READY,
    DEFAULT_TOTAL_OUTREACH_READY_SUMMARY,
    ensure_parent_dir,
    project_relative,
)


OUTPUT_FIELDNAMES = [
    "Record ID",
    "Nome Attivita",
    "Priorita Distanza",
    "Distanza KM",
    "Categoria",
    "Sottocategoria",
    "Comune CSV",
    "Indirizzo CSV",
    "Telefono CSV",
    "Email CSV",
    "Sito CSV",
    "OSM URL",
    "Stato",
    "Comune Verificato",
    "Indirizzo Verificato",
    "Categoria Verificata",
    "Telefono",
    "Email",
    "Sito",
    "Fonte Recensioni Principale",
    "Rating Principale",
    "Numero Recensioni Principale",
    "Fonte Recensioni Secondaria",
    "Rating Secondaria",
    "Numero Recensioni Secondaria",
    "Cosa Fanno",
    "Punti Forti",
    "Criticita",
    "Proposta Mirata Base",
    "Note",
    "Fonti",
]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    destination = ensure_parent_dir(path)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, str]], manual_rows: int) -> None:
    counts = Counter(row["Stato"] for row in rows)
    lines = [
        "# CSV Totale Outreach Ready",
        "",
        f"- Righe totali: {len(rows)}",
        f"- Righe fuse dalla shortlist arricchita: {manual_rows}",
        f"- OK: {counts.get('OK', 0)}",
        f"- PARZIALE: {counts.get('PARZIALE', 0)}",
        f"- DA_VERIFICARE: {counts.get('DA_VERIFICARE', 0)}",
        "",
        "## Logica",
        "",
        "- Le attivita' della shortlist gia' curate mantengono i dati ricchi.",
        "- Tutte le altre righe ricevono una base commerciale prudente dai dati OSM.",
        "- Nessuna recensione viene inventata dove non ci sono fonti solide.",
        "",
        f"File generato: `{project_relative(DEFAULT_TOTAL_OUTREACH_READY)}`",
    ]
    destination = ensure_parent_dir(path)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def shortlist_enriched_by_osm(
    shortlist_input_rows: list[dict[str, str]],
    shortlist_ready_rows: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    ready_by_target = {row["Target ID"]: row for row in shortlist_ready_rows}
    enriched_by_osm: dict[str, dict[str, str]] = {}
    for shortlist_row in shortlist_input_rows:
        target_id = shortlist_row.get("Target ID", "")
        osm_url = row_value(shortlist_row, "OSM URL")
        ready = ready_by_target.get(target_id)
        if osm_url and ready:
            enriched_by_osm[osm_url] = ready
    return enriched_by_osm


def record_id(index: int) -> str:
    return f"CV-{index:05d}"


def verified_category(row: dict[str, str]) -> str:
    subtype = row_value(row, "Sottocategoria")
    category = row_value(row, "Categoria")
    return " / ".join(part for part in [subtype, category] if part) or "N/D"


def default_state(row: dict[str, str]) -> str:
    if not any(
        [
            row_value(row, "Comune"),
            row_value(row, "Indirizzo"),
            row_value(row, "Telefono"),
            row_value(row, "Email"),
            row_value(row, "Sito Web"),
        ]
    ):
        return "DA_VERIFICARE"
    return "PARZIALE"


def default_strengths(row: dict[str, str]) -> str:
    strengths = []
    if row_value(row, "Sito Web"):
        strengths.append("sito gia presente")
    if row_value(row, "Telefono"):
        strengths.append("telefono disponibile")
    if row_value(row, "Email"):
        strengths.append("email disponibile")
    if row_value(row, "Comune") and row_value(row, "Indirizzo"):
        strengths.append("anagrafica pratica gia presente")
    if not strengths:
        strengths.append("lead locale presente nel dataset OSM")
    return "; ".join(strengths[:3])


def empty_insight() -> dict[str, str]:
    return {}


def default_business_summary(row: dict[str, str]) -> str:
    focus = business_focus(row, empty_insight())
    city = row_value(row, "Comune") or "zona Varese"
    subtype = row_value(row, "Sottocategoria")
    if subtype:
        return f"{subtype} a {city}; {focus}"
    return f"{focus} a {city}"


def default_notes(row: dict[str, str]) -> str:
    playbook = category_playbook(row)
    verify = points_to_verify(row, empty_insight())
    parts = [playbook["verify"]]
    if verify and verify not in parts:
        parts.append(verify)
    return "; ".join(parts)


def base_record(row: dict[str, str], index: int) -> dict[str, str]:
    gaps = automatic_gaps(row)
    primary_issue = choose_primary_issue(row, empty_insight(), [])
    proposal = choose_proposal(row, empty_insight(), [])
    lever = commercial_lever(row, [])
    issue_text = "; ".join(gaps[:3]) if gaps else primary_issue
    note_text = default_notes(row)
    return {
        "Record ID": record_id(index),
        "Nome Attivita": row_value(row, "Nome Attivita'"),
        "Priorita Distanza": row_value(row, "Priorita'"),
        "Distanza KM": row_value(row, "Distanza da Vedano Olona (km)"),
        "Categoria": row_value(row, "Categoria"),
        "Sottocategoria": row_value(row, "Sottocategoria"),
        "Comune CSV": row_value(row, "Comune") or "N/D",
        "Indirizzo CSV": row_value(row, "Indirizzo") or "N/D",
        "Telefono CSV": row_value(row, "Telefono") or "N/D",
        "Email CSV": row_value(row, "Email") or "N/D",
        "Sito CSV": row_value(row, "Sito Web") or "N/D",
        "OSM URL": row_value(row, "OSM URL") or "N/D",
        "Stato": default_state(row),
        "Comune Verificato": row_value(row, "Comune") or "N/D",
        "Indirizzo Verificato": row_value(row, "Indirizzo") or "N/D",
        "Categoria Verificata": verified_category(row),
        "Telefono": row_value(row, "Telefono"),
        "Email": row_value(row, "Email"),
        "Sito": row_value(row, "Sito Web"),
        "Fonte Recensioni Principale": "",
        "Rating Principale": "",
        "Numero Recensioni Principale": "",
        "Fonte Recensioni Secondaria": "",
        "Rating Secondaria": "",
        "Numero Recensioni Secondaria": "",
        "Cosa Fanno": default_business_summary(row),
        "Punti Forti": default_strengths(row),
        "Criticita": issue_text,
        "Proposta Mirata Base": f"{proposal}; obiettivo: {lever}",
        "Note": note_text,
        "Fonti": row_value(row, "OSM URL"),
    }


def merge_enriched(row: dict[str, str], index: int, enriched: dict[str, str]) -> dict[str, str]:
    merged = base_record(row, index)
    merged.update(
        {
            "Record ID": enriched.get("Target ID") or merged["Record ID"],
            "Stato": enriched.get("Stato") or merged["Stato"],
            "Comune Verificato": enriched.get("Comune Verificato") or merged["Comune Verificato"],
            "Indirizzo Verificato": enriched.get("Indirizzo Verificato") or merged["Indirizzo Verificato"],
            "Categoria Verificata": enriched.get("Categoria Verificata") or merged["Categoria Verificata"],
            "Telefono": enriched.get("Telefono") or row_value(row, "Telefono"),
            "Email": enriched.get("Email") or row_value(row, "Email"),
            "Sito": enriched.get("Sito") or row_value(row, "Sito Web"),
            "Fonte Recensioni Principale": enriched.get("Fonte Recensioni Principale", ""),
            "Rating Principale": enriched.get("Rating Principale", ""),
            "Numero Recensioni Principale": enriched.get("Numero Recensioni Principale", ""),
            "Fonte Recensioni Secondaria": enriched.get("Fonte Recensioni Secondaria", ""),
            "Rating Secondaria": enriched.get("Rating Secondaria", ""),
            "Numero Recensioni Secondaria": enriched.get("Numero Recensioni Secondaria", ""),
            "Cosa Fanno": enriched.get("Cosa Fanno") or merged["Cosa Fanno"],
            "Punti Forti": enriched.get("Punti Forti") or merged["Punti Forti"],
            "Criticita": enriched.get("Criticita") or merged["Criticita"],
            "Proposta Mirata Base": enriched.get("Proposta Mirata Base") or merged["Proposta Mirata Base"],
            "Note": enriched.get("Note") or merged["Note"],
            "Fonti": enriched.get("Fonti") or merged["Fonti"],
        }
    )
    return merged


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera il CSV outreach-ready sull'intero dataset."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_OSM_OUTPUT),
        help="CSV base completo da trasformare.",
    )
    parser.add_argument(
        "--shortlist-input",
        default=str(DEFAULT_DEEP_RESEARCH_SHORTLIST),
        help="CSV shortlist con Target ID e OSM URL.",
    )
    parser.add_argument(
        "--shortlist-ready",
        default=str(DEFAULT_SHORTLIST_OUTREACH_READY),
        help="CSV finale della shortlist gia' arricchito.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_TOTAL_OUTREACH_READY),
        help="CSV totale di output.",
    )
    parser.add_argument(
        "--summary",
        default=str(DEFAULT_TOTAL_OUTREACH_READY_SUMMARY),
        help="Markdown di riepilogo.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_rows = load_csv(Path(args.input))
    shortlist_rows = load_csv(Path(args.shortlist_input))
    shortlist_ready_rows = load_csv(Path(args.shortlist_ready))
    enriched_by_osm = shortlist_enriched_by_osm(shortlist_rows, shortlist_ready_rows)

    output_rows = []
    manual_rows = 0
    for index, row in enumerate(input_rows, start=1):
        osm_url = row_value(row, "OSM URL")
        enriched = enriched_by_osm.get(osm_url)
        if enriched:
            output_rows.append(merge_enriched(row, index, enriched))
            manual_rows += 1
        else:
            output_rows.append(base_record(row, index))

    write_csv(Path(args.output), output_rows)
    write_summary(Path(args.summary), output_rows, manual_rows)

    print(f"Creato CSV totale: {project_relative(args.output)} ({len(output_rows)} righe)")
    print(f"Creato summary: {project_relative(args.summary)}")
    print(f"Righe fuse dalla shortlist arricchita: {manual_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
