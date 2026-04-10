#!/usr/bin/env python3
"""
MORPHEUS - LINKEDIN VERSION
Genera link di ricerca LinkedIn pronti e prepara i file di lavoro.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .paths import (
    DEFAULT_LINKEDIN_INPUT,
    DEFAULT_LINKEDIN_LINKS,
    DEFAULT_LINKEDIN_OUTPUT,
    ensure_parent_dir,
    project_relative,
)


class LinkedInClientFinder:
    def __init__(self) -> None:
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Categorie di aziende + keywords per LinkedIn
    RICERCHE = {
        "Ristoranti": {
            "keywords": "ristorante OR ristorazione",
            "priorita": "ALTA",
        },
        "Bar/Caffetterie": {
            "keywords": "bar OR caffetteria OR cafe",
            "priorita": "ALTA",
        },
        "Pizzerie": {
            "keywords": "pizzeria",
            "priorita": "ALTA",
        },
        "Hotel/B&B": {
            "keywords": 'hotel OR albergo OR "bed and breakfast"',
            "priorita": "MEDIA",
        },
        "Parrucchieri": {
            "keywords": "parrucchiere OR barbiere OR salone bellezza",
            "priorita": "MEDIA",
        },
        "Palestre": {
            "keywords": 'palestra OR fitness OR gym OR "centro wellness"',
            "priorita": "MEDIA",
        },
        "Negozi Abbigliamento": {
            "keywords": "abbigliamento OR moda OR boutique",
            "priorita": "BASSA",
        },
        "Farmacie/Parafarmaci": {
            "keywords": "farmacia OR parafarmacia",
            "priorita": "BASSA",
        },
        "Negozi Alimentari": {
            "keywords": "alimentari OR salumeria OR supermercato",
            "priorita": "BASSA",
        },
        "Studi Professionali": {
            "keywords": "dentista OR studio legale OR consulente",
            "priorita": "BASSA",
        },
    }

    def generate_linkedin_links(self) -> dict[str, dict[str, str]]:
        """Genera link di ricerca LinkedIn."""
        print("\n" + "=" * 80)
        print("LINK DI RICERCA LINKEDIN - VARESOTTO")
        print("=" * 80 + "\n")

        links: dict[str, dict[str, str]] = {}

        for categoria, data in self.RICERCHE.items():
            keywords = data["keywords"]
            priorita = data["priorita"]
            search_url = (
                "https://www.linkedin.com/search/results/companies/"
                f"?keywords={quote(keywords)}&origin=GLOBAL_SEARCH_HEADER&sid=aba"
            )

            links[categoria] = {
                "url": search_url,
                "priorita": priorita,
                "keywords": keywords,
            }

            badge = "ALTA" if priorita == "ALTA" else "MEDIA" if priorita == "MEDIA" else "BASSA"
            print(f"[{badge}] {categoria}")
            print(f"  URL: {search_url}")
            print(f"  Keywords: {keywords}\n")

        return links

    def save_links_to_file(
        self,
        links: dict[str, dict[str, str]],
        filename: str | Path = DEFAULT_LINKEDIN_LINKS,
    ) -> Path:
        """Salva i link in un file."""
        output_path = ensure_parent_dir(filename)

        with output_path.open("w", encoding="utf-8") as handle:
            handle.write("LINK DI RICERCA LINKEDIN - VARESOTTO\n")
            handle.write("=" * 80 + "\n\n")
            handle.write("Istruzioni:\n")
            handle.write("1. Clicca su ogni link\n")
            handle.write("2. Accedi a LinkedIn\n")
            handle.write(
                f"3. Copia i risultati e incollali nel file {project_relative(DEFAULT_LINKEDIN_INPUT)}\n"
            )
            handle.write("4. Esegui: python3 scripts/varesotto_linkedin_import.py\n\n")
            handle.write("=" * 80 + "\n\n")

            for categoria, data in links.items():
                priorita = data["priorita"]
                handle.write(
                    f"\n{'PRIORITA ALTA' if priorita == 'ALTA' else 'PRIORITA MEDIA' if priorita == 'MEDIA' else 'PRIORITA BASSA'}\n"
                )
                handle.write(f"Categoria: {categoria}\n")
                handle.write(f"Keywords: {data['keywords']}\n")
                handle.write(f"Link: {data['url']}\n")
                handle.write("-" * 80 + "\n")

        print(f"Link salvati in: {project_relative(output_path)}")
        return output_path

    def create_input_template(self, filename: str | Path = DEFAULT_LINKEDIN_INPUT) -> Path:
        """Crea template per l'input manuale."""
        template = """# ISTRUZIONI:
# 1. Per ogni categoria, clicca sul link LinkedIn
# 2. Copia i risultati (Nome Azienda, Indirizzo, ecc)
# 3. Incolla qui sotto nel formato indicato

# FORMATO:
# Nome Azienda | Indirizzo | Telefono | Email | Sito Web | Note

# RISTORANTI (PRIORITA ALTA)
# Copia i risultati da LinkedIn qui:

# BAR/CAFFETTERIE (PRIORITA ALTA)
# Copia i risultati da LinkedIn qui:

# PIZZERIE (PRIORITA ALTA)
# Copia i risultati da LinkedIn qui:

# HOTEL/B&B (PRIORITA MEDIA)
# Copia i risultati da LinkedIn qui:

# PARRUCCHIERI (PRIORITA MEDIA)
# Copia i risultati da LinkedIn qui:

# PALESTRE (PRIORITA MEDIA)
# Copia i risultati da LinkedIn qui:

# NEGOZI ABBIGLIAMENTO (PRIORITA BASSA)
# Copia i risultati da LinkedIn qui:

# FARMACIE (PRIORITA BASSA)
# Copia i risultati da LinkedIn qui:

# NEGOZI ALIMENTARI (PRIORITA BASSA)
# Copia i risultati da LinkedIn qui:

# STUDI PROFESSIONALI (PRIORITA BASSA)
# Copia i risultati da LinkedIn qui:
"""

        output_path = ensure_parent_dir(filename)
        with output_path.open("w", encoding="utf-8") as handle:
            handle.write(template)

        print(f"Template creato: {project_relative(output_path)}")
        return output_path

    def print_instructions(
        self,
        links_file: str | Path = DEFAULT_LINKEDIN_LINKS,
        input_file: str | Path = DEFAULT_LINKEDIN_INPUT,
        output_file: str | Path = DEFAULT_LINKEDIN_OUTPUT,
    ) -> None:
        """Stampa istruzioni operative."""
        print("\n" + "=" * 80)
        print("COME USARE QUESTO SCRIPT")
        print("=" * 80 + "\n")

        print("STEP 1: Apri i link LinkedIn")
        print(f"  - Apri '{project_relative(links_file)}'")
        print("  - Parti dalle categorie a priorita alta\n")

        print("STEP 2: Accedi a LinkedIn")
        print("  - Fai login con il tuo account\n")

        print("STEP 3: Ricerca e copia")
        print("  - Per ogni categoria, copia i risultati nel formato previsto\n")

        print("STEP 4: Incolla nell'input")
        print(f"  - Apri '{project_relative(input_file)}'")
        print("  - Incolla i risultati sotto la categoria giusta\n")

        print("STEP 5: Genera CSV finale")
        print("  - Esegui: python3 scripts/varesotto_linkedin_import.py")
        print(f"  - Output previsto: '{project_relative(output_file)}'\n")

        print("=" * 80 + "\n")

    def run(self) -> None:
        """Esegue il programma."""
        print("\n" + "=" * 80)
        print("MORPHEUS - LINKEDIN VERSION")
        print("=" * 80)
        print(f"Data: {self.timestamp}\n")

        links = self.generate_linkedin_links()
        links_file = self.save_links_to_file(links)
        input_file = self.create_input_template()
        self.print_instructions(links_file=links_file, input_file=input_file)

        print("Setup completato.\n")
        print("File aggiornati:")
        print(f"  - {project_relative(links_file)}")
        print(f"  - {project_relative(input_file)}")
        print(f"  - scripts/varesotto_linkedin_import.py\n")


if __name__ == "__main__":
    LinkedInClientFinder().run()
