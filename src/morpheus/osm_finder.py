#!/usr/bin/env python3
"""
MORPHEUS — RACCOLTA LEAD OSM/OVERPASS + FOURSQUARE

Recupera attivita' commerciali in una provincia da OpenStreetMap,
le ordina per score composito (distanza + assenza sito + categoria target)
e le integra con dati da Foursquare Places API.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
from pathlib import Path
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import requests

from .paths import DEFAULT_OSM_OUTPUT, ensure_parent_dir, project_relative


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = (
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
FSQ_SEARCH_URL = "https://api.foursquare.com/v3/places/search"
GOOGLE_PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Field mask Google Places (New): Essentials + Pro.
# "websiteUri" e "nationalPhoneNumber" sono Pro → billing Pro SKU (~$0.036/call).
# NON aggiungere campi Enterprise (rating, opening hours, photos) senza valutare il costo.
GOOGLE_PLACES_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.types",
        "places.primaryType",
        "places.primaryTypeDisplayName",
        "places.addressComponents",
        "places.websiteUri",
        "places.nationalPhoneNumber",
    )
)

# Limiti free tier — qualunque sforo sono soldi reali.
# Free credit $200/mese ≈ 5.500 chiamate Pro. Con default sotto, una scansione costa < $0.30.
GOOGLE_PLACES_ENABLED: bool = os.environ.get("GOOGLE_PLACES_ENABLED", "1").strip() not in {"0", "false", "no", ""}
GOOGLE_PLACES_MAX_CALLS: int = int(os.environ.get("GOOGLE_PLACES_MAX_CALLS", "15"))
GOOGLE_PLACES_MAX_RESULTS: int = int(os.environ.get("GOOGLE_PLACES_MAX_RESULTS", "180"))
GOOGLE_PLACES_PAGE_SIZE: int = 20           # hard cap lato Google (searchNearby)
GOOGLE_PLACES_MAX_RADIUS_M: int = 50_000    # hard cap lato Google (searchNearby)

DEFAULT_REFERENCE_QUERY = "Vedano Olona, Varese, Lombardia, Italia"
DEFAULT_PROVINCE_QUERY = "Provincia di Varese, Lombardia, Italia"
DEFAULT_OUTPUT = str(DEFAULT_OSM_OUTPUT)

# Scoring: configurabili via env (opzionale)
DEFAULT_MAX_DISTANCE_KM: float = float(os.environ.get("SCORING_MAX_DISTANCE_KM", "50"))
DEFAULT_TARGET_CATEGORIES: list[str] = [
    cat.strip()
    for cat in os.environ.get("SCORING_CATEGORIES", "").split(",")
    if cat.strip()
]

# Fallback usato se Nominatim non riesce a geocodificare il punto di riferimento.
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
FITNESS_VALUES = {"dance", "fitness_centre", "sports_centre"}
HEALTH_VALUES = {"clinic", "dentist", "doctors", "pharmacy", "veterinary"}
ENTERTAINMENT_VALUES = {"cinema", "events_venue", "nightclub", "theatre"}
OFFICE_VALUES = {
    "accountant",
    "architect",
    "association",
    "company",
    "estate_agent",
    "financial",
    "insurance",
    "it",
    "lawyer",
    "logistics",
    "notary",
    "travel_agent",
}
SHOP_BEAUTY_VALUES = {"beauty", "cosmetics", "hairdresser", "perfumery"}
SHOP_HEALTH_VALUES = {"chemist", "hearing_aids", "medical_supply", "optician"}
SHOP_FITNESS_VALUES = {"sports"}
AUTOMOTIVE_AMENITY_VALUES = {"car_rental", "car_sharing", "car_wash", "fuel", "charging_station"}
SHOP_AUTOMOTIVE_VALUES = {
    "bicycle",
    "car",
    "car_parts",
    "car_repair",
    "motorcycle",
    "motorcycle_repair",
    "tyres",
}
EDUCATION_AMENITY_VALUES = {
    "dance_school",
    "driving_school",
    "language_school",
    "music_school",
    "training",
    "tutoring",
}
OFFICE_EDUCATION_VALUES = {"educational_institution", "tutoring", "research"}

CATEGORY_ORDER = {
    "Ristorazione": 0,
    "Ospitalita'": 1,
    "Beauty & Benessere": 2,
    "Fitness & Sport": 3,
    "Sanita'": 4,
    "Servizi Professionali": 5,
    "Artigiani": 6,
    "Negozi": 7,
    "Intrattenimento": 8,
    "Automotive": 9,
    "Formazione": 10,
}

FRIENDLY_VALUE_LABELS = {
    "bicycle": "Negozio Bici",
    "car": "Concessionaria Auto",
    "car_parts": "Autoricambi",
    "car_rental": "Autonoleggio",
    "car_repair": "Officina",
    "car_sharing": "Car Sharing",
    "car_wash": "Autolavaggio",
    "charging_station": "Colonnina Ricarica",
    "dance_school": "Scuola Danza",
    "driving_school": "Scuola Guida",
    "educational_institution": "Scuola / Ente Formazione",
    "fuel": "Distributore Carburante",
    "language_school": "Scuola Lingue",
    "motorcycle": "Concessionaria Moto",
    "motorcycle_repair": "Officina Moto",
    "music_school": "Scuola Musica",
    "research": "Centro Ricerca",
    "training": "Centro Formazione",
    "tutoring": "Ripetizioni",
    "tyres": "Gommista",
    "accountant": "Commercialista",
    "alpine_hut": "Rifugio",
    "apartment": "Appartamenti",
    "architect": "Architetto",
    "association": "Associazione",
    "bar": "Bar",
    "barber": "Barbiere",
    "beauty": "Centro Estetico",
    "bed_and_breakfast": "B&B",
    "biergarten": "Birreria",
    "cafe": "Caffetteria",
    "camp_site": "Camping",
    "chalet": "Chalet",
    "cinema": "Cinema",
    "clinic": "Clinica",
    "company": "Azienda",
    "dance": "Studio Danza",
    "dentist": "Dentista",
    "doctors": "Studio Medico",
    "estate_agent": "Agenzia Immobiliare",
    "events_venue": "Spazio Eventi",
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
    "it": "Azienda IT",
    "lawyer": "Studio Legale",
    "logistics": "Logistica",
    "motel": "Motel",
    "nightclub": "Discoteca",
    "notary": "Notaio",
    "pharmacy": "Farmacia",
    "pub": "Pub",
    "restaurant": "Ristorante",
    "sports_centre": "Centro Sportivo",
    "theatre": "Teatro",
    "travel_agent": "Agenzia Viaggi",
    "veterinary": "Veterinario",
}

# Mapping categoria Foursquare → nostra categoria.
# Lista ordinata: prima corrispondenza trovata vince (case-insensitive substring).
_FSQ_CATEGORY_MAP: list[tuple[str, str]] = [
    ("restaurant", "Ristorazione"),
    ("trattoria", "Ristorazione"),
    ("osteria", "Ristorazione"),
    ("cafe", "Ristorazione"),
    ("coffee", "Ristorazione"),
    ("bar", "Ristorazione"),
    ("pizza", "Ristorazione"),
    ("bakery", "Ristorazione"),
    ("food", "Ristorazione"),
    ("pub", "Ristorazione"),
    ("hotel", "Ospitalita'"),
    ("hostel", "Ospitalita'"),
    ("bed & breakfast", "Ospitalita'"),
    ("b&b", "Ospitalita'"),
    ("lodging", "Ospitalita'"),
    ("camping", "Ospitalita'"),
    ("guest house", "Ospitalita'"),
    ("beauty", "Beauty & Benessere"),
    ("spa", "Beauty & Benessere"),
    ("hair", "Beauty & Benessere"),
    ("nail", "Beauty & Benessere"),
    ("barber", "Beauty & Benessere"),
    ("cosmet", "Beauty & Benessere"),
    ("dance", "Fitness & Sport"),
    ("gym", "Fitness & Sport"),
    ("fitness", "Fitness & Sport"),
    ("sport", "Fitness & Sport"),
    ("palestra", "Fitness & Sport"),
    ("yoga", "Fitness & Sport"),
    ("medical", "Sanita'"),
    ("dental", "Sanita'"),
    ("pharmacy", "Sanita'"),
    ("farmacia", "Sanita'"),
    ("doctor", "Sanita'"),
    ("health", "Sanita'"),
    ("clinic", "Sanita'"),
    ("hospital", "Sanita'"),
    ("nightclub", "Intrattenimento"),
    ("cinema", "Intrattenimento"),
    ("theater", "Intrattenimento"),
    ("theatre", "Intrattenimento"),
    ("entertainment", "Intrattenimento"),
    ("event", "Intrattenimento"),
    ("law", "Servizi Professionali"),
    ("accountant", "Servizi Professionali"),
    ("insurance", "Servizi Professionali"),
    ("real estate", "Servizi Professionali"),
    ("tech", "Servizi Professionali"),
    ("it service", "Servizi Professionali"),
    ("financial", "Servizi Professionali"),
    ("auto repair", "Automotive"),
    ("car wash", "Automotive"),
    ("gas station", "Automotive"),
    ("auto dealer", "Automotive"),
    ("car dealer", "Automotive"),
    ("automotive", "Automotive"),
    ("motorcycle", "Automotive"),
    ("tire", "Automotive"),
    ("tyre", "Automotive"),
    ("driving school", "Formazione"),
    ("language school", "Formazione"),
    ("music school", "Formazione"),
    ("dance school", "Formazione"),
    ("school", "Formazione"),
    ("tutoring", "Formazione"),
    ("education", "Formazione"),
    ("college", "Formazione"),
    ("university", "Formazione"),
    ("craft", "Artigiani"),
    ("repair", "Artigiani"),
    ("workshop", "Artigiani"),
    ("plumb", "Artigiani"),
    ("electric", "Artigiani"),
    ("tailor", "Artigiani"),
    ("shop", "Negozi"),
    ("store", "Negozi"),
    ("boutique", "Negozi"),
    ("market", "Negozi"),
]

# Mapping nostra categoria → Google Places types (New API).
# 11 categorie = 11 call/scan. A $0.036/call Pro SKU → ~$0.40/scan.
# Free tier $200/mese ≈ 500 scan totali. Margine largo.
# Per Negozi e Artigiani scegliamo type specifici per evitare risultati generici
# di catene nazionali che saturano i 20 slot/chiamata.
_GOOGLE_CATEGORY_TYPES: dict[str, tuple[str, ...]] = {
    "Ristorazione": (
        "restaurant",
        "cafe",
        "bar",
        "bakery",
        "coffee_shop",
        "ice_cream_shop",
        "meal_takeaway",
    ),
    "Ospitalita'": (
        "lodging",
    ),
    "Beauty & Benessere": (
        "beauty_salon",
        "hair_salon",
        "spa",
        "barber_shop",
        "nail_salon",
    ),
    "Fitness & Sport": (
        "gym",
        "fitness_center",
    ),
    "Sanita'": (
        "doctor",
        "dentist",
        "pharmacy",
        "hospital",
        "physiotherapist",
        "veterinary_care",
    ),
    "Servizi Professionali": (
        "lawyer",
        "accounting",
        "insurance_agency",
        "real_estate_agency",
        "travel_agency",
    ),
    "Intrattenimento": (
        "movie_theater",
        "night_club",
    ),
    "Automotive": (
        "car_dealer",
        "car_rental",
        "car_repair",
        "car_wash",
        "gas_station",
    ),
    "Formazione": (
        "driving_school",
        "school",
        "primary_school",
        "secondary_school",
        "preschool",
    ),
    "Artigiani": (
        "plumber",
        "electrician",
        "painter",
        "locksmith",
        "roofing_contractor",
        "general_contractor",
    ),
    "Negozi": (
        "clothing_store",
        "shoe_store",
        "jewelry_store",
        "book_store",
        "furniture_store",
        "hardware_store",
        "florist",
        "electronics_store",
    ),
}

_GOOGLE_TYPE_TO_CATEGORY: dict[str, str] = {
    gtype: cat for cat, gtypes in _GOOGLE_CATEGORY_TYPES.items() for gtype in gtypes
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
        label="Intrattenimento",
        key="amenity",
        values=tuple(sorted(ENTERTAINMENT_VALUES)),
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
    SearchGroup(
        label="Automotive",
        key="amenity",
        values=tuple(sorted(AUTOMOTIVE_AMENITY_VALUES)),
    ),
    SearchGroup(
        label="Automotive",
        key="shop",
        values=tuple(sorted(SHOP_AUTOMOTIVE_VALUES)),
    ),
    SearchGroup(
        label="Formazione",
        key="amenity",
        values=tuple(sorted(EDUCATION_AMENITY_VALUES)),
    ),
    SearchGroup(
        label="Formazione",
        key="office",
        values=tuple(sorted(OFFICE_EDUCATION_VALUES)),
    ),
)


class MorpheusFinder:
    def __init__(
        self,
        province_query: str = DEFAULT_PROVINCE_QUERY,
        reference_query: str = DEFAULT_REFERENCE_QUERY,
        output_file: str = DEFAULT_OUTPUT,
        limit: int = 0,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        target_categories: list[str] | None = None,
        max_distance_km: float | None = None,
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
        self.progress_callback = progress_callback
        self.target_categories: list[str] = (
            target_categories if target_categories is not None else DEFAULT_TARGET_CATEGORIES
        )
        self.max_distance_km: float = (
            max_distance_km if max_distance_km is not None else DEFAULT_MAX_DISTANCE_KM
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Morpheus/1.0 (B2B lead generation)",
                "Accept-Language": "it",
            }
        )

    # ── Progress ───────────────────────────────────────────────────────────────

    def _notify_progress(self, stage: str, percent: int, message: str, **extra: Any) -> None:
        if not self.progress_callback:
            return
        payload = {
            "stage": stage,
            "progress": max(0, min(100, int(percent))),
            "message": message,
        }
        payload.update(extra)
        self.progress_callback(payload)

    # ── Text utilities ─────────────────────────────────────────────────────────

    def _normalize_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        lowered = ascii_value.lower().strip()
        return re.sub(r"\s+", " ", lowered)

    # ── Geo ────────────────────────────────────────────────────────────────────

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

    # ── Composite scoring ──────────────────────────────────────────────────────

    def _composite_score(
        self,
        distance_km: float,
        has_website: bool,
        category: str,
    ) -> float:
        """Score composito [0, 1]: distanza(50%) + assenza sito(30%) + categoria target(20%)."""
        dist_norm = max(0.0, 1.0 - distance_km / self.max_distance_km)
        assenza_sito = 0.0 if has_website else 1.0
        cat_target = (
            1.0
            if (self.target_categories and category in self.target_categories)
            else 0.0
        )
        return 0.5 * dist_norm + 0.3 * assenza_sito + 0.2 * cat_target

    def _composite_priority(self, score: float) -> str:
        if score >= 0.75:
            return "ALTISSIMA"
        if score >= 0.55:
            return "ALTA"
        if score >= 0.35:
            return "MEDIA"
        if score >= 0.20:
            return "BASSA"
        return "MOLTO BASSA"

    # ── OSM tag helpers ────────────────────────────────────────────────────────

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
                if raw_value in ENTERTAINMENT_VALUES:
                    return "Intrattenimento", self._friendly_value(raw_value)
                if raw_value in AUTOMOTIVE_AMENITY_VALUES:
                    return "Automotive", self._friendly_value(raw_value)
                if raw_value in EDUCATION_AMENITY_VALUES:
                    return "Formazione", self._friendly_value(raw_value)
            elif key == "tourism" and raw_value in HOSPITALITY_VALUES:
                return "Ospitalita'", self._friendly_value(raw_value)
            elif key == "leisure" and raw_value in FITNESS_VALUES:
                return "Fitness & Sport", self._friendly_value(raw_value)
            elif key == "office":
                if raw_value in OFFICE_EDUCATION_VALUES:
                    return "Formazione", self._friendly_value(raw_value)
                if raw_value in OFFICE_VALUES:
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
                if raw_value in SHOP_AUTOMOTIVE_VALUES:
                    return "Automotive", self._friendly_value(raw_value)
                return "Negozi", self._friendly_value(raw_value)

        subtype = self._first_tag(tags, fallback_group.key) or fallback_group.label
        return fallback_group.label, self._friendly_value(subtype)

    def _compose_address(self, tags: dict[str, Any]) -> tuple[str, str]:
        address_full = self._first_tag(tags, "addr:full")
        city = self._first_tag(
            tags, "addr:city", "addr:town", "addr:village", "addr:hamlet", "addr:place"
        )
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

    # ── Dedup ──────────────────────────────────────────────────────────────────

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

    # ── Nominatim / Overpass ───────────────────────────────────────────────────

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
        for item in self._search_nominatim(self.province_query):
            osm_type = item.get("osm_type")
            osm_id = item.get("osm_id")
            item_type = self._normalize_text(item.get("type", ""))
            addresstype = self._normalize_text(item.get("addresstype", ""))
            display_name = self._normalize_text(item.get("display_name", ""))

            if osm_type not in {"relation", "way"} or not osm_id:
                continue
            if (
                "provincia" not in display_name
                and item_type not in {"county", "administrative"}
                and addresstype not in {"county", "state_district"}
            ):
                continue

            if osm_type == "relation":
                self.area_id = 3_600_000_000 + int(osm_id)
            else:
                self.area_id = 2_400_000_000 + int(osm_id)
            return

        raise RuntimeError(
            f"Impossibile determinare l'area OSM per: {self.province_query!r}. "
            "Verifica che la query sia una provincia riconoscibile su OpenStreetMap."
        )

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
            raise RuntimeError(
                f"Overpass non disponibile per {group.label}: {last_error}"
            ) from last_error
        raise RuntimeError(f"Overpass non disponibile per {group.label}")

    def _element_to_record(self, element: dict[str, Any], group: SearchGroup) -> dict[str, Any] | None:
        tags = element.get("tags", {})
        if not tags:
            return None

        # Salta attività esplicitamente chiuse/dismesse (solo tag certi, non generici)
        if (
            tags.get("disused") == "yes"
            or tags.get("closed") == "yes"
            or tags.get("shop") == "vacant"
            or tags.get("amenity") == "vacant"
            or tags.get("opening_hours") == "off"
            or tags.get("disused:amenity")
            or tags.get("disused:shop")
            or tags.get("disused:office")
            or tags.get("disused:tourism")
            or tags.get("disused:leisure")
        ):
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

        has_website = bool(website)
        comp_score = self._composite_score(distance_km, has_website, category)

        return {
            "Data Ricerca": self.timestamp,
            "Priorita'": self._composite_priority(comp_score),
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
            "Ha Sito Web": "SI" if has_website else "NO",
            "Opportunita' Web": self._website_opportunity(website, email),
            "Fonte": "OpenStreetMap / Overpass",
            "OSM URL": self._osm_url(element) or "N/D",
            "Note": "Verificare contatto commerciale e stato sito web",
            "Lat": round(float(lat), 6),
            "Lon": round(float(lon), 6),
            "_lat": float(lat),
            "_lon": float(lon),
            "_composite_score": comp_score,
        }

    # ── Foursquare ─────────────────────────────────────────────────────────────

    def _classify_foursquare(self, categories: list[dict[str, Any]]) -> tuple[str, str]:
        if not categories:
            return "Negozi", "N/D"
        primary_name = (categories[0].get("name") or "").strip()
        primary_lower = primary_name.lower()
        for keyword, our_cat in _FSQ_CATEGORY_MAP:
            if keyword in primary_lower:
                return our_cat, primary_name
        return "Negozi", primary_name or "N/D"

    def _foursquare_to_record(self, place: dict[str, Any]) -> dict[str, Any] | None:
        fsq_id = (place.get("fsq_id") or "").strip()
        name = (place.get("name") or "").strip()
        if not name or len(name) < 4:
            return None

        location = place.get("location") or {}
        lat = location.get("lat")
        lon = location.get("lng")
        if lat is None or lon is None:
            return None

        lat = float(lat)
        lon = float(lon)

        if self._normalize_text(name) in GENERIC_NAMES:
            return None

        categories_list = place.get("categories") or []
        category, subcategory = self._classify_foursquare(categories_list)

        website = (place.get("website") or "").strip()
        email = (place.get("email") or "").strip()
        phone = (place.get("tel") or "").strip()

        city = (
            location.get("locality")
            or location.get("town")
            or location.get("region")
            or ""
        ).strip()
        street = (location.get("address") or "").strip()
        postcode = (location.get("postcode") or "").strip()
        line_2 = " ".join(p for p in (postcode, city) if p).strip()
        address = ", ".join(p for p in (street, line_2) if p).strip() or "N/D"

        distance_km = self._haversine_km(
            self.reference_point["lat"],
            self.reference_point["lon"],
            lat,
            lon,
        )

        has_website = bool(website)
        comp_score = self._composite_score(distance_km, has_website, category)

        return {
            "Data Ricerca": self.timestamp,
            "Priorita'": self._composite_priority(comp_score),
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
            "Ha Sito Web": "SI" if has_website else "NO",
            "Opportunita' Web": self._website_opportunity(website, email),
            "Fonte": "Foursquare",
            "OSM URL": f"foursquare://{fsq_id}" if fsq_id else "N/D",
            "Note": "Lead da Foursquare — verificare dati",
            "Lat": round(lat, 6),
            "Lon": round(lon, 6),
            "_lat": lat,
            "_lon": lon,
            "_composite_score": comp_score,
        }

    def _fetch_foursquare(self, api_key: str) -> int:
        """Interroga Foursquare Places API e aggiunge i risultati a self.results."""
        radius_m = min(int(self.max_distance_km * 1000), 100_000)
        headers = {
            "Accept": "application/json",
            "Authorization": api_key,
        }
        params: dict[str, Any] = {
            "ll": f"{self.reference_point['lat']},{self.reference_point['lon']}",
            "radius": radius_m,
            "limit": 50,
            "fields": "fsq_id,name,location,categories,tel,website,email",
        }

        added = 0
        max_pages = 20  # cap a 1000 risultati

        for page in range(max_pages):
            try:
                response = self.session.get(
                    FSQ_SEARCH_URL,
                    headers=headers,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                print(f"    ! Foursquare errore (pagina {page + 1}): {exc}")
                break

            for place in payload.get("results", []):
                record = self._foursquare_to_record(place)
                if record:
                    self.results.append(record)
                    added += 1

            # Paginazione: cerca il cursore nel body o nel Link header
            next_cursor: str | None = payload.get("cursor")
            if not next_cursor:
                link = response.headers.get("Link", "")
                match = re.search(r"cursor=([^&>]+)", link)
                next_cursor = match.group(1) if match else None

            if not next_cursor:
                break
            params["cursor"] = next_cursor
            time.sleep(0.5)

        return added

    # ── Google Places (New) ────────────────────────────────────────────────────

    def _google_place_to_record(self, place: dict[str, Any]) -> dict[str, Any] | None:
        place_id = (place.get("id") or "").strip()

        display = place.get("displayName")
        name = ""
        if isinstance(display, dict):
            name = (display.get("text") or "").strip()
        if not name or len(name) < 4:
            return None

        if self._normalize_text(name) in GENERIC_NAMES:
            return None

        location = place.get("location") or {}
        lat = location.get("latitude")
        lon = location.get("longitude")
        if lat is None or lon is None:
            return None
        lat = float(lat)
        lon = float(lon)

        primary_type = (place.get("primaryType") or "").strip()
        category = _GOOGLE_TYPE_TO_CATEGORY.get(primary_type)
        if not category:
            for candidate in place.get("types") or []:
                if candidate in _GOOGLE_TYPE_TO_CATEGORY:
                    category = _GOOGLE_TYPE_TO_CATEGORY[candidate]
                    primary_type = primary_type or candidate
                    break
        if not category:
            return None

        primary_display = place.get("primaryTypeDisplayName")
        subcategory = ""
        if isinstance(primary_display, dict):
            subcategory = (primary_display.get("text") or "").strip()
        if not subcategory:
            subcategory = self._friendly_value(primary_type) if primary_type else "N/D"

        website = (place.get("websiteUri") or "").strip()
        phone = (place.get("nationalPhoneNumber") or "").strip()
        address = (place.get("formattedAddress") or "").strip() or "N/D"

        city = ""
        for comp in place.get("addressComponents") or []:
            types = comp.get("types") or []
            if "locality" in types or "postal_town" in types:
                city = (comp.get("longText") or "").strip()
                break
            if not city and "administrative_area_level_3" in types:
                city = (comp.get("longText") or "").strip()

        distance_km = self._haversine_km(
            self.reference_point["lat"],
            self.reference_point["lon"],
            lat,
            lon,
        )
        has_website = bool(website)
        comp_score = self._composite_score(distance_km, has_website, category)

        return {
            "Data Ricerca": self.timestamp,
            "Priorita'": self._composite_priority(comp_score),
            "Distanza da Vedano Olona (km)": f"{distance_km:.2f}",
            "Categoria": category,
            "Sottocategoria": subcategory,
            "Nome Attivita'": name,
            "Comune": city or "N/D",
            "Indirizzo": address,
            "Provincia": "Varese",
            "Telefono": phone or "N/D",
            "Email": "N/D",
            "Sito Web": website or "N/D",
            "Ha Sito Web": "SI" if has_website else "NO",
            "Opportunita' Web": self._website_opportunity(website, ""),
            "Fonte": "Google Places",
            "OSM URL": f"gplaces://{place_id}" if place_id else "N/D",
            "Note": "Lead da Google Places — verificare dati",
            "Lat": round(lat, 6),
            "Lon": round(lon, 6),
            "_lat": lat,
            "_lon": lon,
            "_composite_score": comp_score,
        }

    def _fetch_google_places(self, api_key: str) -> int:
        """Interroga Google Places API (New) e aggiunge i risultati a self.results.

        Free tier safety:
          - Usa searchNearby (1 call per categoria, 20 risultati max/call).
          - Field mask limitato a Essentials + Pro (no Enterprise SKU).
          - Hard cap su numero di call e risultati totali via env.
          - Aborta su 403 (chiave invalida) per evitare di bruciare quota.
        """
        if not GOOGLE_PLACES_ENABLED:
            print("  ! Google Places disabilitato via GOOGLE_PLACES_ENABLED=0")
            return 0

        radius_m = min(int(self.max_distance_km * 1000), GOOGLE_PLACES_MAX_RADIUS_M)
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": GOOGLE_PLACES_FIELD_MASK,
        }

        added = 0
        calls_used = 0
        total_results = 0

        for category, included_types in _GOOGLE_CATEGORY_TYPES.items():
            if calls_used >= GOOGLE_PLACES_MAX_CALLS:
                print(
                    f"    ! Google Places: cap call raggiunto ({GOOGLE_PLACES_MAX_CALLS}), stop"
                )
                break
            if total_results >= GOOGLE_PLACES_MAX_RESULTS:
                print(
                    f"    ! Google Places: cap risultati raggiunto ({GOOGLE_PLACES_MAX_RESULTS}), stop"
                )
                break

            body = {
                "includedTypes": list(included_types),
                "maxResultCount": GOOGLE_PLACES_PAGE_SIZE,
                "languageCode": "it",
                "regionCode": "IT",
                "locationRestriction": {
                    "circle": {
                        "center": {
                            "latitude": self.reference_point["lat"],
                            "longitude": self.reference_point["lon"],
                        },
                        "radius": float(radius_m),
                    }
                },
            }

            try:
                response = self.session.post(
                    GOOGLE_PLACES_NEARBY_URL,
                    headers=headers,
                    json=body,
                    timeout=30,
                )
                calls_used += 1

                if response.status_code == 429:
                    print(f"    ! Google Places: rate limit su {category}, pausa 5s")
                    time.sleep(5)
                    continue
                if response.status_code in {401, 403}:
                    print(
                        f"    ! Google Places: chiave rifiutata ({response.status_code}), abort"
                    )
                    break
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                print(f"    ! Google Places errore su {category}: {exc}")
                continue

            places = payload.get("places") or []
            cat_added = 0
            for place in places:
                record = self._google_place_to_record(place)
                if record is None:
                    continue
                self.results.append(record)
                cat_added += 1
                total_results += 1
                if total_results >= GOOGLE_PLACES_MAX_RESULTS:
                    break
            added += cat_added
            print(f"    -> Google Places {category}: {cat_added} aggiunti")
            time.sleep(0.3)

        print(
            f"  -> Google Places: {added} totali "
            f"(calls: {calls_used}/{GOOGLE_PLACES_MAX_CALLS}, "
            f"results: {total_results}/{GOOGLE_PLACES_MAX_RESULTS})"
        )
        return added

    # ── Dedup / sort / output ──────────────────────────────────────────────────

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
                -item.get("_composite_score", 0.0),
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

        fsq_count = sum(1 for item in self.results if item.get("Fonte") == "Foursquare")
        gplaces_count = sum(1 for item in self.results if item.get("Fonte") == "Google Places")
        osm_count = len(self.results) - fsq_count - gplaces_count

        print("\n" + "=" * 78)
        print("RIEPILOGO")
        print("=" * 78)
        print(
            f"Totale attivita': {len(self.results)}"
            f"  (OSM: {osm_count}, Foursquare: {fsq_count}, Google: {gplaces_count})"
        )
        print(f"Senza sito web: {without_site}")
        print(f"Con sito web:   {len(self.results) - without_site}")
        print(
            f"Centro ranking: {self.reference_point['name']} "
            f"({self.reference_point['lat']:.4f}, {self.reference_point['lon']:.4f})"
        )
        if self.target_categories:
            print(f"Categorie target: {', '.join(self.target_categories)}")
        print(f"Distanza massima: {self.max_distance_km:.0f} km")
        print("\nPer priorita' composita:")
        for label in ("ALTISSIMA", "ALTA", "MEDIA", "BASSA", "MOLTO BASSA"):
            print(f"  - {label:<13} {per_priority.get(label, 0)}")
        if self.failed_groups:
            print("\nGruppi con query non completata:")
            for group in self.failed_groups:
                print(f"  - {group}")

    def run(self) -> None:
        print("\n" + "=" * 78)
        print("MORPHEUS — RACCOLTA LEAD OSM/OVERPASS + FOURSQUARE + GOOGLE PLACES")
        print("=" * 78)
        print(f"Avvio: {self.timestamp}")

        print(f"\n[1/6] Geocodifico il centro di priorita': {self.reference_query}")
        self._notify_progress("geocode", 5, f"Geocodifico il centro: {self.reference_query}")
        self.geocode_reference_point()

        print(f"[2/6] Individuo l'area OSM della provincia: {self.province_query}")
        self._notify_progress("resolve_area", 10, f"Individuo l'area OSM: {self.province_query}")
        self.resolve_area_id()

        print("[3/6] Raccolgo attivita' commerciali via Overpass")
        for index, group in enumerate(SEARCH_GROUPS, start=1):
            print(f"  - Query {index}/{len(SEARCH_GROUPS)}: {group.label}")
            query_progress = 15 + int(((index - 1) / len(SEARCH_GROUPS)) * 50)
            self._notify_progress(
                "fetch_group",
                query_progress,
                f"Query {index}/{len(SEARCH_GROUPS)}: {group.label}",
                current_group=group.label,
                current_index=index,
                total_groups=len(SEARCH_GROUPS),
            )
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
            self._notify_progress(
                "fetch_group_done",
                15 + int((index / len(SEARCH_GROUPS)) * 50),
                f"{group.label}: {added} elementi utili",
                current_group=group.label,
                current_index=index,
                total_groups=len(SEARCH_GROUPS),
                added=added,
            )
            time.sleep(1)

        print("[4/6] Integro dati Foursquare Places")
        fsq_key = os.environ.get("FSQ_API_KEY", "").strip()
        if fsq_key:
            self._notify_progress("foursquare", 68, "Integro dati Foursquare...")
            fsq_added = self._fetch_foursquare(fsq_key)
            print(f"  -> Foursquare: {fsq_added} attivita' aggiunte")
        else:
            print("  ! FSQ_API_KEY non impostata, skip Foursquare")
        self._notify_progress("foursquare_done", 72, "Foursquare completato")

        print("[5/6] Integro dati Google Places")
        gkey = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
        if gkey:
            self._notify_progress("google_places", 74, "Integro dati Google Places...")
            g_added = self._fetch_google_places(gkey)
            print(f"  -> Google Places: {g_added} attivita' aggiunte")
        else:
            print("  ! GOOGLE_PLACES_API_KEY non impostata, skip Google Places")
        self._notify_progress("google_places_done", 80, "Google Places completato")

        self._notify_progress("dedupe", 84, "Pulisco duplicati e ordino i lead")
        self.cleanup_duplicates()
        self.sort_results()

        print(f"[6/6] Salvo il CSV ordinato per score in {project_relative(self.output_file)}")
        self._notify_progress("save_csv", 90, "Salvo il CSV del popolamento")
        self.save_csv()
        self._notify_progress("summary", 97, "Calcolo il riepilogo finale")
        self.print_summary()
        self._notify_progress(
            "done",
            100,
            f"Popolamento completato: {len(self.results)} attivita' trovate",
            total_results=len(self.results),
        )
        print(
            "\nCSV pronto. I lead sono ordinati per score composito"
            " (distanza + assenza sito + categoria)."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Morpheus: trova attivita' commerciali in una provincia, ordinate per score composito."
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
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        help=(
            "Categorie target per lo scoring (es. Ristorazione Artigiani). "
            "Default: da SCORING_CATEGORIES env."
        ),
    )
    parser.add_argument(
        "--max-distance",
        type=float,
        default=None,
        help=f"Distanza massima in km per la normalizzazione (default: {DEFAULT_MAX_DISTANCE_KM}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    finder = MorpheusFinder(
        province_query=args.province,
        reference_query=args.reference,
        output_file=args.output,
        limit=args.limit,
        target_categories=args.categories,
        max_distance_km=args.max_distance,
    )
    finder.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
