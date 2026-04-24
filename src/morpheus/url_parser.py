from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

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
    "events", "photo", "video", "watch", "marketplace", "profile.php",
})

_DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _slug_to_name(slug: str) -> str:
    # If no separators, preserve original casing (e.g. "CartoleriaMarina")
    if not re.search(r"[-_.]", slug):
        return slug.strip()
    name = re.sub(r"[-_.]", " ", slug).strip()
    return " ".join(word.capitalize() for word in name.split() if word)


def _fetch_og_tags(url: str, timeout: int = 6) -> dict:
    """Try to fetch a page and extract Open Graph meta tags. Best effort."""
    try:
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": _DESKTOP_UA,
                "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
            },
        )
        if resp.status_code != 200:
            return {}
        html = resp.text
    except Exception:
        return {}

    tags: dict = {}
    for match in re.finditer(
        r'<meta[^>]+property=["\']og:([^"\']+)["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    ):
        tags[match.group(1).lower()] = match.group(2)
    for match in re.finditer(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:([^"\']+)["\']',
        html,
        re.IGNORECASE,
    ):
        tags.setdefault(match.group(2).lower(), match.group(1))
    return tags


def _parse_facebook(url: str) -> dict:
    match = re.search(r"facebook\.com/([^/?#]+)", url)
    if not match:
        return {}
    slug = match.group(1).rstrip("/")
    if slug.lower() in _FB_SKIP_SLUGS:
        return {}

    nome = _slug_to_name(slug)
    facebook_url = f"https://www.facebook.com/{slug}"
    result = {"nome": nome, "facebook_url": facebook_url}

    og = _fetch_og_tags(facebook_url)
    og_title = og.get("title", "").strip()
    if og_title and og_title.lower() not in {"facebook", "log in to facebook"}:
        result["nome"] = og_title
    og_desc = og.get("description", "").strip()
    if og_desc:
        phone = _extract_phone(og_desc)
        if phone:
            result["telefono"] = phone
        site = _extract_website(og_desc)
        if site:
            result["sito"] = site
    return result


_PHONE_RE = re.compile(r"(?:\+39[\s.-]?)?(?:0\d{1,3}[\s./-]?\d{5,8}|3\d{2}[\s./-]?\d{6,7})")
_WEBSITE_RE = re.compile(r"https?://(?!(?:www\.)?facebook\.com)[\w.-]+\.[a-z]{2,}(?:/[^\s]*)?", re.IGNORECASE)


def _extract_phone(text: str) -> str:
    match = _PHONE_RE.search(text)
    return match.group(0).strip() if match else ""


def _extract_website(text: str) -> str:
    match = _WEBSITE_RE.search(text)
    return match.group(0).strip() if match else ""


def _parse_google_maps(url: str) -> dict:
    result: dict = {}

    # /maps/place/NOME+PATH/@lat,lon/... — may be "Nome,+Via+X,+1,+Città+VA,+Italia"
    place_match = re.search(r"/maps/place/([^/@?]+)", url)
    if place_match:
        raw = unquote(place_match.group(1)).replace("+", " ").strip()
        if raw:
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            if parts:
                result["nome"] = parts[0]
                # Try to detect Italian city/province from trailing parts:
                # typical order: Nome, Indirizzo, [CAP] Città VA, Italia
                if len(parts) >= 2:
                    addr_parts = [p for p in parts[1:] if p.lower() != "italia"]
                    if addr_parts:
                        comune = _detect_comune(addr_parts)
                        if comune:
                            result["comune"] = comune
                        # indirizzo = street part + optional standalone civic number
                        street = ""
                        for i, part in enumerate(addr_parts):
                            if part == result.get("comune") or _is_city_like(part):
                                continue
                            if not street:
                                street = part
                                # Next token is just digits? treat as civico
                                if i + 1 < len(addr_parts) and re.fullmatch(r"\d+\w?", addr_parts[i + 1]):
                                    street = f"{street} {addr_parts[i + 1]}"
                                break
                        if street:
                            result["indirizzo"] = street

    # ?q=Nome+Via  — used in /maps/search/ or /maps?q=
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    q_val = (qs.get("q") or qs.get("query") or [""])[0]
    if q_val and "nome" not in result:
        q_clean = q_val.replace("+", " ").strip()
        result["nome"] = q_clean.split(",")[0].strip()

    # !3d{LAT}!4d{LON} — precise coords from data= block
    fine_match = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url)
    if fine_match:
        try:
            result["lat"] = float(fine_match.group(1))
            result["lon"] = float(fine_match.group(2))
        except ValueError:
            pass

    # @lat,lon,zoom — viewport center, fallback if no !3d!4d
    if "lat" not in result or result.get("lat") is None:
        coord_match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
        if coord_match:
            try:
                result["lat"] = float(coord_match.group(1))
                result["lon"] = float(coord_match.group(2))
            except ValueError:
                pass

    return result


_PROVINCE_CODES = frozenset({
    "AG", "AL", "AN", "AO", "AP", "AQ", "AR", "AT", "AV", "BA", "BG", "BI", "BL", "BN",
    "BO", "BR", "BS", "BT", "BZ", "CA", "CB", "CE", "CH", "CL", "CN", "CO", "CR", "CS",
    "CT", "CZ", "EN", "FC", "FE", "FG", "FI", "FM", "FR", "GE", "GO", "GR", "IM", "IS",
    "KR", "LC", "LE", "LI", "LO", "LT", "LU", "MB", "MC", "ME", "MI", "MN", "MO", "MS",
    "MT", "NA", "NO", "NU", "OR", "PA", "PC", "PD", "PE", "PG", "PI", "PN", "PO", "PR",
    "PT", "PU", "PV", "PZ", "RA", "RC", "RE", "RG", "RI", "RM", "RN", "RO", "SA", "SI",
    "SO", "SP", "SR", "SS", "SU", "SV", "TA", "TE", "TN", "TO", "TP", "TR", "TS", "TV",
    "UD", "VA", "VB", "VC", "VE", "VI", "VR", "VT", "VV",
})


def _is_city_like(text: str) -> bool:
    """Heuristic: is this string likely to contain a city name + province code?"""
    tokens = text.strip().split()
    if not tokens:
        return False
    last = tokens[-1].upper()
    return last in _PROVINCE_CODES


def _detect_comune(parts: list[str]) -> str:
    """From a list of comma-separated address parts, extract the city.

    Typical Italian Maps format: 'Via Roma 1', '21100 Varese VA', 'Italia'.
    """
    for part in parts:
        # Match: optional CAP (5 digits) + city words + optional province code
        match = re.match(r"^\s*(?:\d{5}\s+)?([A-Za-zÀ-ÿ'\s.-]+?)(?:\s+([A-Z]{2}))?\s*$", part)
        if match and match.group(2) and match.group(2) in _PROVINCE_CODES:
            return match.group(1).strip()
    # Fallback: part without digits/province code = likely just city
    for part in parts:
        stripped = part.strip()
        if not re.search(r"\d", stripped) and len(stripped.split()) <= 4:
            return stripped
    return ""


def _follow_redirect(url: str, timeout: int = 8) -> str:
    try:
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": _DESKTOP_UA},
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

    if "facebook.com" in url or "fb.com" in url or "fb.me" in url:
        if "fb.me" in url or "fb.com" in url:
            url = _follow_redirect(url)
        data = _parse_facebook(url)
        return {**_EMPTY_RESULT, **data}

    if "maps.app.goo.gl" in url or "goo.gl/maps" in url:
        url = _follow_redirect(url)

    if "google." in url and ("/maps" in url or "maps." in url):
        data = _parse_google_maps(url)
        return {**_EMPTY_RESULT, **data}

    raise ValueError("URL non riconosciuto. Incolla un link Facebook o Google Maps.")
