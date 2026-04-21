"""
Enrichment Facebook: cerca il profilo Facebook pubblico dei lead.

Usa due motori di ricerca (Brave + DuckDuckGo HTML) con rate limiter separati.
Ogni motore ha il suo canale indipendente → ~4 req/s totali invece di ~2.

Non richiede API key.
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .db import fetch_facebook_candidates, merge_lead_enrichment
from .paths import DB_PATH

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

MAX_WORKERS = 5

# ── Configurazione motori di ricerca ──────────────────────────────────────────
# Ogni motore ha il suo rate limiter indipendente: i thread possono prenotare
# slot su motori diversi in parallelo senza bloccarsi a vicenda.

def _make_engine(name: str, url: str, interval: float) -> dict:
    return {
        "name": name,
        "url": url,
        "interval": interval,
        "last_time": 0.0,
        "lock": threading.Lock(),
    }

_ENGINES: list[dict] = [
    _make_engine("brave", "https://search.brave.com/search", interval=0.5),
    _make_engine("ddg",   "https://html.duckduckgo.com/html/", interval=0.6),
]

_rr_lock = threading.Lock()
_rr_idx = 0  # round-robin counter


def _next_engine() -> dict:
    """Restituisce il prossimo motore in round-robin."""
    global _rr_idx
    with _rr_lock:
        engine = _ENGINES[_rr_idx % len(_ENGINES)]
        _rr_idx += 1
    return engine


def _other_engine(current: dict) -> dict:
    """Restituisce l'altro motore (per fallback)."""
    for e in _ENGINES:
        if e is not current:
            return e
    return current


# Sotto-percorsi Facebook da ignorare
_FB_SKIP_PATHS = {
    "/login", "/signup", "/sharer", "/share", "/dialog",
    "/watch", "/photo", "/photos", "/video", "/videos",
    "/hashtag", "/groups", "/events", "/marketplace",
    "/help", "/privacy", "/policies", "/ads", "/places",
    "/bookmarks", "/gaming", "/notifications", "/messages",
    "/friends", "/profile.php",
}

_STOP_TOKENS = {
    "bar", "ristorante", "pizza", "trattoria", "osteria",
    "caffe", "cafe", "hotel", "albergo", "farmacia", "negozio",
    "studio", "centro", "san", "santa", "via", "del", "della",
    "dei", "delle", "di", "il", "la", "le", "lo", "gli",
}


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_ = nfkd.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", ascii_).strip()


def _name_tokens(nome: str) -> list[str]:
    return [t for t in _normalize(nome).split() if len(t) > 2 and t not in _STOP_TOKENS]


def _is_valid_fb_page(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if "facebook.com" not in (parsed.netloc or ""):
        return False
    path = parsed.path.rstrip("/")
    if not path or path == "/":
        return False
    first_segment = "/" + path.lstrip("/").split("/")[0]
    if first_segment in _FB_SKIP_PATHS:
        return False
    if re.match(r"^/\d+$", path):
        return False
    return True


def _canonical_fb_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        path = "/" + "/".join(
            s for s in parsed.path.strip("/").split("/")
            if s and s.lower() not in {"about", "posts", "reviews", "photos", "videos"}
        )
        return f"https://www.facebook.com{path}"
    except Exception:
        return url


def _score_fb_url(url: str, nome: str, comune: str) -> int:
    if not _is_valid_fb_page(url):
        return 0
    slug = _normalize(urlparse(url).path)
    tokens = _name_tokens(nome)
    comune_norm = _normalize(comune)
    score = 1
    score += sum(1 for t in tokens if t in slug) * 3
    if comune_norm and comune_norm in slug:
        score += 2
    return score


# ── Rate limiting per motore ───────────────────────────────────────────────────

def _book_slot(engine: dict) -> float:
    """Prenota il prossimo slot libero per l'engine, ritorna il timestamp di partenza."""
    with engine["lock"]:
        now = time.monotonic()
        fire_at = max(now, engine["last_time"] + engine["interval"])
        engine["last_time"] = fire_at
    return fire_at


def _apply_penalty(engine: dict, penalty: float) -> None:
    """Su 429: sposta last_time avanti per rallentare tutti i thread su quest'engine."""
    with engine["lock"]:
        engine["last_time"] = max(engine["last_time"], time.monotonic() + penalty)


# ── Parsing risultati per motore ───────────────────────────────────────────────

def _extract_fb_urls_brave(soup: BeautifulSoup) -> list[str]:
    urls = []
    for sel in [
        "div.snippet[data-type='web'] a[href]",
        "div.result a[href]",
        "article a[href]",
        "a[href*='facebook.com']",
    ]:
        for tag in soup.select(sel):
            href = tag.get("href", "")
            if "facebook.com" in href:
                urls.append(href)
    return urls


def _extract_fb_urls_ddg(soup: BeautifulSoup) -> list[str]:
    """Estrae URL dai risultati DuckDuckGo HTML.

    DDG wrappa i link in redirect del tipo:
      //duckduckgo.com/l/?uddg=<encoded_url>&rut=...
    oppure li espone direttamente in <a class="result__a">.
    """
    urls = []
    for a in soup.select("a.result__a, a[href*='facebook.com']"):
        href = a.get("href", "")
        if not href:
            continue
        # Unwrap redirect DDG
        if "duckduckgo.com/l/" in href:
            try:
                full = href if href.startswith("http") else "https:" + href
                qs = parse_qs(urlparse(full).query)
                decoded = unquote(qs.get("uddg", [""])[0])
                if decoded:
                    href = decoded
            except Exception:
                pass
        if "facebook.com" in href:
            urls.append(href)
    return urls


def _extract_fb_urls(soup: BeautifulSoup, engine_name: str) -> list[str]:
    if engine_name == "ddg":
        return _extract_fb_urls_ddg(soup)
    return _extract_fb_urls_brave(soup)


# ── Ricerca ────────────────────────────────────────────────────────────────────

def _search_one_engine(
    session: requests.Session,
    engine: dict,
    query: str,
    nome: str,
    comune: str,
    *,
    max_retries: int = 2,
) -> int:
    """Esegue UNA query su UN motore. Ritorna il best_score e aggiorna best_url
    tramite dizionario mutabile di ritorno.

    Ritorna (best_score, best_url).
    """
    params = {"q": query, "source": "web"} if engine["name"] == "brave" else {"q": query}

    for attempt in range(max_retries):
        fire_at = _book_slot(engine)
        wait = fire_at - time.monotonic()
        if wait > 0:
            time.sleep(wait)

        try:
            resp = session.get(engine["url"], params=params, timeout=8)
        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(1.0)
            continue

        if resp.status_code == 429:
            _apply_penalty(engine, 10.0)
            time.sleep(1.0)
            continue
        if resp.status_code >= 400:
            if attempt < max_retries - 1:
                time.sleep(1.0)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        raw_urls = _extract_fb_urls(soup, engine["name"])
        candidates = [
            (s, _canonical_fb_url(u))
            for u in raw_urls
            if (s := _score_fb_url(u, nome, comune)) > 0
        ]
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0]  # (score, url)
        return 0, ""  # nessun risultato ma richiesta ok

    return 0, ""  # tutti i tentativi falliti


def search_facebook_page(
    session: requests.Session,
    nome: str,
    comune: str,
    categoria: str,
    primary_engine: dict,
) -> str:
    """
    Cerca una pagina Facebook per un'attività locale.

    Strategia:
    1. Query con virgolette sul motore primario (round-robin)
    2. Se nessun risultato → stessa query sul motore secondario (fallback)
    3. Se ancora niente → query senza virgolette sul motore primario
    Appena trova qualcosa si ferma.
    """
    query_strict = f'site:facebook.com "{nome}" {comune}'
    query_loose  = f'site:facebook.com {nome} {comune}'
    secondary_engine = _other_engine(primary_engine)

    steps = [
        (primary_engine,   query_strict),
        (secondary_engine, query_strict),
        (primary_engine,   query_loose),
    ]

    for engine, query in steps:
        score, url = _search_one_engine(session, engine, query, nome, comune)
        if score > 0:
            return url

    return ""


def _enrich_one(lead: dict, db_path: Any) -> tuple[str, str]:
    nome     = lead.get("nome") or ""
    comune   = lead.get("comune") or ""
    categoria = lead.get("categoria") or ""
    osm_url  = lead.get("osm_url") or ""

    if not nome or not osm_url or not _name_tokens(nome):
        merge_lead_enrichment(osm_url, facebook_url="N/F", db_path=db_path)
        return osm_url, "N/F"

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Assegna il motore primario in round-robin
    primary = _next_engine()
    fb_url = search_facebook_page(session, nome, comune, categoria, primary)
    result = fb_url if fb_url else "N/F"
    merge_lead_enrichment(osm_url, facebook_url=result, db_path=db_path)
    return osm_url, result


def _optimal_workers(total: int) -> int:
    if total <= 10:
        return 2
    if total <= 50:
        return 3
    return MAX_WORKERS


def enrich_leads_facebook(
    dataset_id: str | None = None,
    *,
    db_path: Any = None,
    max_workers: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, int]:
    """
    Cerca il profilo Facebook per tutti i lead senza facebook_url.
    Usa due motori (Brave + DDG) con rate limiter separati: ~4 req/s totali.
    """
    if db_path is None:
        db_path = DB_PATH

    all_leads = fetch_facebook_candidates(dataset_id, limit=50_000, offset=0, db_path=db_path)
    total = len(all_leads)

    if total == 0:
        if progress_callback:
            progress_callback({
                "progress": 100, "stage": "done",
                "message": "Nessun lead da arricchire.",
                "enriched": 0, "skipped": 0, "total": 0,
            })
        return {"enriched": 0, "skipped": 0, "total": 0}

    workers = max_workers if max_workers is not None else _optimal_workers(total)

    enriched = skipped = processed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_enrich_one, lead, db_path): lead for lead in all_leads}

        for future in as_completed(futures):
            try:
                _, fb_url = future.result()
                if fb_url and fb_url != "N/F":
                    enriched += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1

            processed += 1
            if progress_callback:
                progress_callback({
                    "progress": min(99, int(processed / total * 100)),
                    "stage": "facebook_search",
                    "message": (
                        f"Ricerca Facebook: {processed}/{total} lead "
                        f"({enriched} trovati, {workers} thread, Brave+DDG)."
                    ),
                    "enriched": enriched,
                    "skipped": skipped,
                    "total": total,
                })

    if progress_callback:
        progress_callback({
            "progress": 100,
            "stage": "done",
            "message": f"Enrichment completato: {enriched} profili trovati su {total} lead.",
            "enriched": enriched,
            "skipped": skipped,
            "total": total,
        })

    return {"enriched": enriched, "skipped": skipped, "total": total}
