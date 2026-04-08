#!/usr/bin/env python3
"""
VARESOTTO CLIENT FINDER - OSM/OVERPASS

Recupera attivita' commerciali nella provincia di Varese da OpenStreetMap,
le ordina per distanza da Vedano Olona e mette in cima quelle senza sito web.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from .paths import DEFAULT_OSM_OUTPUT, ensure_parent_dir, project_relative


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = (
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)

DEFAULT_REFERENCE_QUERY = "Vedano Olona, Varese, Lombardia, Italia"
DEFAULT_PROVINCE_QUERY = "Provincia di Varese, Lombardia, Italia"
DEFAULT_OUTPUT = str(DEFAULT_OSM_OUTPUT)

# Fallback usato se Nominatim non riesce a geocodificare Vedano Olona.
DEFAULT_REFERENCE_POINT = {
    "name": "Vedano Olona",
    "lat": 45.7755,
    "lon": 8.8872,
}

GENERIC_NAMES = {
    "bar",
    "bar caffe",
    "bar caffetteria",
    "cafe",
    "caffe",
    "caffetteria",
    "centro estetico",
    "dentista",
    "farmacia",
    "fast food",
    "fitness centre",
    "gelateria",
    "gym",
    "hairdresser",
    "hotel",
    "lavanderia",
    "negozio",
    "palestra",
    "parafarmacia",
    "parrucchiere",
    "pizzeria",
    "pub",
    "restaurant",
    "ristorante",
    "salone bellezza",
    "shop",
    "studio dentistico",
    "studio legale",
    "studio medico",
}

FOOD_VALUES = {
    "bar",
    "biergarten",
    "cafe",
    "fast_food",
    "food_court",
    "ice_cream",
    "pub",
    "restaurant",
}
HOSPITALITY_VALUES = {
    "alpine_hut",
    "apartment",
    "bed_and_breakfast",
    "camp_site",
    "chalet",
    "guest_house",
    "hostel",
    "hotel",
    "motel",
}
BEAUTY_VALUES = {"beauty", "hairdresser", "barber"}
FITNESS_VALUES = {"fitness_centre", "sports_centre"}
HEALTH_VALUES = {"clinic", "dentist", "doctors", "pharmacy", "veterinary"}
OFFICE_VALUES = {
    "accountant",
    "architect",
    "company",
    "estate_agent",
    "financial",
    "insurance",
    "lawyer",
    "travel_agent",
}
SHOP_BEAUTY_VALUES = {"beauty", "cosmetics", "hairdresser", "perfumery"}
SHOP_HEALTH_VALUES = {"chemist", "hearing_aids", "medical_supply", "optician"}
SHOP_FITNESS_VALUES = {"sports"}

CATEGORY_ORDER = {
    "Ristorazione": 0,
    "Ospitalita'": 1,
    "Beauty & Benessere": 2,
    "Fitness & Sport": 3,
    "Sanita'": 4,
    "Servizi Professionali": 5,
    "Artigiani": 6,
    "Negozi": 7,
}

FRIENDLY_VALUE_LABELS = {
    "accountant": "Commercialista",
    "alpine_hut": "Rifugio",
    "apartment": "Appartamenti",
    "architect": "Architetto",
    "bar": "Bar",
    "barber": "Barbiere",
    "beauty": "Centro Estetico",
    "bed_and_breakfast": "B&B",
    "biergarten": "Birreria",
    "cafe": "Caffetteria",
    "camp_site": "Camping",
    "chalet": "Chalet",
    "clinic": "Clinica",
    "company": "Azienda",
    "dentist": "Dentista",
    "doctors": "Studio Medico",
    "estate_agent": "Agenzia Immobiliare",
    "fast_food": "Fast Food",
    "financial": "Servizi Finanziari",
    "fitness_centre": "Centro Fitness",
    "food_court": "Food Court",
    "guest_house": "Affittacamere",
    "hairdresser": "Parrucchiere",
    "hostel": "Ostello",
    "hotel": "Hotel",
    "ice_cream": "Gelateria",
    "insurance": "Assicurazioni",
    "lawyer": "Studio Legale",
    "motel": "Motel",
    "pharmacy": "Farmacia",
    "pub": "Pub",
    "restaurant": "Ristorante",
    "sports_centre": "Centro Sportivo",
    "travel_agent": "Agenzia Viaggi",
    "veterinary": "Veterinario",
}


@dataclass(frozen=True)
class SearchGroup:
    label: str
    key: str
    values: tuple[str, ...] | None = None


SEARCH_GROUPS = (
    SearchGroup(
        label="Ristorazione",
        key="amenity",
        values=tuple(sorted(FOOD_VALUES)),
    ),
    SearchGroup(
        label="Ospitalita'",
        key="tourism",
        values=tuple(sorted(HOSPITALITY_VALUES)),
    ),
    SearchGroup(
        label="Beauty & Benessere",
        key="amenity",
        values=tuple(sorted(BEAUTY_VALUES)),
    ),
    SearchGroup(
        label="Beauty & Benessere",
        key="shop",
        values=tuple(sorted(SHOP_BEAUTY_VALUES)),
    ),
    SearchGroup(
        label="Fitness & Sport",
        key="leisure",
        values=tuple(sorted(FITNESS_VALUES)),
    ),
    SearchGroup(
        label="Fitness & Sport",
        key="shop",
        values=tuple(sorted(SHOP_FITNESS_VALUES)),
    ),
    SearchGroup(
        label="Sanita'",
        key="amenity",
        values=tuple(sorted(HEALTH_VALUES)),
    ),
    SearchGroup(
        label="Sanita'",
        key="shop",
        values=tuple(sorted(SHOP_HEALTH_VALUES)),
    ),
    SearchGroup(
        label="Servizi Professionali",
        key="office",
        values=tuple(sorted(OFFICE_VALUES)),
    ),
    SearchGroup(
        label="Artigiani",
        key="craft",
        values=None,
    ),
    SearchGroup(
        label="Negozi",
        key="shop",
        values=None,
    ),
)


class VaresottoOSMFinder:
    def __init__(
        self,
        province_query: str = DEFAULT_PROVINCE_QUERY,
        reference_query: str = DEFAULT_REFERENCE_QUERY,
        output_file: str = DEFAULT_OUTPUT,
        limit: int = 0,
    ) -> None:
        self.province_query = province_query
        self.reference_query = reference_query
        self.output_file = Path(output_file)
        self.limit = limit
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.results: list[dict[str, Any]] = []
        self.failed_groups: list[str] = []
        self.reference_point = DEFAULT_REFERENCE_POINT.copy()
        self.area_id: int | None = None
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "VaresottoClientFinder/2.0 (Codex)",
                "Accept-Language": "it",
            }
        )

    def _normalize_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        lowered = ascii_value.lower().strip()
        return re.sub(r"\s+", " ", lowered)

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_km = 6371.0
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius_km * c

    def _distance_priority(self, distance_km: float) -> str:
        if distance_km <= 5:
            return "ALTISSIMA"
        if distance_km <= 10:
            return "ALTA"
        if distance_km <= 20:
            return "MEDIA"
        if distance_km <= 30:
            return "BASSA"
        return "MOLTO BASSA"

    def _website_opportunity(self, website: str, email: str) -> str:
        if not website:
            return "ALTA"
        if not email:
            return "MEDIA"
        return "BASSA"

    def _first_tag(self, tags: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = tags.get(key)
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    return cleaned
        return ""

    def _safe_name(self, tags: dict[str, Any]) -> str:
        candidates = (
            tags.get("name"),
            tags.get("brand"),
            tags.get("official_name"),
            tags.get("operator"),
        )

        best_name = ""
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            cleaned = candidate.strip()
            if cleaned:
                best_name = cleaned
                break

        if not best_name:
            return ""

        normalized = self._normalize_text(best_name)
        if normalized in GENERIC_NAMES:
            for fallback_key in ("brand", "operator", "official_name"):
                fallback = tags.get(fallback_key)
                if isinstance(fallback, str) and fallback.strip():
                    fallback_clean = fallback.strip()
                    if self._normalize_text(fallback_clean) not in GENERIC_NAMES:
                        return fallback_clean
        return best_name

    def _is_useful_name(self, name: str, subtype: str) -> bool:
        normalized_name = self._normalize_text(name)
        normalized_subtype = self._normalize_text(subtype.replace("_", " "))

        if len(normalized_name) < 4:
            return False
        if normalized_name in GENERIC_NAMES:
            return False
        if normalized_subtype and normalized_name == normalized_subtype:
            return False
        return True

    def _friendly_value(self, value: str) -> str:
        if value in FRIENDLY_VALUE_LABELS:
            return FRIENDLY_VALUE_LABELS[value]
        return value.replace("_", " ").title()

    def _classify_business(self, tags: dict[str, Any], fallback_group: SearchGroup) -> tuple[str, str]:
        for key in ("amenity", "tourism", "leisure", "office", "craft", "shop"):
            raw_value = self._first_tag(tags, key)
            if not raw_value:
                continue

            if key == "amenity":
                if raw_value in FOOD_VALUES:
                    return "Ristorazione", self._friendly_value(raw_value)
                if raw_value in BEAUTY_VALUES:
                    return "Beauty & Benessere", self._friendly_value(raw_value)
                if raw_value in HEALTH_VALUES:
                    return "Sanita'", self._friendly_value(raw_value)
            elif key == "tourism" and raw_value in HOSPITALITY_VALUES:
                return "Ospitalita'", self._friendly_value(raw_value)
            elif key == "leisure" and raw_value in FITNESS_VALUES:
                return "Fitness & Sport", self._friendly_value(raw_value)
            elif key == "office" and raw_value in OFFICE_VALUES:
                return "Servizi Professionali", self._friendly_value(raw_value)
            elif key == "craft":
                return "Artigiani", self._friendly_value(raw_value)
            elif key == "shop":
                if raw_value in SHOP_BEAUTY_VALUES:
                    return "Beauty & Benessere", self._friendly_value(raw_value)
                if raw_value in SHOP_HEALTH_VALUES:
                    return "Sanita'", self._friendly_value(raw_value)
                if raw_value in SHOP_FITNESS_VALUES:
                    return "Fitness & Sport", self._friendly_value(raw_value)
                return "Negozi", self._friendly_value(raw_value)

        subtype = self._first_tag(tags, fallback_group.key) or fallback_group.label
        return fallback_group.label, self._friendly_value(subtype)

    def _compose_address(self, tags: dict[str, Any]) -> tuple[str, str]:
        address_full = self._first_tag(tags, "addr:full")
        city = self._first_tag(tags, "addr:city", "addr:town", "addr:village", "addr:hamlet", "addr:place")
        postcode = self._first_tag(tags, "addr:postcode")
        street = self._first_tag(tags, "addr:street")
        house_number = self._first_tag(tags, "addr:housenumber")

        if address_full:
            return address_full, city

        line_1 = " ".join(part for part in (street, house_number) if part).strip()
        line_2 = " ".join(part for part in (postcode, city) if part).strip()
        address = ", ".join(part for part in (line_1, line_2) if part).strip(", ")
        return address or "N/D", city

    def _osm_url(self, element: dict[str, Any]) -> str:
        element_type = element.get("type")
        element_id = element.get("id")
        if not element_type or element_id is None:
            return ""
        return f"https://www.openstreetmap.org/{element_type}/{element_id}"

    def _record_score(self, record: dict[str, Any]) -> int:
        score = 0
        score += 3 if record["Ha Sito Web"] == "NO" else 0
        score += 2 if record["Telefono"] != "N/D" else 0
        score += 2 if record["Email"] != "N/D" else 0
        score += 1 if record["Indirizzo"] != "N/D" else 0
        score += 1 if record["Comune"] != "N/D" else 0
        return score

    def _dedupe_key(self, record: dict[str, Any]) -> tuple[str, float, float]:
        return (
            self._normalize_text(record["Nome Attivita'"]),
            round(record["_lat"], 4),
            round(record["_lon"], 4),
        )

    def _choose_record(self, current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        if self._record_score(candidate) > self._record_score(current):
            return candidate
        return current

    def geocode_reference_point(self) -> None:
        data = self._search_nominatim(self.reference_query)
        if not data:
            print(
                f"  ! Geocodifica non disponibile, uso coordinate di fallback per {self.reference_point['name']}"
            )
            return

        first = data[0]
        self.reference_point = {
            "name": first.get("display_name", DEFAULT_REFERENCE_QUERY).split(",")[0].strip(),
            "lat": float(first["lat"]),
            "lon": float(first["lon"]),
        }

    def resolve_area_id(self) -> None:
        candidates = (
            self.province_query,
            "Varese, Lombardia, Italia",
        )

        for query in candidates:
            for item in self._search_nominatim(query):
                osm_type = item.get("osm_type")
                osm_id = item.get("osm_id")
                display_name = self._normalize_text(item.get("display_name", ""))
                item_type = self._normalize_text(item.get("type", ""))
                addresstype = self._normalize_text(item.get("addresstype", ""))

                if osm_type not in {"relation", "way"} or not osm_id:
                    continue
                if "varese" not in display_name:
                    continue
                if "provincia" not in display_name and item_type not in {"county", "administrative"} and addresstype not in {"county", "state_district"}:
                    continue

                if osm_type == "relation":
                    self.area_id = 3_600_000_000 + int(osm_id)
                else:
                    self.area_id = 2_400_000_000 + int(osm_id)
                return

        raise RuntimeError("Impossibile determinare l'area della provincia di Varese.")

    def _search_nominatim(self, query: str) -> list[dict[str, Any]]:
        try:
            response = self.session.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 5,
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return []

    def _build_overpass_query(self, group: SearchGroup) -> str:
        if self.area_id is None:
            raise RuntimeError("Area OSM non inizializzata.")

        if group.values:
            value_pattern = "|".join(re.escape(value) for value in group.values)
            selector = f'["{group.key}"~"^({value_pattern})$"]'
        else:
            selector = f'["{group.key}"]'

        return f"""
[out:json][timeout:180];
area({self.area_id})->.searchArea;
(
  nwr(area.searchArea){selector}["name"];
);
out body center qt;
"""

    def _fetch_group(self, group: SearchGroup) -> list[dict[str, Any]]:
        query = self._build_overpass_query(group)

        last_error = None
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                response = self.session.post(
                    endpoint,
                    data={"data": query},
                    timeout=120,
                )
                response.raise_for_status()
                payload = response.json()
                return payload.get("elements", [])
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                continue

        if last_error:
            raise RuntimeError(f"Overpass non disponibile per {group.label}: {last_error}") from last_error
        raise RuntimeError(f"Overpass non disponibile per {group.label}")

    def _element_to_record(self, element: dict[str, Any], group: SearchGroup) -> dict[str, Any] | None:
        tags = element.get("tags", {})
        if not tags:
            return None

        lat = element.get("lat")
        lon = element.get("lon")
        if lat is None or lon is None:
            center = element.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")
        if lat is None or lon is None:
            return None

        name = self._safe_name(tags)
        subtype = self._first_tag(tags, "amenity", "tourism", "leisure", "office", "craft", "shop")
        if not name or not self._is_useful_name(name, subtype):
            return None

        category, subcategory = self._classify_business(tags, group)
        address, city = self._compose_address(tags)
        website = self._first_tag(tags, "website", "contact:website")
        email = self._first_tag(tags, "email", "contact:email")
        phone = self._first_tag(tags, "phone", "contact:phone", "mobile", "contact:mobile")
        distance_km = self._haversine_km(
            self.reference_point["lat"],
            self.reference_point["lon"],
            float(lat),
            float(lon),
        )

        return {
            "Data Ricerca": self.timestamp,
            "Priorita'": self._distance_priority(distance_km),
            "Distanza da Vedano Olona (km)": f"{distance_km:.2f}",
            "Categoria": category,
            "Sottocategoria": subcategory,
            "Nome Attivita'": name,
            "Comune": city or "N/D",
            "Indirizzo": address,
            "Provincia": "Varese",
            "Telefono": phone or "N/D",
            "Email": email or "N/D",
            "Sito Web": website or "N/D",
            "Ha Sito Web": "SI" if website else "NO",
            "Opportunita' Web": self._website_opportunity(website, email),
            "Fonte": "OpenStreetMap / Overpass",
            "OSM URL": self._osm_url(element) or "N/D",
            "Note": "Verificare contatto commerciale e stato sito web",
            "Lat": round(float(lat), 6),
            "Lon": round(float(lon), 6),
            "_lat": float(lat),
            "_lon": float(lon),
        }

    def cleanup_duplicates(self) -> None:
        deduped: dict[tuple[str, float, float], dict[str, Any]] = {}

        for record in self.results:
            key = self._dedupe_key(record)
            current = deduped.get(key)
            deduped[key] = record if current is None else self._choose_record(current, record)

        removed = len(self.results) - len(deduped)
        self.results = list(deduped.values())
        if removed > 0:
            print(f"\n  ♻ Rimossi {removed} duplicati")

    def sort_results(self) -> None:
        self.results.sort(
            key=lambda item: (
                float(item["Distanza da Vedano Olona (km)"]),
                0 if item["Ha Sito Web"] == "NO" else 1,
                CATEGORY_ORDER.get(item["Categoria"], 99),
                self._normalize_text(item["Nome Attivita'"]),
            )
        )

        if self.limit > 0:
            self.results = self.results[: self.limit]

    def save_csv(self) -> None:
        if not self.results:
            raise RuntimeError("Nessun risultato da salvare.")

        fieldnames = [
            "Data Ricerca",
            "Priorita'",
            "Distanza da Vedano Olona (km)",
            "Lat",
            "Lon",
            "Categoria",
            "Sottocategoria",
            "Nome Attivita'",
            "Comune",
            "Indirizzo",
            "Provincia",
            "Telefono",
            "Email",
            "Sito Web",
            "Ha Sito Web",
            "Opportunita' Web",
            "Fonte",
            "OSM URL",
            "Note",
        ]

        output_path = ensure_parent_dir(self.output_file)
        with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.results)

    def print_summary(self) -> None:
        without_site = sum(1 for item in self.results if item["Ha Sito Web"] == "NO")

        per_priority: dict[str, int] = {}
        for item in self.results:
            priority = item["Priorita'"]
            per_priority[priority] = per_priority.get(priority, 0) + 1

        print("\n" + "=" * 78)
        print("RIEPILOGO")
        print("=" * 78)
        print(f"Totale attivita': {len(self.results)}")
        print(f"Senza sito web: {without_site}")
        print(f"Con sito web:   {len(self.results) - without_site}")
        print(f"Centro ranking: {self.reference_point['name']} ({self.reference_point['lat']:.4f}, {self.reference_point['lon']:.4f})")
        print("\nPer priorita' distanza:")
        for label in ("ALTISSIMA", "ALTA", "MEDIA", "BASSA", "MOLTO BASSA"):
            print(f"  - {label:<13} {per_priority.get(label, 0)}")
        if self.failed_groups:
            print("\nGruppi con query non completata:")
            for group in self.failed_groups:
                print(f"  - {group}")

    def run(self) -> None:
        print("\n" + "=" * 78)
        print("VARESOTTO CLIENT FINDER - OSM/OVERPASS")
        print("=" * 78)
        print(f"Avvio: {self.timestamp}")

        print(f"\n[1/4] Geocodifico il centro di priorita': {self.reference_query}")
        self.geocode_reference_point()

        print(f"[2/4] Individuo l'area OSM della provincia: {self.province_query}")
        self.resolve_area_id()

        print("[3/4] Raccolgo attivita' commerciali nella provincia di Varese")
        for index, group in enumerate(SEARCH_GROUPS, start=1):
            print(f"  - Query {index}/{len(SEARCH_GROUPS)}: {group.label}")
            try:
                elements = self._fetch_group(group)
            except RuntimeError as exc:
                print(f"    ! salto il gruppo per errore rete: {exc}")
                self.failed_groups.append(group.label)
                continue
            added = 0
            for element in elements:
                record = self._element_to_record(element, group)
                if record:
                    self.results.append(record)
                    added += 1
            print(f"    -> elementi utili: {added}")
            time.sleep(1)

        self.cleanup_duplicates()
        self.sort_results()

        print(f"[4/4] Salvo il CSV ordinato per vicinanza in {project_relative(self.output_file)}")
        self.save_csv()
        self.print_summary()
        print("\nCSV pronto. I primi record sono i prospect piu' vicini a Vedano Olona.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trova attivita' commerciali nella provincia di Varese ordinate per distanza da Vedano Olona."
    )
    parser.add_argument(
        "--province",
        default=DEFAULT_PROVINCE_QUERY,
        help="Area da interrogare su OSM/Nominatim. Default: provincia di Varese.",
    )
    parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE_QUERY,
        help="Punto da cui calcolare la distanza. Default: Vedano Olona.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Percorso del CSV finale. Default: {project_relative(DEFAULT_OSM_OUTPUT)}.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Numero massimo di righe da salvare dopo l'ordinamento. 0 = nessun limite.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    finder = VaresottoOSMFinder(
        province_query=args.province,
        reference_query=args.reference,
        output_file=args.output,
        limit=args.limit,
    )
    finder.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
