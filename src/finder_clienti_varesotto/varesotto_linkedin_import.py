#!/usr/bin/env python3
"""
LINKEDIN IMPORT - Converte l'input manuale in CSV.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from .paths import (
    DEFAULT_LINKEDIN_INPUT,
    DEFAULT_LINKEDIN_OUTPUT,
    ensure_parent_dir,
    project_relative,
)


class LinkedInImporter:
    def __init__(self) -> None:
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.results: list[dict[str, str]] = []

    def parse_input_file(self, filename: str | Path = DEFAULT_LINKEDIN_INPUT) -> bool:
        """Legge e parsa il file di input."""
        input_path = Path(filename)
        print(f"\nLettura: {project_relative(input_path)}\n")

        try:
            with input_path.open("r", encoding="utf-8") as handle:
                content = handle.read()

            sections = re.split(r"# ([A-Z_]+.*?)\n", content)
            current_category: dict[str, str] | None = None

            for section in sections:
                if "(PRIORITA" in section:
                    match = re.search(r"([A-Z/&\s]+)\s+\(PRIORITA\s+(ALTA|MEDIA|BASSA)\)", section)
                    if match:
                        current_category = {
                            "name": match.group(1).strip(),
                            "priority": match.group(2),
                        }
                    continue

                if not current_category or not section.strip() or section.startswith("#"):
                    continue

                lines = [
                    line.strip()
                    for line in section.split("\n")
                    if line.strip() and not line.startswith("#")
                ]

                for line in lines:
                    if "|" in line:
                        self.parse_line(line, current_category)

            return len(self.results) > 0

        except FileNotFoundError:
            print(f"File non trovato: {project_relative(input_path)}")
            print("Esegui prima: python3 scripts/varesotto_linkedin.py")
            return False
        except Exception as exc:
            print(f"Errore: {exc}")
            return False

    def parse_line(self, line: str, category: dict[str, str]) -> None:
        """Parsa una riga di dati."""
        parts = [part.strip() for part in line.split("|")]
        if not parts:
            return

        result = {
            "Data Ricerca": self.timestamp,
            "Priorita": category["priority"],
            "Categoria": category["name"],
            "Nome Attivita": parts[0] if len(parts) > 0 else "N/A",
            "Indirizzo": parts[1] if len(parts) > 1 else "N/A",
            "Provincia": "Varese",
            "Telefono": parts[2] if len(parts) > 2 else "N/A",
            "Email": parts[3] if len(parts) > 3 else "N/A",
            "Sito Web": parts[4] if len(parts) > 4 else "N/A",
            "Fonte": "LinkedIn",
            "Messaggio WhatsApp": (
                "Ciao! Sono un fornitore di menu digitali via QR code. "
                "Posso mostrarvi come funziona in 2 minuti?"
            ),
            "Note": parts[5] if len(parts) > 5 else "Contattare direttamente",
        }

        if result["Nome Attivita"] not in [record["Nome Attivita"] for record in self.results]:
            self.results.append(result)

    def save_csv(self, filename: str | Path = DEFAULT_LINKEDIN_OUTPUT) -> bool:
        """Salva i risultati su CSV."""
        if not self.results:
            print("Nessun risultato da salvare")
            return False

        priority_order = {"ALTA": 0, "MEDIA": 1, "BASSA": 2}
        self.results.sort(key=lambda item: priority_order.get(item["Priorita"], 3))

        fieldnames = [
            "Data Ricerca",
            "Priorita",
            "Categoria",
            "Nome Attivita",
            "Indirizzo",
            "Provincia",
            "Telefono",
            "Email",
            "Sito Web",
            "Fonte",
            "Messaggio WhatsApp",
            "Note",
        ]

        try:
            output_path = ensure_parent_dir(filename)
            with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.results)

            print(f"\nSalvato: {project_relative(output_path)}")
            return True
        except Exception as exc:
            print(f"Errore: {exc}")
            return False

    def print_summary(self) -> None:
        """Mostra riepilogo."""
        print("\n" + "=" * 70)
        print("RIEPILOGO RISULTATI")
        print("=" * 70)
        print(f"\nTotale attivita: {len(self.results)}")

        by_category: dict[str, int] = {}
        for result in self.results:
            category = result["Categoria"]
            by_category[category] = by_category.get(category, 0) + 1

        print("\nPer categoria:")
        for category in sorted(by_category):
            print(f"  - {category}: {by_category[category]}")

        by_priority: dict[str, int] = {}
        for result in self.results:
            priority = result["Priorita"]
            by_priority[priority] = by_priority.get(priority, 0) + 1

        print("\nPer priorita:")
        print(f"  - ALTA:   {by_priority.get('ALTA', 0)}")
        print(f"  - MEDIA:  {by_priority.get('MEDIA', 0)}")
        print(f"  - BASSA:  {by_priority.get('BASSA', 0)}")
        print("\n" + "=" * 70 + "\n")

    def run(self) -> None:
        """Esegue l'import."""
        print("\n" + "=" * 70)
        print("LINKEDIN IMPORTER - Da input a CSV")
        print("=" * 70)

        if not self.parse_input_file():
            print("\nErrore nel parsing dell'input LinkedIn")
            print("\nFormato richiesto in input.txt:")
            print("  Nome Azienda | Indirizzo | Telefono | Email | Sito Web | Note\n")
            return

        if self.save_csv():
            self.print_summary()
            print("Fatto.")
            print(f"Apri '{project_relative(DEFAULT_LINKEDIN_OUTPUT)}' per il file finale.\n")


if __name__ == "__main__":
    LinkedInImporter().run()
