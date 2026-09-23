"""Studio des Ursulines — https://www.studiodesursulines.com/

Showtimes come from the cine.boutique ticketing API (account
"parisstudioursulines", see platforms/cineboutique.py): exact times, version,
booking link, director, year, Allociné id. The API titles are upper case
without accents, so the WordPress home page (which lists every film with its
tag: cycle, festival, age) gives the display title and the tags.
"""

import re

from ..common import Cinema, clean, norm_title, soup
from ..platforms import cineboutique

CINEMA = Cinema(
    id='ursulines',
    name='Studio des Ursulines',
    address='10 rue des Ursulines, 75005 Paris',
    lat=48.842722,
    lon=2.342033,
    url='https://www.studiodesursulines.com/',
    allocine='C0083',
    group='Quartier Latin',
    tags=['Art et essai'],
)

ACCOUNT = "parisstudioursulines"
FILM_RE = re.compile(r"top\.location='(https://www\.studiodesursulines\.com/film/[^']+)'")
PREFIX_RE = re.compile(r"^\s*(avant[- ]premi[eè]re|ciné[- ]club|rencontre|séance spéciale)\s*:\s*", re.I)


def _home_films() -> dict[str, dict]:
    """norm title -> {"title", "tags", "url"} from the WordPress home page."""
    home = soup(CINEMA.url)
    films: dict[str, dict] = {}
    for div in home.select("[onclick]"):
        m = FILM_RE.search(div.get("onclick", ""))
        t = div.select_one(".movietitle") or div.select_one(".slidertitle > div")
        if not m or not t:
            continue
        title = clean(t.get_text())
        tags = set()
        p = PREFIX_RE.match(title)
        if p:
            title = title[p.end():]
            w = p.group(1).lower()
            tags.add("Avant-première" if w.startswith("avant") else p.group(1).capitalize())
        for tag in div.select(".movietag, .eventtag"):
            if clean(tag.get_text()):
                tags.add(clean(tag.get_text()))
        f = films.setdefault(norm_title(title), {"title": title, "tags": set(), "url": m.group(1)})
        f["tags"] |= tags
    return films


def _pretty(title: str) -> str:
    """'MONSTRES & CIE' -> 'Monstres & cie' for titles missing from the home page."""
    return title[:1].upper() + title[1:].lower() if title.isupper() else title


def scrape() -> list[dict]:
    shows = cineboutique.showtimes(CINEMA.id, ACCOUNT)
    try:
        films = _home_films()
    except Exception:
        films = {}
    for s in shows:
        f = films.get(norm_title(s["title"]))
        if f:
            s["title"] = f["title"]
            tags = sorted(set(s.get("tags", [])) | f["tags"])
            if tags:
                s["tags"] = tags
        else:
            s["title"] = _pretty(s["title"])
    return shows
