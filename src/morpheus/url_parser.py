from __future__ import annotations

import re
from urllib.parse import unquote

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
    "events", "photo", "video", "watch", "marketplace",
})


def _slug_to_name(slug: str) -> str:
    name = re.sub(r"[-_.]", " ", slug).strip()
    return " ".join(word.capitalize() for word in name.split() if word)


def _parse_facebook(url: str) -> dict:
    match = re.search(r"facebook\.com/([^/?#]+)", url)
    if not match:
        return {}
    slug = match.group(1).rstrip("/")
    if slug in _FB_SKIP_SLUGS:
        return {}
    nome = _slug_to_name(slug)
    facebook_url = f"https://www.facebook.com/{slug}"
    return {"nome": nome, "facebook_url": facebook_url}


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
