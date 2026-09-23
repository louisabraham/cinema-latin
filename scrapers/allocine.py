"""Allociné internal JSON API.

Used for three things:
  1. film metadata (synopsis, poster, genres...) for the enrichment step,
  2. fallback showtimes when a cinema's own scraper fails,
  3. cross-check of the site scrapers (tests/compare.py).
"""

from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from urllib.parse import quote

from .common import get, parse_duration, show, to_paris, window

BASE = "https://www.allocine.fr"


def _json(path: str) -> dict:
    r = get(BASE + path, headers={"Accept": "application/json"})
    return r.json()


def movie_meta(m: dict) -> dict:
    """Extract the fields we keep from an Allociné movie object."""
    data = m.get("data") or {}
    stats = m.get("stats") or {}
    directors = [
        f"{c['person'].get('firstName') or ''} {c['person'].get('lastName') or ''}".strip()
        for c in m.get("credits") or []
        if (c.get("position") or {}).get("name") == "DIRECTOR" and c.get("person")
    ]
    cast = []
    for e in ((m.get("cast") or {}).get("edges") or [])[:4]:
        a = (e.get("node") or {}).get("actor") or {}
        if a:
            cast.append(f"{a.get('firstName') or ''} {a.get('lastName') or ''}".strip())
    synopsis = m.get("synopsisFull") or m.get("synopsis")
    if synopsis:
        synopsis = re.sub(r"<[^>]+>", "", synopsis).strip()
    return {
        "allocine_id": int(m["internalId"]),
        "title": m.get("title"),
        "original_title": m.get("originalTitle"),
        "year": data.get("productionYear"),
        "duration": parse_duration(m.get("runtime")),
        "directors": directors,
        "cast": cast,
        "genres": [g["translate"] for g in m.get("genres") or []],
        "countries": [c.get("localizedName") or c.get("name") for c in m.get("countries") or []],
        "synopsis": synopsis,
        "poster": (m.get("poster") or {}).get("url"),
        "ratings": {
            "allocine_press": (stats.get("pressReview") or {}).get("score"),
            "allocine_spect": (stats.get("userRating") or {}).get("score"),
        },
    }


def theater_day(code: str, day) -> list[dict]:
    """All results (movie + showtimes) for one theater and one day, all pages."""
    out, page = [], 1
    while True:
        suffix = f"p-{page}/" if page > 1 else ""
        d = _json(f"/_/showtimes/theater-{code}/d-{day.isoformat()}/{suffix}")
        if d.get("error"):
            break
        out += d.get("results") or []
        pag = d.get("pagination") or {}
        if page >= (pag.get("totalPages") or 1):
            break
        page += 1
    return out


def theater_showtimes(cinema_id: str, code: str, days: int = 14) -> list[dict]:
    """Standard showtime dicts for an Allociné theater code."""
    shows = []
    for day in window(days):
        for res in theater_day(code, day):
            meta = movie_meta(res["movie"])
            for group, sts in (res.get("showtimes") or {}).items():
                for st in sts:
                    start = to_paris(datetime.fromisoformat(st["startsAt"]))
                    dv = st.get("diffusionVersion")
                    version = {"ORIGINAL": "VO", "LOCAL": "VF", "DUBBED": "VF"}.get(dv)
                    url = None
                    for t in (st.get("data") or {}).get("ticketing") or []:
                        if t.get("provider") == "default" and t.get("urls"):
                            url = t["urls"][0]
                    shows.append(show(
                        cinema_id, meta["title"], start,
                        version=version,
                        url=url or f"{BASE}/seance/salle_gen_csalle={code}.html",
                        original_title=meta["original_title"],
                        director=", ".join(meta["directors"]) or None,
                        year=meta["year"],
                        duration=meta["duration"],
                        allocine_id=meta["allocine_id"],
                    ))
    return shows


def theater_movies(code: str, days: int = 14) -> dict[int, dict]:
    """allocine_id -> movie meta, for every film shown by a theater."""
    out = {}
    for day in window(days):
        for res in theater_day(code, day):
            meta = movie_meta(res["movie"])
            out[meta["allocine_id"]] = meta
    return out


@lru_cache(maxsize=None)
def search(query: str) -> list[dict]:
    """Autocomplete search. Returns [{'id', 'title', 'original_title', 'year', 'directors'}]."""
    q = quote(query.strip()[:80])
    try:
        d = _json(f"/_/autocomplete/mobile/movie/{q}")
    except Exception:
        return []
    out = []
    for r in d.get("results") or []:
        if r.get("entity_type") != "movie":
            continue
        data = r.get("data") or {}
        out.append({
            "id": int(r["entity_id"]),
            "title": r.get("label"),
            "original_title": r.get("original_label"),
            "year": int(data["year"]) if str(data.get("year") or "").isdigit() else None,
            "directors": data.get("director_name") or [],
            "poster_path": data.get("poster_path"),
        })
    return out


@lru_cache(maxsize=None)
def movie_page(allocine_id: int) -> dict:
    """Metadata scraped from a film page, for films not found in any theater feed."""
    from bs4 import BeautifulSoup
    import json

    r = get(f"{BASE}/film/fichefilm_gen_cfilm={allocine_id}.html")
    s = BeautifulSoup(r.content, "lxml")
    meta: dict = {"allocine_id": allocine_id}
    for tag in s.select('script[type="application/ld+json"]'):
        try:
            ld = json.loads(tag.string or "")
        except ValueError:
            continue
        if isinstance(ld, dict) and ld.get("@type") == "Movie":
            meta["title"] = ld.get("name")
            img = ld.get("image")
            meta["poster"] = img.get("url") if isinstance(img, dict) else img
            meta["genres"] = ld.get("genre") if isinstance(ld.get("genre"), list) else [ld.get("genre")] if ld.get("genre") else []
            dirs = ld.get("director") or []
            dirs = dirs if isinstance(dirs, list) else [dirs]
            meta["directors"] = [d.get("name") for d in dirs if isinstance(d, dict)]
            meta["duration"] = parse_duration(ld.get("duration"))
            if ld.get("dateCreated"):
                meta["year"] = int(str(ld["dateCreated"])[:4])
    syn = s.select_one("section.synopsis-section .content-txt, #synopsis-details .content-txt")
    if syn:
        meta["synopsis"] = syn.get_text(" ", strip=True)
    return meta
