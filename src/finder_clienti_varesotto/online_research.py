#!/usr/bin/env python3
"""
Arricchisce le attivita del CSV cercando informazioni online.

Output:
- sito ufficiale trovato
- descrizione base dell'attivita
- contatti e social rilevati dal sito
- pagine terze parti / recensioni individuate dalla ricerca
- snippet utili per fare analisi manuale successiva
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .paths import (
    DEFAULT_COMPANY_RESEARCH_OUTPUT,
    DEFAULT_COMPANY_RESEARCH_MERGED_OUTPUT,
    DEFAULT_COMPANY_RESEARCH_SUMMARY,
    DEFAULT_OSM_OUTPUT,
    ensure_parent_dir,
    project_relative,
)


DUCKDUCKGO_HTML_URL = "https://search.brave.com/search"
OSM_API_BASE_URL = "https://api.openstreetmap.org/api/0.6"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
OSM_USER_AGENT = "VaresottoClientFinder/2.0 (Codex)"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

PRIORITY_ORDER = {
    "ALTISSIMA": 0,
    "ALTA": 1,
    "MEDIA": 2,
    "BASSA": 3,
    "MOLTO BASSA": 4,
}

SEARCH_FIELDNAMES = [
    "Data Ricerca",
    "Nome Attivita",
    "Comune",
    "Categoria",
    "Sottocategoria",
    "Priorita Distanza",
    "Distanza KM",
    "Indirizzo",
    "Telefono CSV",
    "Email CSV",
    "Sito Web CSV",
    "OSM URL",
    "OSM Nome Verificato",
    "OSM Comune Verificato",
    "OSM Indirizzo Verificato",
    "OSM Tipo Verificato",
    "OSM Coordinate",
    "Query Principale",
    "Query Recensioni",
    "Sito Ufficiale Trovato",
    "Titolo Sito",
    "Descrizione Sito",
    "H1 Sito",
    "Telefono Trovato Online",
    "Email Trovata Online",
    "Link Social",
    "Link Utili",
    "Google Maps URL",
    "Facebook URL",
    "Tripadvisor URL",
    "Tripadvisor Snippet",
    "Tripadvisor Rating",
    "Tripadvisor Review Count",
    "Tripadvisor Price Range",
    "Tripadvisor Cuisines",
    "Tripadvisor Status",
    "TheFork URL",
    "TheFork Snippet",
    "TheFork Rating",
    "TheFork Review Count",
    "TheFork Price Range",
    "TheFork Cuisines",
    "TheFork Status",
    "Directory Fonte",
    "Directory URL",
    "Directory Titolo",
    "Directory Descrizione",
    "Directory Telefono",
    "Directory Email",
    "Directory Indirizzo",
    "Directory Sito",
    "Directory Categoria",
    "Directory Rating",
    "Directory Review Count",
    "Directory Review Summary",
    "Directory Review Keywords",
    "Directory Status",
    "Review Fonte",
    "Review URL",
    "Review Rating",
    "Review Count",
    "Review Summary",
    "Review Keywords",
    "Review Status",
    "Confidenza Match",
    "Pagine Terze Parti",
    "Snippet Ricerca",
    "Cosa Fanno",
    "Segnali Digitali",
    "Elementi Da Verificare",
    "Errore Ricerca",
]

OFFICIAL_SITE_BLOCKLIST = (
    "facebook.com",
    "instagram.com",
    "tripadvisor.",
    "restaurantguru.",
    "thefork.",
    "paginegialle.",
    "virgilio.",
    "justeat.",
    "deliveroo.",
    "glovo.",
    "sluurpy.",
    "foursquare.",
    "tiktok.com",
    "linkedin.com",
    "youtube.com",
    "google.",
    "g.co",
    "consent.google.",
    "maps.google.",
    "tuttocitta.",
    "trova-aperto.",
    "lamigliorepizzeria.",
    "misterimprese.",
    "firmania.",
    "infobel.",
    "reteimprese.",
    "paginebianche.",
    "yelp.",
    "aziende-info.",
    "aziendeitalia.",
)

THIRD_PARTY_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "tripadvisor.",
    "restaurantguru.",
    "thefork.",
    "paginegialle.",
    "virgilio.",
    "justeat.",
    "deliveroo.",
    "glovo.",
    "sluurpy.",
    "foursquare.",
    "google.com",
    "g.co",
    "trova-aperto.",
    "lamigliorepizzeria.",
    "misterimprese.",
    "firmania.",
    "infobel.",
    "reteimprese.",
    "paginebianche.",
    "yelp.",
    "aziende-info.",
    "aziendeitalia.",
)

SOCIAL_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "linkedin.com",
)

USEFUL_LINK_KEYWORDS = (
    "menu",
    "prenot",
    "booking",
    "servizi",
    "listino",
    "trattamenti",
    "shop",
    "catalog",
    "ordine",
    "contatti",
)

MAPS_DOMAINS = ("google.", "g.co")
FACEBOOK_DOMAINS = ("facebook.com",)
TRIPADVISOR_DOMAINS = ("tripadvisor.",)
THEFORK_DOMAINS = ("thefork.",)
RESTAURANTGURU_DOMAINS = ("restaurantguru.",)
RETEIMPRESE_DOMAINS = ("reteimprese.",)
DIRECTORY_DOMAINS = (
    "restaurantguru.",
    "paginegialle.",
    "virgilio.",
    "reteimprese.",
    "trova-aperto.",
    "lamigliorepizzeria.",
    "misterimprese.",
    "firmania.",
    "infobel.",
    "paginebianche.",
)
GENERIC_BUSINESS_TOKENS = {
    "bar",
    "san",
    "santa",
    "ristorante",
    "farmacia",
    "azienda",
    "negozio",
    "centro",
    "pub",
    "hotel",
    "pizzeria",
    "trattoria",
    "osteria",
    "caffe",
    "caffe'",
}
ADDRESS_STOPWORDS = {
    "via",
    "viale",
    "piazza",
    "corso",
    "vicolo",
    "largo",
    "strada",
    "lungo",
    "piazzale",
    "dei",
    "delle",
    "della",
    "del",
}
LISTING_HINTS = (
    "/ricerca/",
    "/cat/",
    "/restaurants-",
    "/restaurantsnear-",
    "/activities-",
    "/search",
)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_value.lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def ambiguous_business(row: dict[str, str]) -> bool:
    name_tokens = normalize_text(row_value(row, "Nome Attivita'")).split()
    if not row_value(row, "Comune"):
        return True
    if len(name_tokens) <= 1:
        return True
    if name_tokens[:1] in (["san"], ["santa"]):
        return True
    return False


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


def osm_headers() -> dict[str, str]:
    return {
        "User-Agent": OSM_USER_AGENT,
        "Accept-Language": "it",
        "Referer": "https://www.openstreetmap.org/",
    }


def parse_osm_reference(osm_url: str) -> tuple[str, str]:
    match = re.search(r"/(node|way|relation)/(\d+)", osm_url or "")
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def average_coordinates(elements: list[dict[str, Any]]) -> tuple[str, str]:
    points = [
        (item.get("lat"), item.get("lon"))
        for item in elements
        if isinstance(item, dict) and item.get("lat") is not None and item.get("lon") is not None
    ]
    if not points:
        return "", ""
    lat = sum(point[0] for point in points) / len(points)
    lon = sum(point[1] for point in points) / len(points)
    return f"{lat:.7f}", f"{lon:.7f}"


def fetch_osm_enrichment(session: requests.Session, row: dict[str, str]) -> dict[str, str]:
    profile = {
        "name": "",
        "city": "",
        "address": "",
        "type": "",
        "lat": "",
        "lon": "",
        "phone": "",
        "email": "",
        "website": "",
    }
    osm_type, osm_id = parse_osm_reference(row_value(row, "OSM URL"))
    if not osm_type or not osm_id:
        return profile

    if osm_type == "node":
        endpoint = f"{OSM_API_BASE_URL}/node/{osm_id}.json"
    elif osm_type == "way":
        endpoint = f"{OSM_API_BASE_URL}/way/{osm_id}/full.json"
    else:
        return profile

    try:
        response = session.get(endpoint, headers=osm_headers(), timeout=25)
        response.raise_for_status()
    except requests.RequestException:
        return profile

    payload = response.json()
    elements = payload.get("elements", [])
    target = next(
        (
            item for item in elements
            if isinstance(item, dict) and item.get("type") == osm_type and str(item.get("id")) == osm_id
        ),
        {},
    )
    tags = target.get("tags", {}) if isinstance(target, dict) else {}
    if osm_type == "node":
        lat = str(target.get("lat", "")) if isinstance(target, dict) else ""
        lon = str(target.get("lon", "")) if isinstance(target, dict) else ""
    else:
        lat, lon = average_coordinates(elements)

    city = (
        clean_value(tags.get("addr:city"))
        or clean_value(tags.get("addr:town"))
        or clean_value(tags.get("addr:village"))
        or clean_value(tags.get("addr:hamlet"))
        or clean_value(tags.get("addr:place"))
    )
    street = clean_value(tags.get("addr:street"))
    house_number = clean_value(tags.get("addr:housenumber"))
    address_parts = [street, house_number, city]
    address = ", ".join(part for part in address_parts if part)

    if lat and lon and not city:
        try:
            reverse_response = session.get(
                NOMINATIM_REVERSE_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "jsonv2",
                    "zoom": 18,
                    "addressdetails": 1,
                },
                headers=osm_headers(),
                timeout=25,
            )
            reverse_response.raise_for_status()
            reverse_payload = reverse_response.json()
            address_data = reverse_payload.get("address", {})
            city = (
                clean_value(address_data.get("city"))
                or clean_value(address_data.get("town"))
                or clean_value(address_data.get("village"))
                or clean_value(address_data.get("hamlet"))
            )
            if not address:
                road = clean_value(address_data.get("road"))
                number = clean_value(address_data.get("house_number"))
                address = ", ".join(part for part in [road, number, city] if part)
        except requests.RequestException:
            pass

    profile.update(
        {
            "name": clean_value(tags.get("name")),
            "city": city,
            "address": address,
            "type": clean_value(tags.get("amenity") or tags.get("shop") or tags.get("tourism") or tags.get("office") or tags.get("craft")),
            "lat": lat,
            "lon": lon,
            "phone": clean_value(tags.get("phone") or tags.get("contact:phone") or tags.get("mobile") or tags.get("contact:mobile")),
            "email": clean_value(tags.get("email") or tags.get("contact:email")),
            "website": clean_value(tags.get("website") or tags.get("contact:website")),
        }
    )
    return profile


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    output_path = ensure_parent_dir(path)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def merged_rows(
    source_rows: list[dict[str, str]],
    research_rows: list[dict[str, str]],
) -> tuple[list[str], list[dict[str, str]]]:
    appended_fields = [
        "Ricerca Sito Ufficiale",
        "Ricerca Titolo Sito",
        "Ricerca Descrizione Sito",
        "Ricerca Telefono Online",
        "Ricerca Email Online",
        "Ricerca OSM Comune Verificato",
        "Ricerca OSM Indirizzo Verificato",
        "Ricerca OSM Tipo Verificato",
        "Ricerca Link Social",
        "Ricerca Link Utili",
        "Ricerca Google Maps URL",
        "Ricerca Facebook URL",
        "Ricerca Tripadvisor URL",
        "Ricerca Tripadvisor Rating",
        "Ricerca Tripadvisor Review Count",
        "Ricerca Tripadvisor Price Range",
        "Ricerca Tripadvisor Cuisines",
        "Ricerca Tripadvisor Status",
        "Ricerca TheFork URL",
        "Ricerca TheFork Rating",
        "Ricerca TheFork Review Count",
        "Ricerca TheFork Price Range",
        "Ricerca TheFork Cuisines",
        "Ricerca TheFork Status",
        "Ricerca Directory Fonte",
        "Ricerca Directory URL",
        "Ricerca Directory Titolo",
        "Ricerca Directory Descrizione",
        "Ricerca Directory Telefono",
        "Ricerca Directory Email",
        "Ricerca Directory Indirizzo",
        "Ricerca Directory Sito",
        "Ricerca Directory Categoria",
        "Ricerca Directory Rating",
        "Ricerca Directory Review Count",
        "Ricerca Directory Review Summary",
        "Ricerca Directory Review Keywords",
        "Ricerca Directory Status",
        "Ricerca Review Fonte",
        "Ricerca Review URL",
        "Ricerca Review Rating",
        "Ricerca Review Count",
        "Ricerca Review Summary",
        "Ricerca Review Keywords",
        "Ricerca Review Status",
        "Ricerca Confidenza Match",
        "Ricerca Pagine Terze Parti",
        "Ricerca Snippet",
        "Ricerca Cosa Fanno",
        "Ricerca Segnali Digitali",
        "Ricerca Da Verificare",
        "Ricerca Errore",
    ]

    fieldnames = list(source_rows[0].keys()) + appended_fields if source_rows else appended_fields
    rows = []
    for source, research in zip(source_rows, research_rows):
        merged = dict(source)
        merged.update(
            {
                "Ricerca Sito Ufficiale": research["Sito Ufficiale Trovato"],
                "Ricerca Titolo Sito": research["Titolo Sito"],
                "Ricerca Descrizione Sito": research["Descrizione Sito"],
                "Ricerca Telefono Online": research["Telefono Trovato Online"],
                "Ricerca Email Online": research["Email Trovata Online"],
                "Ricerca OSM Comune Verificato": research["OSM Comune Verificato"],
                "Ricerca OSM Indirizzo Verificato": research["OSM Indirizzo Verificato"],
                "Ricerca OSM Tipo Verificato": research["OSM Tipo Verificato"],
                "Ricerca Link Social": research["Link Social"],
                "Ricerca Link Utili": research["Link Utili"],
                "Ricerca Google Maps URL": research["Google Maps URL"],
                "Ricerca Facebook URL": research["Facebook URL"],
                "Ricerca Tripadvisor URL": research["Tripadvisor URL"],
                "Ricerca Tripadvisor Rating": research["Tripadvisor Rating"],
                "Ricerca Tripadvisor Review Count": research["Tripadvisor Review Count"],
                "Ricerca Tripadvisor Price Range": research["Tripadvisor Price Range"],
                "Ricerca Tripadvisor Cuisines": research["Tripadvisor Cuisines"],
                "Ricerca Tripadvisor Status": research["Tripadvisor Status"],
                "Ricerca TheFork URL": research["TheFork URL"],
                "Ricerca TheFork Rating": research["TheFork Rating"],
                "Ricerca TheFork Review Count": research["TheFork Review Count"],
                "Ricerca TheFork Price Range": research["TheFork Price Range"],
                "Ricerca TheFork Cuisines": research["TheFork Cuisines"],
                "Ricerca TheFork Status": research["TheFork Status"],
                "Ricerca Directory Fonte": research["Directory Fonte"],
                "Ricerca Directory URL": research["Directory URL"],
                "Ricerca Directory Titolo": research["Directory Titolo"],
                "Ricerca Directory Descrizione": research["Directory Descrizione"],
                "Ricerca Directory Telefono": research["Directory Telefono"],
                "Ricerca Directory Email": research["Directory Email"],
                "Ricerca Directory Indirizzo": research["Directory Indirizzo"],
                "Ricerca Directory Sito": research["Directory Sito"],
                "Ricerca Directory Categoria": research["Directory Categoria"],
                "Ricerca Directory Rating": research["Directory Rating"],
                "Ricerca Directory Review Count": research["Directory Review Count"],
                "Ricerca Directory Review Summary": research["Directory Review Summary"],
                "Ricerca Directory Review Keywords": research["Directory Review Keywords"],
                "Ricerca Directory Status": research["Directory Status"],
                "Ricerca Review Fonte": research["Review Fonte"],
                "Ricerca Review URL": research["Review URL"],
                "Ricerca Review Rating": research["Review Rating"],
                "Ricerca Review Count": research["Review Count"],
                "Ricerca Review Summary": research["Review Summary"],
                "Ricerca Review Keywords": research["Review Keywords"],
                "Ricerca Review Status": research["Review Status"],
                "Ricerca Confidenza Match": research["Confidenza Match"],
                "Ricerca Pagine Terze Parti": research["Pagine Terze Parti"],
                "Ricerca Snippet": research["Snippet Ricerca"],
                "Ricerca Cosa Fanno": research["Cosa Fanno"],
                "Ricerca Segnali Digitali": research["Segnali Digitali"],
                "Ricerca Da Verificare": research["Elementi Da Verificare"],
                "Ricerca Errore": research["Errore Ricerca"],
            }
        )
        rows.append(merged)
    return fieldnames, rows


def safe_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    return f"https://{url.lstrip('/')}"


def decode_duckduckgo_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


def shorten(text: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def build_query(row: dict[str, str]) -> str:
    parts = [
        row_value(row, "Nome Attivita'"),
        row_value(row, "Comune"),
        row_value(row, "Sottocategoria"),
        row_value(row, "Categoria"),
        "Varese",
    ]
    if not row_value(row, "Comune"):
        parts.insert(2, row_value(row, "Indirizzo"))
    return " ".join(part for part in parts if part)


def dedupe_preserve(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def business_name_tokens(row: dict[str, str]) -> list[str]:
    tokens = normalize_text(row_value(row, "Nome Attivita'")).split()
    return [
        token
        for token in tokens
        if len(token) > 2 and token not in GENERIC_BUSINESS_TOKENS
    ]


def location_tokens(row: dict[str, str]) -> list[str]:
    tokens = []
    business_tokens = set(normalize_text(row_value(row, "Nome Attivita'")).split())
    tokens.extend(normalize_text(row_value(row, "Comune")).split())
    tokens.extend(normalize_text(row_value(row, "Provincia")).split())
    tokens.extend(
        token
        for token in normalize_text(row_value(row, "Indirizzo")).split()
        if len(token) > 2
        and token not in ADDRESS_STOPWORDS
        and token not in business_tokens
    )
    return dedupe_preserve(tokens)


def result_text(result: dict[str, str]) -> str:
    return normalize_text(
        " ".join(
            part
            for part in [
                result.get("title", ""),
                result.get("snippet", ""),
                result.get("url", ""),
            ]
            if part
        )
    )


def is_listing_result(result: dict[str, str]) -> bool:
    haystack = f"{result.get('url', '').lower()} {result.get('title', '').lower()}"
    return any(hint in haystack for hint in LISTING_HINTS)


def score_result(row: dict[str, str], result: dict[str, str]) -> int:
    haystack = result_text(result)
    score = 0

    name_tokens = business_name_tokens(row)
    full_name = normalize_text(row_value(row, "Nome Attivita'"))
    matched_name_tokens = sum(1 for token in name_tokens if token in haystack)
    score += matched_name_tokens * 4
    if full_name and full_name in haystack:
        score += 4

    matched_location_tokens = sum(1 for token in location_tokens(row)[:4] if token in haystack)
    score += matched_location_tokens * 2

    domain = result.get("domain", "")
    if any(blocked in domain for blocked in OFFICIAL_SITE_BLOCKLIST):
        score -= 2

    if is_listing_result(result):
        score -= 3

    if name_tokens and matched_name_tokens == 0:
        score -= 5
    if ambiguous_business(row) and matched_location_tokens == 0:
        score -= 6

    return score


def content_match_score(row: dict[str, str], text: str) -> tuple[int, int]:
    haystack = normalize_text(text)
    name_matches = sum(1 for token in business_name_tokens(row) if token in haystack)
    location_matches = sum(1 for token in location_tokens(row)[:4] if token in haystack)
    return name_matches, location_matches


def slugify_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    compact = ascii_value.replace("'", "")
    compact = re.sub(r"[^A-Za-z0-9]+", "-", compact).strip("-")
    return compact


def guess_restaurantguru_result(
    session: requests.Session,
    row: dict[str, str],
    delay_seconds: float,
) -> dict[str, str]:
    if row_value(row, "Categoria") != "Ristorazione":
        return {}

    city = row_value(row, "Comune")
    name = row_value(row, "Nome Attivita'")
    if not name or not city:
        return {}

    name_slug = slugify_component(name)
    city_slug = slugify_component(city)
    subtype_slug = slugify_component(row_value(row, "Sottocategoria"))
    prefixes = ["", subtype_slug]
    if subtype_slug == "Ristorante":
        prefixes.extend(["Pizzeria", "Ristorante-Bar-Pizzeria"])
    elif subtype_slug == "Bar":
        prefixes.extend(["Pub"])
    elif subtype_slug == "Pub":
        prefixes.extend(["Bar"])

    candidates = []
    for prefix in dedupe_preserve(prefixes):
        pieces = [prefix, name_slug, city_slug] if prefix else [name_slug, city_slug]
        slug = "-".join(part for part in pieces if part)
        if not slug:
            continue
        candidates.append(f"https://restaurantguru.it/{slug}")

    for url in dedupe_preserve(candidates):
        try:
            response = session.get(url, timeout=25, allow_redirects=True)
        except requests.RequestException:
            continue
        if response.status_code != 200:
            continue
        page_text = re.sub(r"\s+", " ", response.text)
        if "prezzi e recensioni" not in page_text.lower():
            continue
        name_matches, location_matches = content_match_score(row, page_text[:2000])
        if name_matches == 0:
            continue
        if ambiguous_business(row) and location_matches == 0:
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        description_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
            "meta", attrs={"property": "og:description"}
        )
        time.sleep(delay_seconds)
        return {
            "title": shorten(soup.title.get_text(" ", strip=True), 140) if soup.title else "",
            "url": response.url,
            "snippet": shorten(description_tag.get("content", ""), 240) if description_tag else "",
            "domain": domain_from_url(response.url),
        }
    return {}


def search_duckduckgo(
    session: requests.Session,
    query: str,
    max_results: int,
) -> list[dict[str, str]]:
    for attempt in range(3):
        try:
            response = session.get(
                DUCKDUCKGO_HTML_URL,
                params={"q": query, "source": "web"},
                timeout=25,
            )
        except requests.RequestException:
            if attempt == 2:
                return []
            time.sleep(2.0 + attempt)
            continue

        if response.status_code == 403:
            if attempt == 2:
                return []
            time.sleep(4.0 + attempt * 2)
            continue
        if response.status_code >= 400:
            if attempt == 2:
                return []
            time.sleep(2.0 + attempt)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for result in soup.select("div.snippet[data-type='web']"):
            link = result.select_one("a.l1[href]") or result.select_one("a[href]")
            if not link:
                continue
            url = decode_duckduckgo_url(link.get("href", ""))
            if not url:
                continue
            title_node = result.select_one(".title") or link
            title = shorten(title_node.get_text(" ", strip=True), 140)
            snippet_node = result.select_one(".generic-snippet .content") or result.select_one(".content")
            snippet = shorten(snippet_node.get_text(" ", strip=True), 240) if snippet_node else ""
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "domain": domain_from_url(url),
                }
            )
            if len(results) >= max_results:
                break

        if results or attempt == 2:
            return results
        time.sleep(1.0 + attempt)
    return []


def choose_official_site(row: dict[str, str], results: list[dict[str, str]]) -> str:
    csv_site = safe_url(row_value(row, "Sito Web"))
    if csv_site:
        return csv_site

    best_url = ""
    best_score = 0
    for result in results:
        domain = result["domain"]
        if any(blocked in domain for blocked in OFFICIAL_SITE_BLOCKLIST):
            continue
        current_score = score_result(row, result)
        if current_score > best_score:
            best_score = current_score
            best_url = result["url"]
    return best_url if best_score >= 4 else ""


def collect_third_party_links(results: list[dict[str, str]]) -> list[str]:
    links = []
    seen = set()
    for result in results:
        domain = result["domain"]
        if not any(item in domain for item in THIRD_PARTY_DOMAINS):
            continue
        url = result["url"]
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
    return links


def best_result_for_domains(
    row: dict[str, str],
    results: list[dict[str, str]],
    domains: tuple[str, ...],
    min_score: int = 1,
) -> dict[str, str]:
    best_result: dict[str, str] = {}
    best_score = -999
    for result in results:
        domain = result["domain"]
        if not any(item in domain for item in domains):
            continue
        current_score = score_result(row, result)
        if current_score > best_score:
            best_result = result
            best_score = current_score
    if best_score < min_score:
        return {}
    return best_result


def pipe_join(values: list[str], limit: int | None = None) -> str:
    cleaned = [clean_value(value) for value in values if clean_value(value)]
    unique = dedupe_preserve(cleaned)
    if limit is not None:
        unique = unique[:limit]
    return " | ".join(unique)


def confidence_label(score: int) -> str:
    if score >= 10:
        return "ALTA"
    if score >= 6:
        return "MEDIA"
    if score >= 2:
        return "BASSA"
    return "DA_VERIFICARE"


def normalize_rating(value: str) -> str:
    if not value:
        return ""
    return value.replace(",", ".").strip()


def extract_review_metrics(text: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return "", ""
    if re.search(r"nessuna recensione", normalized, re.IGNORECASE):
        return "0", "0"

    rating = ""
    review_count = ""

    rating_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:su|/)\s*5", normalized, re.IGNORECASE)
    if rating_match:
        rating = normalize_rating(rating_match.group(1))

    for pattern in (
        r"(\d+)\s+recensioni",
        r"(\d+)\s+voti",
        r"recensioni(?:\s+dei\s+visitatori)?\s*/\s*(\d+)",
    ):
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            review_count = match.group(1)
            break

    return rating, review_count


def extract_price_range(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return ""
    for pattern in (
        r"Fascia prezzo a persona\s*([€$£0-9A-Za-z.,\-– ]{3,30})",
        r"price per person:\s*([€$£0-9A-Za-z.,\-– ]{3,30})",
    ):
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return shorten(match.group(1).strip(), 40)
    return ""


def extract_address_from_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return ""
    match = re.search(
        r"((?:Via|Viale|Piazza|Corso|Vicolo|Largo|Strada)\s+[A-Z0-9][^|;]{5,120})",
        normalized,
    )
    if not match:
        return ""
    return shorten(match.group(1).strip(" ,."), 160)


def format_jsonld_address(value: Any) -> str:
    if isinstance(value, str):
        return shorten(value, 160)
    if not isinstance(value, dict):
        return ""
    parts = [
        first_jsonld_value(value, "streetAddress"),
        first_jsonld_value(value, "postalCode"),
        first_jsonld_value(value, "addressLocality"),
        first_jsonld_value(value, "addressRegion"),
        first_jsonld_value(value, "addressCountry"),
    ]
    return pipe_join(parts)


def structured_business_profile(soup: BeautifulSoup) -> dict[str, str]:
    candidate: dict[str, Any] = {}
    accepted_types = {
        "LocalBusiness",
        "Restaurant",
        "FoodEstablishment",
        "Store",
        "MedicalBusiness",
        "Organization",
    }
    for node in parse_jsonld_objects(soup):
        if not isinstance(node, dict):
            continue
        if any(jsonld_has_type(node, target) for target in accepted_types):
            candidate = node
            break
        if any(key in node for key in ("telephone", "address", "aggregateRating")):
            candidate = node
            break

    if not candidate:
        return {}

    aggregate = candidate.get("aggregateRating", {})
    address = format_jsonld_address(candidate.get("address"))

    return {
        "name": first_jsonld_value(candidate, "name"),
        "telephone": first_jsonld_value(candidate, "telephone"),
        "email": first_jsonld_value(candidate, "email"),
        "url": first_jsonld_value(candidate, "url"),
        "address": address,
        "category": first_jsonld_value(candidate, "@type"),
        "rating": first_jsonld_value(aggregate, "ratingValue") if isinstance(aggregate, dict) else "",
        "review_count": first_jsonld_value(aggregate, "reviewCount") if isinstance(aggregate, dict) else "",
        "price_range": first_jsonld_value(candidate, "priceRange"),
    }


def preferred_external_website(soup: BeautifulSoup, base_url: str) -> str:
    base_domain = domain_from_url(base_url)
    preferred = []
    generic = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        absolute = urljoin(base_url, href)
        candidate_domain = domain_from_url(absolute)
        if not candidate_domain or candidate_domain == base_domain:
            continue
        if any(item in candidate_domain for item in THIRD_PARTY_DOMAINS + SOCIAL_DOMAINS):
            continue
        label = normalize_text(anchor.get_text(" ", strip=True))
        if any(keyword in label for keyword in ("sito", "website", "web", "visita", "home")):
            preferred.append(absolute)
        else:
            generic.append(absolute)
    options = preferred or generic
    return options[0] if options else ""


def empty_directory_profile(result: dict[str, str]) -> dict[str, str]:
    rating, review_count = extract_review_metrics(result.get("snippet", ""))
    return {
        "source": "",
        "url": result.get("url", ""),
        "title": "",
        "description": "",
        "phone": "",
        "email": "",
        "address": "",
        "website": "",
        "category": "",
        "rating": rating,
        "review_count": review_count,
        "review_summary": shorten(result.get("snippet", ""), 260) if result else "",
        "review_keywords": "",
        "status": "LINK_FOUND" if result else "NOT_FOUND",
    }


def empty_review_profile(result: dict[str, str]) -> dict[str, str]:
    rating, review_count = extract_review_metrics(result.get("snippet", ""))
    return {
        "source": "",
        "url": result.get("url", ""),
        "rating": rating,
        "review_count": review_count,
        "summary": shorten(result.get("snippet", ""), 260) if result else "",
        "keywords": "",
        "status": "LINK_FOUND" if result else "NOT_FOUND",
    }


def generic_profiles_from_response(
    result: dict[str, str],
    response: requests.Response,
    soup: BeautifulSoup,
) -> tuple[dict[str, str], dict[str, str]]:
    directory = empty_directory_profile(result)
    review = empty_review_profile(result)

    title = shorten(soup.title.get_text(" ", strip=True), 160) if soup.title else ""
    description_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    description = shorten(description_tag.get("content", ""), 260) if description_tag else ""
    h1 = shorten(soup.h1.get_text(" ", strip=True), 180) if soup.h1 else ""
    page_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    phones = find_phones(response.text, soup)
    emails = find_emails(response.text, soup)
    structured = structured_business_profile(soup)
    rating, review_count = extract_review_metrics(" ".join([description, h1, page_text[:1500]]))

    directory.update(
        {
            "source": domain_from_url(response.url),
            "url": response.url,
            "title": title,
            "description": description,
            "phone": pipe_join([structured.get("telephone", ""), *phones], limit=3),
            "email": pipe_join([structured.get("email", ""), *emails], limit=3),
            "address": structured.get("address") or extract_address_from_text(page_text),
            "website": preferred_external_website(soup, response.url),
            "category": structured.get("category") or h1,
            "rating": normalize_rating(structured.get("rating") or rating),
            "review_count": structured.get("review_count") or review_count,
            "review_summary": description or h1 or directory["review_summary"],
            "status": "OK",
        }
    )

    review.update(
        {
            "source": directory["source"],
            "url": response.url,
            "rating": directory["rating"],
            "review_count": directory["review_count"],
            "summary": directory["review_summary"],
            "status": "OK" if any(
                [directory["rating"], directory["review_count"], directory["review_summary"]]
            ) else "OK_NO_DATA",
        }
    )

    return directory, review


def parse_restaurantguru_profiles(
    session: requests.Session,
    result: dict[str, str],
    response: requests.Response,
    soup: BeautifulSoup,
    delay_seconds: float,
) -> tuple[dict[str, str], dict[str, str]]:
    directory, review = generic_profiles_from_response(result, response, soup)
    description = directory["description"]
    page_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    rating, review_count = extract_review_metrics(description or page_text)
    positive_tags = [
        shorten(tag.get_text(" ", strip=True), 60)
        for tag in soup.select(".meals_list .tag.excellent span")
    ]
    negative_tags = [
        shorten(tag.get_text(" ", strip=True), 60)
        for tag in soup.select(".meals_list .tag.bad span")
    ]

    directory.update(
        {
            "source": "Restaurant Guru",
            "rating": normalize_rating(rating or directory["rating"]),
            "review_count": review_count or directory["review_count"],
            "review_keywords": pipe_join(
                [
                    f"positivi: {pipe_join(positive_tags, limit=5)}" if positive_tags else "",
                    f"critici: {pipe_join(negative_tags, limit=5)}" if negative_tags else "",
                ]
            ),
            "review_summary": description or directory["review_summary"],
            "status": "OK",
        }
    )

    review.update(
        {
            "source": "Restaurant Guru",
            "rating": directory["rating"],
            "review_count": directory["review_count"],
            "keywords": directory["review_keywords"],
            "summary": directory["review_summary"],
            "status": "OK" if any(
                [directory["rating"], directory["review_count"], directory["review_keywords"]]
            ) else review["status"],
        }
    )

    reviews_url = response.url.rstrip("/") + "/reviews"
    try:
        reviews_response = session.get(reviews_url, timeout=25)
        if reviews_response.status_code == 200:
            reviews_soup = BeautifulSoup(reviews_response.text, "html.parser")
            positives = []
            negatives = []
            for card in reviews_soup.select(".o_review")[:12]:
                raw_score = clean_value(card.get("data-score"))
                review_text = shorten(
                    (
                        card.select_one(".text_full")
                        or card.select_one(".text")
                    ).get_text(" ", strip=True),
                    220,
                ) if (card.select_one(".text_full") or card.select_one(".text")) else ""
                if not review_text or len(review_text) < 20:
                    continue
                try:
                    score = int(raw_score or "0")
                except ValueError:
                    score = 0
                block = f"{score}/5: {review_text}" if score else review_text
                if score >= 4 and len(positives) < 2:
                    positives.append(block)
                elif score <= 2 and len(negatives) < 2:
                    negatives.append(block)

            summary_blocks = []
            if positives:
                summary_blocks.append(f"positivi: {pipe_join(positives)}")
            if negatives:
                summary_blocks.append(f"critici: {pipe_join(negatives)}")
            if summary_blocks:
                review["summary"] = pipe_join(summary_blocks)
                directory["review_summary"] = review["summary"]
                review["status"] = "OK"
        time.sleep(delay_seconds)
    except requests.RequestException:
        review["status"] = review["status"] or "PARTIAL"

    return directory, review


def parse_reteimprese_profiles(
    result: dict[str, str],
    response: requests.Response,
    soup: BeautifulSoup,
) -> tuple[dict[str, str], dict[str, str]]:
    directory, review = generic_profiles_from_response(result, response, soup)
    page_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    phone_match = re.search(r"Telefono:\s*([+()\d\s./-]{6,30})", page_text, re.IGNORECASE)
    address_match = re.search(r"Indirizzo:\s*(.+?)\s+Cap:", page_text, re.IGNORECASE)
    rating, review_count = extract_review_metrics(page_text)

    directory.update(
        {
            "source": "Reteimprese",
            "phone": phone_match.group(1).strip() if phone_match else directory["phone"],
            "address": shorten(address_match.group(1).strip(), 160) if address_match else directory["address"],
            "rating": normalize_rating(rating or directory["rating"]),
            "review_count": review_count or directory["review_count"],
            "status": "OK",
        }
    )

    if re.search(r"Nessuna recensione", page_text, re.IGNORECASE):
        review.update(
            {
                "source": "Reteimprese",
                "rating": directory["rating"] or "0",
                "review_count": directory["review_count"] or "0",
                "summary": "nessuna recensione pubblica trovata",
                "status": "ZERO_REVIEWS",
            }
        )
    else:
        review.update(
            {
                "source": "Reteimprese",
                "rating": directory["rating"],
                "review_count": directory["review_count"],
                "summary": directory["review_summary"],
                "status": "OK" if any([directory["rating"], directory["review_count"]]) else review["status"],
            }
        )

    return directory, review


def parse_third_party_result(
    session: requests.Session,
    result: dict[str, str],
    delay_seconds: float,
) -> tuple[dict[str, str], dict[str, str]]:
    directory = empty_directory_profile(result)
    review = empty_review_profile(result)
    if not result:
        return directory, review

    domain = result.get("domain", "")
    if any(item in domain for item in HARD_BLOCKED_DOMAINS):
        directory["status"] = "BLOCKED_SOURCE"
        review["status"] = "BLOCKED_SOURCE"
        return directory, review

    try:
        response = session.get(safe_url(result["url"]), timeout=25)
    except requests.RequestException:
        directory["status"] = "FETCH_ERROR"
        review["status"] = "FETCH_ERROR"
        return directory, review

    if response.status_code != 200:
        directory["status"] = f"HTTP_{response.status_code}"
        review["status"] = f"HTTP_{response.status_code}"
        return directory, review

    soup = BeautifulSoup(response.text, "html.parser")
    if any(item in domain for item in RESTAURANTGURU_DOMAINS):
        directory, review = parse_restaurantguru_profiles(
            session=session,
            result=result,
            response=response,
            soup=soup,
            delay_seconds=delay_seconds,
        )
    elif any(item in domain for item in RETEIMPRESE_DOMAINS):
        directory, review = parse_reteimprese_profiles(result=result, response=response, soup=soup)
    else:
        directory, review = generic_profiles_from_response(result, response, soup)

    time.sleep(delay_seconds)
    return directory, review


def source_query_needed(row: dict[str, str], source: str) -> bool:
    category = row_value(row, "Categoria")
    if source == "tripadvisor":
        return category in {"Ristorazione", "Ospitalita'"}
    if source == "thefork":
        return category == "Ristorazione"
    if source == "restaurantguru":
        return category == "Ristorazione"
    return True


def parse_jsonld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        objects.extend(flatten_jsonld(payload))
    return objects


def flatten_jsonld(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for item in payload:
            items.extend(flatten_jsonld(item))
        return items
    if not isinstance(payload, dict):
        return items

    items.append(payload)
    if "@graph" in payload:
        items.extend(flatten_jsonld(payload["@graph"]))
    if "mainEntity" in payload:
        items.extend(flatten_jsonld(payload["mainEntity"]))
    return items


def jsonld_has_type(node: dict[str, Any], target: str) -> bool:
    node_type = node.get("@type", [])
    if isinstance(node_type, str):
        values = [node_type]
    elif isinstance(node_type, list):
        values = [item for item in node_type if isinstance(item, str)]
    else:
        values = []
    return target in values


def first_jsonld_value(node: dict[str, Any], key: str) -> str:
    value = node.get(key)
    if isinstance(value, list):
        return " | ".join(str(item) for item in value if item)
    if isinstance(value, dict) or value is None:
        return ""
    return str(value)


def structured_restaurant_profile(soup: BeautifulSoup) -> dict[str, str]:
    candidate: dict[str, Any] = {}
    for node in parse_jsonld_objects(soup):
        if jsonld_has_type(node, "Restaurant") or jsonld_has_type(node, "LocalBusiness"):
            candidate = node
            break

    if not candidate:
        return {}

    aggregate = candidate.get("aggregateRating", {})
    cuisines = first_jsonld_value(candidate, "servesCuisine")

    return {
        "rating": first_jsonld_value(aggregate, "ratingValue") if isinstance(aggregate, dict) else "",
        "review_count": first_jsonld_value(aggregate, "reviewCount") if isinstance(aggregate, dict) else "",
        "price_range": first_jsonld_value(candidate, "priceRange"),
        "cuisines": cuisines,
    }


def empty_vertical_profile(result: dict[str, str]) -> dict[str, str]:
    return {
        "url": result.get("url", ""),
        "snippet": result.get("snippet", ""),
        "rating": "",
        "review_count": "",
        "price_range": "",
        "cuisines": "",
        "status": "LINK_FOUND" if result else "NOT_FOUND",
        "error": "",
    }


def parse_vertical_source(
    session: requests.Session,
    result: dict[str, str],
    delay_seconds: float,
) -> dict[str, str]:
    profile = empty_vertical_profile(result)
    if not result:
        return profile

    try:
        response = session.get(safe_url(result["url"]), timeout=25)
    except requests.RequestException as exc:
        profile["status"] = "FETCH_ERROR"
        profile["error"] = str(exc)
        return profile

    if response.status_code != 200:
        profile["status"] = f"HTTP_{response.status_code}"
        profile["error"] = f"pagina non accessibile: HTTP {response.status_code}"
        return profile

    soup = BeautifulSoup(response.text, "html.parser")
    structured = structured_restaurant_profile(soup)
    profile["rating"] = structured.get("rating", "")
    profile["review_count"] = structured.get("review_count", "")
    profile["price_range"] = structured.get("price_range", "")
    profile["cuisines"] = structured.get("cuisines", "")
    profile["status"] = "OK" if any(
        [profile["rating"], profile["review_count"], profile["price_range"], profile["cuisines"]]
    ) else "OK_NO_STRUCTURED_DATA"

    time.sleep(delay_seconds)
    return profile


def extract_text_lines(soup: BeautifulSoup, limit: int = 8) -> str:
    texts = []
    for node in soup.select("p, li"):
        text = node.get_text(" ", strip=True)
        if len(text) < 40:
            continue
        texts.append(text)
        if len(texts) >= limit:
            break
    return " ".join(texts)


def find_emails(text: str, soup: BeautifulSoup) -> list[str]:
    found = set(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE))
    for link in soup.select("a[href^='mailto:']"):
        href = link.get("href", "").removeprefix("mailto:")
        if href:
            found.add(href)
    return sorted(found)


def find_phones(text: str, soup: BeautifulSoup) -> list[str]:
    found = set()
    for raw in re.findall(r"(?:\+?\d[\d\s./()-]{7,}\d)", text):
        compact = re.sub(r"\s+", " ", raw).strip()
        digits_only = re.sub(r"\D", "", compact)
        if len(digits_only) < 8 or len(digits_only) > 14:
            continue
        if re.search(r"\d+\.\d{3,}\s+\d+\.\d{3,}", compact):
            continue
        if compact.count(".") >= 2:
            continue
        if not compact.startswith("+") and digits_only[:2] != "39" and digits_only[:1] not in {"0", "3", "8"}:
            continue
        found.add(compact)
    for link in soup.select("a[href^='tel:']"):
        href = link.get("href", "").removeprefix("tel:")
        if href:
            found.add(href)
    return sorted(found)


def fetch_site_profile(session: requests.Session, url: str) -> dict[str, str]:
    response = session.get(safe_url(url), timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    title = shorten(soup.title.get_text(" ", strip=True), 160) if soup.title else ""
    meta_description = ""
    description_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if description_tag:
        meta_description = shorten(description_tag.get("content", ""), 260)
    h1 = shorten(soup.h1.get_text(" ", strip=True), 160) if soup.h1 else ""
    body_text = " ".join(
        part for part in [meta_description, h1, title, extract_text_lines(soup)] if part
    )

    emails = find_emails(response.text, soup)
    phones = find_phones(response.text, soup)

    social_links = []
    useful_links = []
    signals = []

    base_url = response.url
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        text = shorten(anchor.get_text(" ", strip=True), 80)
        if not href:
            continue
        absolute = urljoin(base_url, href)
        domain = domain_from_url(absolute)
        normalized = normalize_text(f"{text} {href}")

        if any(item in domain for item in SOCIAL_DOMAINS):
            if absolute not in social_links:
                social_links.append(absolute)

        if any(keyword in normalized for keyword in USEFUL_LINK_KEYWORDS):
            label = text or absolute
            pair = f"{label}: {absolute}"
            if pair not in useful_links:
                useful_links.append(pair)

        if "menu" in normalized or "listino" in normalized:
            signals.append("menu o listino presente")
        if "prenot" in normalized or "booking" in normalized:
            signals.append("prenotazione presente")
        if "shop" in normalized or "catalog" in normalized:
            signals.append("catalogo o shop presente")
        if "whatsapp" in normalized:
            signals.append("whatsapp presente")

    if social_links:
        signals.append("social collegati dal sito")
    if phones:
        signals.append("telefono trovato online")
    if emails:
        signals.append("email trovata online")

    return {
        "final_url": response.url,
        "title": title,
        "description": meta_description,
        "h1": h1,
        "what_it_does": shorten(body_text, 320),
        "emails": " | ".join(emails[:3]),
        "phones": " | ".join(phones[:3]),
        "social_links": " | ".join(social_links[:5]),
        "useful_links": " | ".join(useful_links[:6]),
        "signals": " | ".join(sorted(set(signals))),
    }


def normalize_rating_value(value: str) -> str:
    match = re.search(r"\d+(?:[.,]\d+)?", value)
    if not match:
        return ""
    return match.group(0).replace(",", ".")


def normalize_review_count(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits


def first_pattern_value(text: str, patterns: list[str], mode: str = "text") -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip()
        if mode == "rating":
            return normalize_rating_value(value)
        if mode == "count":
            return normalize_review_count(value)
        return shorten(value, 220)
    return ""


def extract_address(text: str) -> str:
    patterns = [
        r"((?:Via|Viale|Piazza|Corso|Largo|Vicolo)\s+[^.;|]{5,120}?\d[^.;|]{0,80})",
        r"Indirizzo:\s*([^.;|]{6,140})",
    ]
    return first_pattern_value(text, patterns)


def extract_external_website(soup: BeautifulSoup, base_url: str) -> str:
    base_domain = domain_from_url(base_url)
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        domain = domain_from_url(absolute)
        if not domain or domain == base_domain:
            continue
        if any(item in domain for item in THIRD_PARTY_DOMAINS):
            continue
        if any(item in domain for item in SOCIAL_DOMAINS):
            continue
        return absolute
    return ""


def infer_directory_category(text: str) -> str:
    normalized = normalize_text(text)
    if "pub e bar" in normalized:
        return "pub e bar"
    if "ristorante" in normalized:
        return "ristorante"
    if "pizzeria" in normalized:
        return "pizzeria"
    if "bar" in normalized:
        return "bar"
    if "farmacia" in normalized:
        return "farmacia"
    return ""


def empty_directory_profile(result: dict[str, str]) -> dict[str, str]:
    return {
        "source": result.get("domain", ""),
        "url": result.get("url", ""),
        "title": result.get("title", ""),
        "description": result.get("snippet", ""),
        "phones": "",
        "emails": "",
        "address": "",
        "website": "",
        "category": "",
        "rating": "",
        "review_count": "",
        "review_summary": "",
        "review_keywords": "",
        "status": "LINK_FOUND" if result else "NOT_FOUND",
        "error": "",
    }


def restaurantguru_review_summary(text: str) -> tuple[str, str]:
    summary = ""
    keywords = ""
    summary_match = re.search(
        r"Aggiungi la tua opinione\s*(.+?)\s*Spesso citati nelle recensioni",
        text,
        re.IGNORECASE,
    )
    if summary_match:
        cleaned = re.sub(r"\bLeggi tutto\b|\bNascondi\b", "", summary_match.group(1), flags=re.IGNORECASE)
        summary = shorten(re.sub(r"\s+", " ", cleaned).strip(), 280)
    keywords_match = re.search(
        r"Spesso citati nelle recensioni\s+(.+?)\s+Valutazioni di",
        text,
        re.IGNORECASE,
    )
    if keywords_match:
        keywords = shorten(re.sub(r"\s+", " ", keywords_match.group(1)).strip(), 180)
    return summary, keywords


def parse_directory_source(
    session: requests.Session,
    row: dict[str, str],
    result: dict[str, str],
    delay_seconds: float,
) -> dict[str, str]:
    profile = empty_directory_profile(result)
    if not result:
        return profile

    try:
        response = session.get(safe_url(result["url"]), timeout=25)
    except requests.RequestException as exc:
        profile["status"] = "FETCH_ERROR"
        profile["error"] = str(exc)
        return profile

    if response.status_code != 200:
        profile["status"] = f"HTTP_{response.status_code}"
        profile["error"] = f"pagina non accessibile: HTTP {response.status_code}"
        return profile

    soup = BeautifulSoup(response.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    description_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    meta_description = description_tag.get("content", "").strip() if description_tag else ""
    listing_page = is_listing_result(result)
    profile["title"] = shorten(soup.title.get_text(" ", strip=True), 160) if soup.title else profile["title"]
    profile["description"] = shorten(meta_description or profile["description"], 260)
    profile["category"] = infer_directory_category(f"{profile['title']} {meta_description} {text[:300]}")
    name_matches, location_matches = content_match_score(
        row,
        " ".join(part for part in [profile["title"], meta_description, text[:1500]] if part),
    )

    if ambiguous_business(row):
        mismatch = name_matches == 0 or location_matches == 0
    else:
        mismatch = name_matches == 0 and normalize_text(row_value(row, "Nome Attivita'")) not in normalize_text(
            " ".join([profile["title"], meta_description, text[:600]])
        )
    if mismatch:
        profile["status"] = "MISMATCH"
        profile["description"] = shorten(meta_description or profile["description"], 220)
        return profile

    if not listing_page:
        profile["phones"] = " | ".join(find_phones(response.text, soup)[:3])
        profile["emails"] = " | ".join(find_emails(response.text, soup)[:3])
        profile["address"] = extract_address(text)
        profile["website"] = extract_external_website(soup, response.url)

    combined_text = f"{meta_description} {text}".strip()
    profile["rating"] = first_pattern_value(
        combined_text,
        [
            r"valutat[oa]\s+([0-9]+(?:[.,][0-9]+)?)\s+su\s+5",
            r"Google\s*\(([0-9]+(?:[.,][0-9]+)?)/5\)",
            r"([1-5](?:[.,][0-9]+)?)\s+su\s+5",
        ],
        mode="rating",
    )
    profile["review_count"] = first_pattern_value(
        combined_text,
        [
            r"([0-9][0-9\.\s]*)\s+recensioni",
            r"recensioni dei visitatori[^0-9]{0,20}([0-9][0-9\.\s]*)",
        ],
        mode="count",
    )

    if any(item in result.get("domain", "") for item in RESTAURANTGURU_DOMAINS):
        restaurantguru_address = first_pattern_value(
            text,
            [
                r"((?:Via|Viale|Piazza|Corso|Largo|Vicolo)\s+[^.;|]{3,80}?,\s*\d{1,4})",
                r"((?:Via|Viale|Piazza|Corso|Largo|Vicolo)\s+[^.;|]{3,80}\d{1,4})",
            ],
        )
        if restaurantguru_address:
            profile["address"] = restaurantguru_address
        positive_tags = [
            shorten(node.get_text(" ", strip=True), 60)
            for node in soup.select(".meals_list .tag.excellent span")
        ]
        negative_tags = [
            shorten(node.get_text(" ", strip=True), 60)
            for node in soup.select(".meals_list .tag.bad span")
        ]
        summary, keywords = restaurantguru_review_summary(text)
        if positive_tags or negative_tags:
            keywords = pipe_join(
                [
                    f"positivi: {pipe_join(positive_tags, limit=5)}" if positive_tags else "",
                    f"critici: {pipe_join(negative_tags, limit=5)}" if negative_tags else "",
                ]
            )

        review_blocks = []
        reviews_url = response.url.rstrip("/") + "/reviews"
        try:
            reviews_response = session.get(reviews_url, timeout=25)
            if reviews_response.status_code == 200:
                reviews_soup = BeautifulSoup(reviews_response.text, "html.parser")
                positive_reviews = []
                critical_reviews = []
                for review_card in reviews_soup.select(".o_review")[:12]:
                    score_raw = clean_value(review_card.get("data-score"))
                    text_node = review_card.select_one(".text_full") or review_card.select_one(".text")
                    if not text_node:
                        continue
                    review_text = shorten(text_node.get_text(" ", strip=True), 220)
                    if len(review_text) < 20:
                        continue
                    try:
                        score = int(score_raw or "0")
                    except ValueError:
                        score = 0
                    block = f"{score}/5: {review_text}" if score else review_text
                    if score >= 4 and len(positive_reviews) < 2:
                        positive_reviews.append(block)
                    elif score <= 2 and len(critical_reviews) < 2:
                        critical_reviews.append(block)

                if positive_reviews:
                    review_blocks.append(f"positivi: {pipe_join(positive_reviews)}")
                if critical_reviews:
                    review_blocks.append(f"critici: {pipe_join(critical_reviews)}")
            time.sleep(delay_seconds)
        except requests.RequestException:
            pass

        profile["review_summary"] = pipe_join(review_blocks) or summary
        profile["review_keywords"] = keywords
        if not profile["category"] and "pub e bar" in text.lower():
            profile["category"] = "pub e bar"
    elif any(item in result.get("domain", "") for item in RETEIMPRESE_DOMAINS):
        reteimprese_address = first_pattern_value(
            text,
            [
                r"Indirizzo:\s*([^.;|]{6,120}?)\s+Cap:",
                r"((?:Via|Viale|Piazza|Corso|Largo|Vicolo)\s+[^.;|]{3,100},\s*\d{5}\s+[^.;|]{2,60})",
            ],
        )
        if reteimprese_address:
            profile["address"] = reteimprese_address
        if re.search(r"Nessuna recensione", text, re.IGNORECASE):
            profile["review_count"] = "0"
    else:
        profile["review_summary"] = shorten(meta_description, 220) if profile["review_count"] else ""

    if listing_page and not any(
        [profile["rating"], profile["review_count"], profile["review_summary"]]
    ):
        profile["status"] = "LISTING_PAGE"
    else:
        profile["status"] = "OK" if any(
            [
                profile["phones"],
                profile["emails"],
                profile["rating"],
                profile["review_count"],
                profile["review_summary"],
                profile["website"],
            ]
        ) else "OK_NO_STRUCTURED_DATA"

    time.sleep(delay_seconds)
    return profile


def choose_review_profile(
    directory_profile: dict[str, str],
    tripadvisor_profile: dict[str, str],
    thefork_profile: dict[str, str],
) -> dict[str, str]:
    candidates = []
    if directory_profile.get("rating") or directory_profile.get("review_count"):
        candidates.append(
            {
                "source": directory_profile.get("source", ""),
                "url": directory_profile.get("url", ""),
                "rating": directory_profile.get("rating", ""),
                "review_count": directory_profile.get("review_count", ""),
                "summary": directory_profile.get("review_summary", ""),
                "keywords": directory_profile.get("review_keywords", ""),
                "status": directory_profile.get("status", ""),
            }
        )
    for name, profile in [("tripadvisor", tripadvisor_profile), ("thefork", thefork_profile)]:
        if profile.get("rating") or profile.get("review_count"):
            candidates.append(
                {
                    "source": name,
                    "url": profile.get("url", ""),
                    "rating": profile.get("rating", ""),
                    "review_count": profile.get("review_count", ""),
                    "summary": profile.get("snippet", ""),
                    "keywords": "",
                    "status": profile.get("status", ""),
                }
            )
    if not candidates:
        return {
            "source": "",
            "url": "",
            "rating": "",
            "review_count": "",
            "summary": "",
            "keywords": "",
            "status": "NOT_FOUND",
        }
    candidates.sort(
        key=lambda item: (
            1 if item["rating"] else 0,
            int(item["review_count"] or "0"),
        ),
        reverse=True,
    )
    return candidates[0]


def fallback_business_summary(row: dict[str, str], results: list[dict[str, str]]) -> str:
    if results:
        for result in results:
            if result["snippet"]:
                return result["snippet"]
    category = row_value(row, "Categoria")
    subtype = row_value(row, "Sottocategoria")
    city = row_value(row, "Comune") or "zona Varese"
    return f"{subtype or category} a {city}"


def snippet_bundle(results: list[dict[str, str]], limit: int = 4) -> str:
    parts = []
    for result in results[:limit]:
        block = f"{result['title']} - {result['snippet']}".strip(" -")
        if block:
            parts.append(shorten(block, 220))
    return " | ".join(parts)


def merge_unique_results(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    merged = []
    seen = set()
    for group in groups:
        for result in group:
            url = result.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(result)
    return merged


def verify_notes(
    row: dict[str, str],
    site_profile: dict[str, str],
    directory_profile: dict[str, str],
    review_profile: dict[str, str],
    third_party_links: list[str],
    confidence_match: str,
    online_phones: str,
    online_emails: str,
) -> str:
    notes = []
    if not (site_profile.get("final_url") or directory_profile.get("website")):
        notes.append("non e' stato trovato un sito ufficiale affidabile")
    if not third_party_links:
        notes.append("non sono emerse pagine terze parti nei primi risultati")
    if not row_value(row, "Comune"):
        notes.append("manca il comune nel CSV base: risultati potenzialmente ambigui")
    if ambiguous_business(row) and site_profile.get("final_url") and not row_value(row, "Sito Web"):
        notes.append("verificare che il sito trovato corrisponda davvero all'attivita del CSV")
    if confidence_match.startswith("BASSA") or confidence_match.startswith("DA_VERIFICARE"):
        notes.append("match fonte da verificare manualmente")
    if review_profile.get("status") == "BLOCKED_SOURCE":
        notes.append("fonte recensioni bloccata da anti-bot")
    if not row_value(row, "Telefono") and not online_phones:
        notes.append("telefono non trovato ne' nel CSV ne' online")
    if not row_value(row, "Email") and not online_emails:
        notes.append("email non trovata ne' nel CSV ne' online")
    if row_value(row, "Categoria") == "Ristorazione" and not review_profile.get("rating"):
        notes.append("rating recensioni non trovato su fonti accessibili")
    return "; ".join(notes)


def research_company(
    session: requests.Session,
    row: dict[str, str],
    delay_seconds: float,
    max_search_results: int,
) -> dict[str, str]:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    osm_profile = fetch_osm_enrichment(session, row)
    enriched_row = dict(row)
    if osm_profile.get("city") and not row_value(row, "Comune"):
        enriched_row["Comune"] = osm_profile["city"]
    if osm_profile.get("address") and not row_value(row, "Indirizzo"):
        enriched_row["Indirizzo"] = osm_profile["address"]
    if osm_profile.get("website") and not row_value(row, "Sito Web"):
        enriched_row["Sito Web"] = osm_profile["website"]
    if osm_profile.get("phone") and not row_value(row, "Telefono"):
        enriched_row["Telefono"] = osm_profile["phone"]
    if osm_profile.get("email") and not row_value(row, "Email"):
        enriched_row["Email"] = osm_profile["email"]

    main_query = build_query(enriched_row)
    review_query = f"{main_query} recensioni"
    name_query = row_value(enriched_row, "Nome Attivita'")
    location_query = row_value(enriched_row, "Comune") or row_value(enriched_row, "Indirizzo") or "Varese"

    general_results = search_duckduckgo(session, main_query, max_search_results)
    time.sleep(delay_seconds)
    if not general_results and name_query:
        general_results = search_duckduckgo(
            session,
            f'"{name_query}" {location_query}',
            max_search_results,
        )
        time.sleep(delay_seconds)
    review_results = search_duckduckgo(session, review_query, max(3, max_search_results // 2))
    time.sleep(delay_seconds)
    if not review_results and name_query:
        review_results = search_duckduckgo(
            session,
            f'"{name_query}" {location_query} recensioni',
            max(3, max_search_results // 2),
        )
        time.sleep(delay_seconds)
    combined_results = merge_unique_results(general_results, review_results)

    restaurantguru_result = guess_restaurantguru_result(session, enriched_row, delay_seconds)
    if restaurantguru_result:
        combined_results = merge_unique_results(combined_results, [restaurantguru_result])
    if not restaurantguru_result:
        restaurantguru_result = best_result_for_domains(
            enriched_row, combined_results, RESTAURANTGURU_DOMAINS, min_score=3
        )
    if source_query_needed(row, "restaurantguru") and not restaurantguru_result:
        restaurantguru_search = search_duckduckgo(
            session,
            f'site:restaurantguru.it "{name_query}" {location_query}',
            max(3, max_search_results // 2),
        )
        time.sleep(delay_seconds)
        combined_results = merge_unique_results(combined_results, restaurantguru_search)
        restaurantguru_result = best_result_for_domains(
            enriched_row,
            restaurantguru_search,
            RESTAURANTGURU_DOMAINS,
            min_score=3,
        )

    contact_directory_domains = tuple(
        domain for domain in DIRECTORY_DOMAINS if domain not in RESTAURANTGURU_DOMAINS
    )
    directory_result = best_result_for_domains(
        enriched_row, combined_results, contact_directory_domains, min_score=3
    )
    if not directory_result:
        directory_search = search_duckduckgo(
            session,
            f'site:reteimprese.it "{name_query}" {location_query}',
            max(3, max_search_results // 2),
        )
        time.sleep(delay_seconds)
        combined_results = merge_unique_results(combined_results, directory_search)
        directory_result = best_result_for_domains(
            enriched_row,
            directory_search,
            contact_directory_domains,
            min_score=3,
        )
    if not directory_result and restaurantguru_result:
        directory_result = restaurantguru_result

    maps_result = best_result_for_domains(enriched_row, combined_results, MAPS_DOMAINS, min_score=-5)
    facebook_result = best_result_for_domains(enriched_row, combined_results, FACEBOOK_DOMAINS, min_score=1)
    tripadvisor_result = best_result_for_domains(enriched_row, combined_results, TRIPADVISOR_DOMAINS, min_score=3)
    thefork_result = best_result_for_domains(enriched_row, combined_results, THEFORK_DOMAINS, min_score=3)

    if source_query_needed(row, "tripadvisor") and not tripadvisor_result:
        tripadvisor_search = search_duckduckgo(
            session,
            f'site:tripadvisor.it "{name_query}" {location_query}',
            max(3, max_search_results // 2),
        )
        time.sleep(delay_seconds)
        combined_results = merge_unique_results(combined_results, tripadvisor_search)
        tripadvisor_result = best_result_for_domains(
            enriched_row, tripadvisor_search, TRIPADVISOR_DOMAINS, min_score=3
        )

    if source_query_needed(row, "thefork") and not thefork_result:
        thefork_search = search_duckduckgo(
            session,
            f'site:thefork.it "{name_query}" {location_query}',
            max(3, max_search_results // 2),
        )
        time.sleep(delay_seconds)
        combined_results = merge_unique_results(combined_results, thefork_search)
        thefork_result = best_result_for_domains(
            enriched_row, thefork_search, THEFORK_DOMAINS, min_score=3
        )

    official_site = choose_official_site(enriched_row, general_results)
    site_profile: dict[str, str] = {
        "final_url": "",
        "signals": "",
        "description": "",
        "h1": "",
        "title": "",
        "what_it_does": "",
        "emails": "",
        "phones": "",
        "social_links": "",
        "useful_links": "",
    }
    errors = []
    if official_site:
        try:
            site_profile = fetch_site_profile(session, official_site)
            time.sleep(delay_seconds)
        except requests.RequestException as exc:
            site_profile["final_url"] = official_site
            errors.append(f"fetch sito fallita: {exc}")

    tripadvisor_profile = parse_vertical_source(session, tripadvisor_result, delay_seconds)
    thefork_profile = parse_vertical_source(session, thefork_result, delay_seconds)
    directory_profile = parse_directory_source(session, enriched_row, directory_result, delay_seconds)
    review_directory_profile = directory_profile
    if restaurantguru_result and restaurantguru_result.get("url") != directory_result.get("url"):
        review_directory_profile = parse_directory_source(
            session,
            enriched_row,
            restaurantguru_result,
            delay_seconds,
        )
    review_profile = choose_review_profile(
        review_directory_profile,
        tripadvisor_profile,
        thefork_profile,
    )

    third_party_links = collect_third_party_links(combined_results)
    snippets = snippet_bundle(combined_results)
    online_phones = pipe_join([site_profile.get("phones", ""), directory_profile.get("phones", "")])
    online_emails = pipe_join([site_profile.get("emails", ""), directory_profile.get("emails", "")])
    useful_links = pipe_join(
        [
            site_profile.get("useful_links", ""),
            f"Sito da directory: {directory_profile.get('website')}" if directory_profile.get("website") else "",
        ]
    )
    cosa_fanno = (
        site_profile.get("what_it_does")
        or directory_profile.get("description")
        or review_profile.get("summary")
        or fallback_business_summary(row, general_results)
    )
    confidence_values = []
    if official_site:
        official_result = next((item for item in general_results if item.get("url") == official_site), {})
        if official_result:
            confidence_values.append(score_result(enriched_row, official_result))
    if directory_result:
        confidence_values.append(score_result(enriched_row, directory_result))
    if review_profile.get("url"):
        review_result = next(
            (item for item in combined_results if item.get("url") == review_profile["url"]),
            {},
        )
        if review_result:
            confidence_values.append(score_result(enriched_row, review_result))
    confidence_score = max(confidence_values) if confidence_values else 0
    confidence_match = f"{confidence_label(confidence_score)} ({confidence_score})"

    signal_parts = [site_profile.get("signals", "")]
    if directory_profile.get("rating"):
        signal_parts.append(f"rating disponibile da {directory_profile.get('source', '')}")
    if review_profile.get("summary"):
        signal_parts.append("sintesi recensioni disponibile")
    if directory_profile.get("phones"):
        signal_parts.append("telefono trovato su directory")
    signals = " | ".join(part for part in signal_parts if part) or "nessun segnale digitale estratto"

    return {
        "Data Ricerca": timestamp,
        "Nome Attivita": row_value(row, "Nome Attivita'"),
        "Comune": row_value(row, "Comune") or "N/D",
        "Categoria": row_value(row, "Categoria"),
        "Sottocategoria": row_value(row, "Sottocategoria"),
        "Priorita Distanza": row_value(row, "Priorita'"),
        "Distanza KM": row_value(row, "Distanza da Vedano Olona (km)"),
        "Indirizzo": row_value(row, "Indirizzo") or "N/D",
        "Telefono CSV": row_value(row, "Telefono") or "N/D",
        "Email CSV": row_value(row, "Email") or "N/D",
        "Sito Web CSV": row_value(row, "Sito Web") or "N/D",
        "OSM URL": row_value(row, "OSM URL") or "N/D",
        "OSM Nome Verificato": osm_profile.get("name", ""),
        "OSM Comune Verificato": osm_profile.get("city", ""),
        "OSM Indirizzo Verificato": osm_profile.get("address", ""),
        "OSM Tipo Verificato": osm_profile.get("type", ""),
        "OSM Coordinate": pipe_join([osm_profile.get("lat", ""), osm_profile.get("lon", "")], limit=2),
        "Query Principale": main_query,
        "Query Recensioni": review_query,
        "Sito Ufficiale Trovato": (
            site_profile.get("final_url")
            or official_site
            or directory_profile.get("website")
            or osm_profile.get("website")
            or "N/D"
        ),
        "Titolo Sito": site_profile.get("title", ""),
        "Descrizione Sito": site_profile.get("description", ""),
        "H1 Sito": site_profile.get("h1", ""),
        "Telefono Trovato Online": online_phones,
        "Email Trovata Online": online_emails,
        "Link Social": site_profile.get("social_links", ""),
        "Link Utili": useful_links,
        "Google Maps URL": maps_result.get("url", ""),
        "Facebook URL": facebook_result.get("url", ""),
        "Tripadvisor URL": tripadvisor_profile["url"],
        "Tripadvisor Snippet": tripadvisor_profile["snippet"],
        "Tripadvisor Rating": tripadvisor_profile["rating"],
        "Tripadvisor Review Count": tripadvisor_profile["review_count"],
        "Tripadvisor Price Range": tripadvisor_profile["price_range"],
        "Tripadvisor Cuisines": tripadvisor_profile["cuisines"],
        "Tripadvisor Status": tripadvisor_profile["status"],
        "TheFork URL": thefork_profile["url"],
        "TheFork Snippet": thefork_profile["snippet"],
        "TheFork Rating": thefork_profile["rating"],
        "TheFork Review Count": thefork_profile["review_count"],
        "TheFork Price Range": thefork_profile["price_range"],
        "TheFork Cuisines": thefork_profile["cuisines"],
        "TheFork Status": thefork_profile["status"],
        "Directory Fonte": directory_profile["source"],
        "Directory URL": directory_profile["url"],
        "Directory Titolo": directory_profile["title"],
        "Directory Descrizione": directory_profile["description"],
        "Directory Telefono": directory_profile["phones"],
        "Directory Email": directory_profile["emails"],
        "Directory Indirizzo": directory_profile["address"],
        "Directory Sito": directory_profile["website"],
        "Directory Categoria": directory_profile["category"],
        "Directory Rating": directory_profile["rating"],
        "Directory Review Count": directory_profile["review_count"],
        "Directory Review Summary": directory_profile["review_summary"],
        "Directory Review Keywords": directory_profile["review_keywords"],
        "Directory Status": directory_profile["status"],
        "Review Fonte": review_profile["source"],
        "Review URL": review_profile["url"],
        "Review Rating": review_profile["rating"],
        "Review Count": review_profile["review_count"],
        "Review Summary": review_profile["summary"],
        "Review Keywords": review_profile["keywords"],
        "Review Status": review_profile["status"],
        "Confidenza Match": confidence_match,
        "Pagine Terze Parti": " | ".join(third_party_links[:8]),
        "Snippet Ricerca": snippets,
        "Cosa Fanno": cosa_fanno,
        "Segnali Digitali": signals,
        "Elementi Da Verificare": verify_notes(
            row,
            site_profile,
            directory_profile,
            review_profile,
            third_party_links,
            confidence_match,
            online_phones,
            online_emails,
        ),
        "Errore Ricerca": " | ".join(errors),
    }


def sorted_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            PRIORITY_ORDER.get(row.get("Priorita'", ""), 99),
            float(row.get("Distanza da Vedano Olona (km)", "9999") or "9999"),
            normalize_text(row.get("Nome Attivita'", "")),
        ),
    )


def write_summary(path: Path, rows: list[dict[str, str]], output_path: Path, merged_output_path: Path) -> None:
    found_sites = sum(1 for row in rows if row["Sito Ufficiale Trovato"] not in {"", "N/D"})
    found_emails = sum(1 for row in rows if row["Email Trovata Online"] or row["Directory Email"])
    found_phones = sum(1 for row in rows if row["Telefono Trovato Online"] or row["Directory Telefono"])
    tripadvisor_hits = sum(1 for row in rows if row["Tripadvisor URL"])
    thefork_hits = sum(1 for row in rows if row["TheFork URL"])
    directory_hits = sum(1 for row in rows if row["Directory URL"])
    review_hits = sum(
        1 for row in rows if row["Review Rating"] or row["Review Count"] or row["Review Summary"]
    )
    categories = Counter(row["Categoria"] for row in rows)

    lines = [
        "# Ricerca Online Attivita",
        "",
        f"- Aziende analizzate: {len(rows)}",
        f"- Siti ufficiali trovati: {found_sites}",
        f"- Email trovate online: {found_emails}",
        f"- Telefoni trovati online: {found_phones}",
        f"- Directory utili trovate: {directory_hits}",
        f"- Schede con rating/recensioni: {review_hits}",
        f"- Link Tripadvisor trovati: {tripadvisor_hits}",
        f"- Link TheFork trovati: {thefork_hits}",
        f"- CSV sorgente: `{project_relative(DEFAULT_OSM_OUTPUT)}`",
        f"- Output CSV ricerca: `{project_relative(output_path)}`",
        f"- Output CSV merged: `{project_relative(merged_output_path)}`",
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
            "- Leggi prima `Cosa Fanno`, `Snippet Ricerca` e `Pagine Terze Parti`.",
            "- Verifica manualmente i punti dubbi in `Elementi Da Verificare`.",
            "- Solo dopo usa questi dati per scrivere il messaggio mirato.",
        ]
    )

    ensure_parent_dir(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cerca informazioni online sulle aziende presenti nel CSV."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_OSM_OUTPUT),
        help=f"CSV sorgente. Default: {project_relative(DEFAULT_OSM_OUTPUT)}.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_COMPANY_RESEARCH_OUTPUT),
        help=f"CSV arricchito finale. Default: {project_relative(DEFAULT_COMPANY_RESEARCH_OUTPUT)}.",
    )
    parser.add_argument(
        "--summary",
        default=str(DEFAULT_COMPANY_RESEARCH_SUMMARY),
        help=f"Riepilogo markdown. Default: {project_relative(DEFAULT_COMPANY_RESEARCH_SUMMARY)}.",
    )
    parser.add_argument(
        "--merged-output",
        default=str(DEFAULT_COMPANY_RESEARCH_MERGED_OUTPUT),
        help=(
            "CSV con colonne originali piu campi ricerca. "
            f"Default: {project_relative(DEFAULT_COMPANY_RESEARCH_MERGED_OUTPUT)}."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Numero massimo di aziende da analizzare. Default: 10.",
    )
    parser.add_argument(
        "--only-missing-website",
        action="store_true",
        help="Analizza solo aziende senza sito nel CSV.",
    )
    parser.add_argument(
        "--include-with-website",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--max-search-results",
        type=int,
        default=8,
        help="Numero massimo di risultati DuckDuckGo per query. Default: 8.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Pausa tra richieste HTTP in secondi. Default: 1.0.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary)
    merged_output_path = Path(args.merged_output)

    rows = load_csv(input_path)
    candidates = []
    for row in sorted_rows(rows):
        if args.only_missing_website and row.get("Ha Sito Web") != "NO":
            continue
        candidates.append(row)
        if args.limit > 0 and len(candidates) >= args.limit:
            break

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    )

    output_rows = []
    for index, row in enumerate(candidates, start=1):
        name = row_value(row, "Nome Attivita'")
        print(f"[{index}/{len(candidates)}] Ricerca online: {name}")
        try:
            output_rows.append(
                research_company(
                    session=session,
                    row=row,
                    delay_seconds=args.delay,
                    max_search_results=args.max_search_results,
                )
            )
        except requests.RequestException as exc:
            output_rows.append(
                {
                    "Data Ricerca": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Nome Attivita": name,
                    "Comune": row_value(row, "Comune") or "N/D",
                    "Categoria": row_value(row, "Categoria"),
                    "Sottocategoria": row_value(row, "Sottocategoria"),
                    "Priorita Distanza": row_value(row, "Priorita'"),
                    "Distanza KM": row_value(row, "Distanza da Vedano Olona (km)"),
                    "Indirizzo": row_value(row, "Indirizzo") or "N/D",
                    "Telefono CSV": row_value(row, "Telefono") or "N/D",
                    "Email CSV": row_value(row, "Email") or "N/D",
                    "Sito Web CSV": row_value(row, "Sito Web") or "N/D",
                    "OSM URL": row_value(row, "OSM URL") or "N/D",
                    "OSM Nome Verificato": "",
                    "OSM Comune Verificato": "",
                    "OSM Indirizzo Verificato": "",
                    "OSM Tipo Verificato": "",
                    "OSM Coordinate": "",
                    "Query Principale": build_query(row),
                    "Query Recensioni": f"{build_query(row)} recensioni",
                    "Sito Ufficiale Trovato": "N/D",
                    "Titolo Sito": "",
                    "Descrizione Sito": "",
                    "H1 Sito": "",
                    "Telefono Trovato Online": "",
                    "Email Trovata Online": "",
                    "Link Social": "",
                    "Link Utili": "",
                    "Google Maps URL": "",
                    "Facebook URL": "",
                    "Tripadvisor URL": "",
                    "Tripadvisor Snippet": "",
                    "Tripadvisor Rating": "",
                    "Tripadvisor Review Count": "",
                    "Tripadvisor Price Range": "",
                    "Tripadvisor Cuisines": "",
                    "Tripadvisor Status": "NOT_RUN",
                    "TheFork URL": "",
                    "TheFork Snippet": "",
                    "TheFork Rating": "",
                    "TheFork Review Count": "",
                    "TheFork Price Range": "",
                    "TheFork Cuisines": "",
                    "TheFork Status": "NOT_RUN",
                    "Directory Fonte": "",
                    "Directory URL": "",
                    "Directory Titolo": "",
                    "Directory Descrizione": "",
                    "Directory Telefono": "",
                    "Directory Email": "",
                    "Directory Indirizzo": "",
                    "Directory Sito": "",
                    "Directory Categoria": "",
                    "Directory Rating": "",
                    "Directory Review Count": "",
                    "Directory Review Summary": "",
                    "Directory Review Keywords": "",
                    "Directory Status": "NOT_RUN",
                    "Review Fonte": "",
                    "Review URL": "",
                    "Review Rating": "",
                    "Review Count": "",
                    "Review Summary": "",
                    "Review Keywords": "",
                    "Review Status": "NOT_RUN",
                    "Confidenza Match": "0",
                    "Pagine Terze Parti": "",
                    "Snippet Ricerca": "",
                    "Cosa Fanno": "",
                    "Segnali Digitali": "",
                    "Elementi Da Verificare": "ricerca online non completata",
                    "Errore Ricerca": str(exc),
                }
            )

    write_csv(output_path, SEARCH_FIELDNAMES, output_rows)
    merged_fieldnames, merged_dataset = merged_rows(candidates, output_rows)
    write_csv(merged_output_path, merged_fieldnames, merged_dataset)
    write_summary(summary_path, output_rows, output_path, merged_output_path)

    print("\nRICERCA ONLINE COMPLETATA")
    print("=" * 72)
    print(f"Aziende analizzate: {len(output_rows)}")
    print(f"Output CSV: {project_relative(output_path)}")
    print(f"Output CSV merged: {project_relative(merged_output_path)}")
    print(f"Report markdown: {project_relative(summary_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
