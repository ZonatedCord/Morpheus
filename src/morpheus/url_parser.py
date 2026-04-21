from __future__ import annotations

import json
import re
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

_EMPTY_RESULT: dict = {
    "nome": "",
    "lat": None,
    "lon": None,
    "facebook_url": "",
    "sito": "",
    "comune": "",
    "categoria": "",
    "indirizzo": "",
    "telefono": "",
    "email": "",
}

_FB_SKIP_SLUGS = frozenset({
    "sharer", "share", "login", "home", "pages", "groups",
    "events", "photo", "video", "watch", "marketplace",
})


def _slug_to_name(slug: str) -> str:
    # If no separators, preserve original casing (e.g. "CartoleriaMarina")
    if not re.search(r"[-_.]", slug):
        return slug.strip()
    name = re.sub(r"[-_.]", " ", slug).strip()
    return " ".join(word.capitalize() for word in name.split() if word)


def _scrape_facebook_page(url: str) -> dict:
    """Attempt to fetch Facebook page HTML and extract og/ld+json metadata."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        html = resp.text
    except Exception:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    result: dict = {}

    # og:title → nome
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        result["nome"] = og_title["content"].strip()

    # og:description → potrebbe contenere indirizzo/telefono
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"].strip()
        # cerca pattern telefono nel testo
        phone_match = re.search(r"(\+?[\d\s\-\(\)]{7,15})", desc)
        if phone_match:
            result["telefono"] = phone_match.group(1).strip()

    # ld+json structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0]
            if not isinstance(data, dict):
                continue
            if not result.get("nome") and data.get("name"):
                result["nome"] = str(data["name"]).strip()
            if data.get("telephone"):
                result["telefono"] = str(data["telephone"]).strip()
            if data.get("email"):
                result["email"] = str(data["email"]).strip()
            if data.get("url"):
                sito = str(data["url"]).strip()
                if "facebook.com" not in sito:
                    result["sito"] = sito
            addr = data.get("address") or {}
            if isinstance(addr, dict):
                parts = [
                    addr.get("streetAddress", ""),
                    addr.get("addressLocality", ""),
                ]
                indirizzo = ", ".join(p for p in parts if p)
                if indirizzo:
                    result["indirizzo"] = indirizzo
                if addr.get("addressLocality"):
                    result["comune"] = addr["addressLocality"].strip()
            geo = data.get("geo") or {}
            if isinstance(geo, dict) and geo.get("latitude") and geo.get("longitude"):
                try:
                    result["lat"] = float(geo["latitude"])
                    result["lon"] = float(geo["longitude"])
                except (TypeError, ValueError):
                    pass
        except Exception:
            continue

    return result


def _parse_facebook(url: str) -> dict:
    match = re.search(r"facebook\.com/([^/?#]+)", url)
    if not match:
        return {}
    slug = match.group(1).rstrip("/")
    if slug in _FB_SKIP_SLUGS:
        return {}
    nome_from_slug = _slug_to_name(slug)
    facebook_url = f"https://www.facebook.com/{slug}"

    # Prova a estrarre dati dalla pagina
    scraped = _scrape_facebook_page(facebook_url)
    result = {"nome": nome_from_slug, "facebook_url": facebook_url}
    result.update(scraped)  # scraped sovrascrive slug-name se trova og:title
    result["facebook_url"] = facebook_url  # mantieni sempre l'URL originale
    return result


def _parse_google_maps(url: str) -> dict:
    result: dict = {}
    place_match = re.search(r"/maps/place/([^/@?]+)", url)
    if place_match:
        raw = place_match.group(1)
        nome = unquote(raw).replace("+", " ").strip()
        if nome:
            result["nome"] = nome
    coord_match = re.search(r"@([-\d.]+),([-\d.]+)", url)
    if coord_match:
        try:
            result["lat"] = float(coord_match.group(1))
            result["lon"] = float(coord_match.group(2))
        except ValueError:
            pass
    return result


def _follow_redirect(url: str, timeout: int = 8) -> str:
    try:
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MorpheusBot/1.0)"},
        )
        return resp.url
    except Exception:
        return url


_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode_address(address: str) -> dict | None:
    """Geocode a free-text address via Nominatim. Returns {lat, lon, display_name} or None."""
    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={"q": address, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": "MorpheusLeadGen/1.0"},
            timeout=8,
        )
        data = resp.json()
        if not data:
            return None
        hit = data[0]
        return {
            "lat": float(hit["lat"]),
            "lon": float(hit["lon"]),
            "display_name": hit.get("display_name", ""),
        }
    except Exception:
        return None


def parse_lead_url(url: str) -> dict:
    """Parse a Facebook or Google Maps URL and return pre-filled lead fields.

    Raises ValueError for unrecognized URL types.
    Missing fields are empty string or None.
    """
    url = url.strip()

    if "facebook.com" in url:
        data = _parse_facebook(url)
        return {**_EMPTY_RESULT, **data}

    if "maps.app.goo.gl" in url or "goo.gl/maps" in url:
        url = _follow_redirect(url)

    if "google.com/maps" in url or "maps.google.com" in url:
        data = _parse_google_maps(url)
        return {**_EMPTY_RESULT, **data}

    raise ValueError("URL non riconosciuto. Incolla un link Facebook o Google Maps.")
