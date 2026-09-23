"""Studio 28 — https://www.cinema-studio28.fr/

Showtimes: the Cotecine booking site "monticket"
https://www.monticketstudio28.cotecine.fr/reserver/ (exact datetimes and VO/VF,
see platforms/cotecine.py).
Details: the WordPress "Modern Events Calendar" posts, one per film, from the
REST API /wp-json/wp/v2/mec-events (genre, duration, director, synopsis,
poster, "Avant première" category), matched by title.
"""

import html
import re
import time

from bs4 import BeautifulSoup

from ..common import Cinema, clean, get, norm_title, parse_duration, show
from ..platforms import cotecine

CINEMA = Cinema(
    id='studio-28',
    name='Studio 28',
    address='10 rue Tholozé, 75018 Paris',
    lat=48.886138,
    lon=2.335388,
    url='https://www.cinema-studio28.fr/',
    allocine='C0061',
    group='Ailleurs',
    tags=['Art et essai'],
)

SITE = "https://www.monticketstudio28.cotecine.fr"
MEC_API = "https://www.cinema-studio28.fr/wp-json/wp/v2/mec-events"
CATEGORY_TAGS = {"avant premiere": "Avant-première", "avant-premiere": "Avant-première"}


def _names(text: str) -> str:
    """'Andrew STANTON, McKenna HARRIS' -> 'Andrew Stanton, McKenna Harris'."""
    return " ".join(w.title() if w.isupper() and len(w) > 1 else w for w in text.split())


def _wp_films() -> dict[str, dict]:
    """norm title -> details, from the 50 latest film posts."""
    for attempt in range(3):  # the server sometimes answers with an empty body
        try:
            posts = get(MEC_API, params={"per_page": 50, "_embed": "wp:featuredmedia,wp:term"}).json()
            break
        except ValueError:
            if attempt == 2:
                raise
            time.sleep(2)
    out = {}
    for p in posts:
        title = html.unescape(p["title"]["rendered"])
        body = BeautifulSoup(p["content"]["rendered"], "lxml")
        info: dict = {"url": p.get("link"), "tags": set()}
        syn = []
        for par in body.find_all("p"):
            t = clean(par.get_text(" "))
            if not t or par.find("iframe"):
                continue
            if t.startswith("Durée"):
                info["duration"] = parse_duration(t.lower())
            elif t.startswith("Réalisé par"):
                info["director"] = _names(t.removeprefix("Réalisé par").strip(" .:"))
            elif "Genre :" in t or t.startswith("Avec"):
                continue
            else:
                syn.append(t)
        info["synopsis"] = " ".join(syn) or None
        emb = p.get("_embedded", {})
        for group in emb.get("wp:term", []):
            for term in group:
                if term.get("taxonomy") == "mec_category":
                    key = clean(html.unescape(term["name"])).lower().replace("è", "e")
                    if key in CATEGORY_TAGS:
                        info["tags"].add(CATEGORY_TAGS[key])
        media = emb.get("wp:featuredmedia") or [{}]
        info["poster"] = media[0].get("source_url")
        out.setdefault(norm_title(title), info)
    return out


def scrape() -> list[dict]:
    films = cotecine.films(SITE)
    try:
        prog = cotecine.programme(SITE)
    except Exception:
        prog = {}
    try:
        wp = _wp_films()
    except Exception:
        wp = {}
    shows = []
    for fid, title in films.items():
        times = cotecine.seances(SITE, fid)
        time.sleep(cotecine.PAUSE)
        w = wp.get(norm_title(title), {})
        p = prog.get(fid, {})
        for start, version in times:
            shows.append(show(
                CINEMA.id, title, start,
                version=version,
                url=cotecine.booking_url(SITE, fid),
                director=w.get("director"),
                duration=w.get("duration") or p.get("duration"),
                tags=sorted(w.get("tags", ())),
                synopsis=w.get("synopsis"),
                poster=w.get("poster") or p.get("poster"),
            ))
    shows.sort(key=lambda s: s["start"])
    return shows
