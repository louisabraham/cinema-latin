"""Le Lucernaire — https://www.lucernaire.fr/

The Lucernaire is also a theatre. Its cinema booking site (Cotecine,
https://lucernaire-vad.cotecine.fr/) only holds film showings, so it is the
showtime source (exact times and version, see platforms/cotecine.py). The
WordPress pages https://www.lucernaire.fr/cinema/<slug>/ add the director,
year, synopsis, poster and event labels for the films of the current week.
"""

import re
import time

from bs4 import BeautifulSoup

from ..common import Cinema, clean, get, parse_duration, show, soup, strip_accents
from ..platforms import cotecine

CINEMA = Cinema(
    id='lucernaire',
    name='Le Lucernaire',
    address='53 rue Notre-Dame des Champs, 75006 Paris',
    lat=48.844259,
    lon=2.33046,
    url='https://www.lucernaire.fr/',
    allocine='C0093',
    group='Quartier Latin',
    tags=['Art et essai'],
)

ACCOUNT = "lucernaire-vad"
LIST_URL = "https://www.lucernaire.fr/cinema/"
EVENT_TYPES = {"evenement": "Évènement", "jeune public": "Jeune public"}


def _slug(s: str) -> str:
    s = strip_accents(s.lower()).replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _wp_pages() -> dict[str, dict]:
    """slug -> {"url", "tags"} from the WordPress cinema listing."""
    s = soup(LIST_URL)
    out: dict[str, dict] = {}
    for a in s.select("a[href*='lucernaire.fr/cinema/']"):
        m = re.search(r"/cinema/([^/]+)/?$", a["href"])
        if not m:
            continue
        page = out.setdefault(m.group(1), {"url": a["href"], "tags": set()})
        box = a.find_parent(class_=re.compile(r"event-thumbnail|mea-spectacle"))
        for d in box.select(".event-thumbnail-date") if box else []:
            label = clean(d.get_text()).split(":")[0]
            if "//" in label:  # "Dimanche 27 septembre // L'Enfance de l'Art"
                page["tags"].add(clean(label.split("//", 1)[1]))
    return out


def _wp_film(url: str) -> dict:
    s = BeautifulSoup(get(url).content, "lxml")
    info: dict = {"url": url, "tags": set()}
    typ = s.select_one(".spectacle-intro p.type")
    for t in (typ.get_text().split(",") if typ else []):
        key = strip_accents(clean(t) or "").lower()
        if key in EVENT_TYPES:
            info["tags"].add(EVENT_TYPES[key])
    ppl = s.select_one(".spectacle-subtitle .people")
    if ppl:
        d = re.sub(r"^de\s+", "", clean(ppl.get_text()) or "")
        info["director"] = d or None
    dur = s.select_one(".spectacle-subtitle .time strong")
    info["duration"] = parse_duration(dur.get_text()) if dur else None
    desc = s.select_one(".spectacle-intro .desc")
    if desc:
        syn = []  # the ".accroche" line (festival, tagline) is not a tag: skip it
        for p in desc.find_all("p"):
            t = clean(p.get_text(" "))
            if not t:
                continue
            m = re.match(r"^\((.*?)(\d{4})\s*\)\s*(.*)$", t)
            if m and "year" not in info:
                info["year"] = int(m.group(2))
                info["version_hint"] = m.group(3)
            elif not t.startswith("Avec "):
                syn.append(t)
        info["synopsis"] = " ".join(syn) or None
    og = s.find("meta", property="og:image")
    info["poster"] = og["content"] if og else None
    return info


def scrape() -> list[dict]:
    films = cotecine.films(ACCOUNT)
    try:
        prog = cotecine.programme(ACCOUNT)
    except Exception:
        prog = {}
    try:
        pages = _wp_pages()
    except Exception:
        pages = {}
    by_slug = {}
    for slug, page in pages.items():
        by_slug.setdefault(slug, page)
        by_slug.setdefault(re.sub(r"-\d+$", "", slug), page)

    shows = []
    for fid, title in films.items():
        times = cotecine.seances(ACCOUNT, fid)
        time.sleep(cotecine.PAUSE)
        if not times:
            continue
        meta = dict(prog.get(fid, {}))
        tags = set()
        page = by_slug.get(_slug(title))
        if page:
            try:
                wp = _wp_film(page["url"])
                time.sleep(cotecine.PAUSE)
            except Exception:
                wp = {}
            tags |= page["tags"] | wp.pop("tags", set())
            wp.pop("version_hint", None)
            wp.pop("url", None)
            meta.update({k: v for k, v in wp.items() if v})
        for start, version in times:
            shows.append(show(
                CINEMA.id, title, start,
                version=version,
                url=cotecine.booking_url(ACCOUNT, fid),
                tags=sorted(tags),
                **meta,
            ))
    shows.sort(key=lambda s: s["start"])
    return shows
