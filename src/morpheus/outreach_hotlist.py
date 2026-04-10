#!/usr/bin/env python3
"""
Estrae dal CSV outreach-ready i sottoinsiemi piu' utili per il contatto.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from .paths import ensure_parent_dir, project_relative


PRIORITY_ORDER = {
    "ALTISSIMA": 0,
    "ALTA": 1,
    "MEDIA": 2,
    "BASSA": 3,
    "MOLTO BASSA": 4,
}


def load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return rows, reader.fieldnames or []


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    destination = ensure_parent_dir(path)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def has_contact_or_site(row: dict[str, str]) -> bool:
    return any([row.get("Telefono"), row.get("Email"), row.get("Sito")])


def has_location(row: dict[str, str]) -> bool:
    return any(
        [
            row.get("Comune Verificato") not in {"", "N/D"},
            row.get("Indirizzo Verificato") not in {"", "N/D"},
        ]
    )


def sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    def key(row: dict[str, str]) -> tuple[int, int, str]:
        status_order = 0 if row.get("Stato") == "OK" else 1
        priority_order = PRIORITY_ORDER.get(row.get("Priorita Distanza", ""), 99)
        return (
            status_order,
            priority_order,
            row.get("Nome Attivita", "").lower(),
        )

    return sorted(rows, key=key)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Estrae hotlist operative dal CSV outreach-ready.")
    parser.add_argument("--input", required=True, help="CSV outreach-ready completo.")
    parser.add_argument("--output-ok", required=True, help="CSV solo OK.")
    parser.add_argument(
        "--output-parziali",
        required=True,
        help="CSV PARZIALI contattabili ad alta priorita.",
    )
    parser.add_argument("--output-hotlist", required=True, help="CSV hotlist combinata.")
    parser.add_argument("--summary", required=True, help="Markdown riassuntivo.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    rows, fieldnames = load_csv(Path(args.input))
    ok_rows = sort_rows([row for row in rows if row.get("Stato") == "OK"])
    parziali_rows = sort_rows(
        [
            row
            for row in rows
            if row.get("Stato") == "PARZIALE"
            and row.get("Priorita Distanza") in {"ALTISSIMA", "ALTA"}
            and has_contact_or_site(row)
            and has_location(row)
        ]
    )
    hotlist_rows = sort_rows(ok_rows + parziali_rows)

    write_csv(Path(args.output_ok), fieldnames, ok_rows)
    write_csv(Path(args.output_parziali), fieldnames, parziali_rows)
    write_csv(Path(args.output_hotlist), fieldnames, hotlist_rows)

    lines = [
        "# Hotlist Outreach",
        "",
        f"- File base: `{project_relative(args.input)}`",
        f"- OK pronti: {len(ok_rows)}",
        f"- PARZIALI contattabili: {len(parziali_rows)}",
        f"- HOTLIST totale: {len(hotlist_rows)}",
        "",
        "## Regola usata per i PARZIALI",
        "",
        "- solo `ALTISSIMA` o `ALTA`",
        "- almeno un `Telefono`, `Email` o `Sito`",
        "- almeno `Comune Verificato` o `Indirizzo Verificato` valorizzato",
        "",
        f"- CSV OK: `{project_relative(args.output_ok)}`",
        f"- CSV PARZIALI: `{project_relative(args.output_parziali)}`",
        f"- CSV HOTLIST: `{project_relative(args.output_hotlist)}`",
    ]
    ensure_parent_dir(args.summary).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"OK: {len(ok_rows)}")
    print(f"PARZIALI contattabili: {len(parziali_rows)}")
    print(f"HOTLIST: {len(hotlist_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
