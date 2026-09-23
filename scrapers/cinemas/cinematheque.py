"""La Cinémathèque française — https://www.cinematheque.fr/

Source: the monthly calendar pages `/calendrier/MM-YYYY.html` (server-rendered
HTML, one `a.show` block per séance with time, room code, cycle and films),
then one `/seance/<id>.html` page per séance in the window for the details
(room name, duration, original title, format, version, booking link, poster).
"""

import re
import time
from datetime import timedelta

from ..common import Cinema, clean, combine, get, now, parse_duration, parse_fr_date, parse_time, show
from bs4 import BeautifulSoup

CINEMA = Cinema(
    id='cinematheque',
    name='La Cinémathèque française',
    address='51 rue de Bercy, 75012 Paris',
    lat=48.836826,
    lon=2.382384,
    url='https://www.cinematheque.fr/',
    allocine='C1559',
    group='Ailleurs',
    tags=['Répertoire'],
)

BASE = "https://www.cinematheque.fr/"
DAYS = 14
ROOMS = {
    "HL": "Salle Henri Langlois",
    "GF": "Salle Georges Franju",
    "JE": "Salle Jean Epstein",
}
# Séances without a listed film that are not screenings.
NOT_FILM_RE = re.compile(r"conf[ée]rence|signature|atelier|visite|stage", re.I)
FORMAT_RE = re.compile(r"\b(35 ?mm|16 ?mm|70 ?mm|9,5 ?mm)\b", re.I)


def _soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(get(url).content, "lxml")


def _txt(el) -> str | None:
    return clean(el.get_text(" ")) if el is not None else None


def _rem_tags(text: str) -> list[str]:
    t = text.lower()
    tags = []
    if "avant-premi" in t:
        tags.append("Avant-première")
    if "accompagnement musical" in t or "ciné-concert" in t or "cine-concert" in t:
        tags.append("Ciné-concert")
    if re.search(r"dialogue|rencontre|en présence|discussion|table ronde|leçon de cinéma", t):
        tags.append("Rencontre")
    if "présentée par" in t or "presentee par" in t:
        tags.append("Présentation")
    return tags


def _calendar_shows(start, end) -> list[dict]:
    """Parse month calendar pages covering [start, end)."""
    months = []
    d = start.replace(day=1)
    while d < end:
        months.append((d.month, d.year))
        d = (d + timedelta(days=32)).replace(day=1)
    out = []
    for i, (m, y) in enumerate(months):
        if i:
            time.sleep(1)
        s = _soup(f"{BASE}calendrier/{m:02d}-{y}.html")
        for day in s.select("div.day"):
            ddiv = day.select_one(".date")
            if ddiv is None:
                continue
            dt = parse_fr_date(ddiv.get_text(" "))
            if dt is None or not (start <= dt < end):
                continue
            for a in day.select("a.show"):
                hm = parse_time(_txt(a.select_one(".time")) or "")
                if not hm:
                    continue
                room = _txt(a.select_one(".salle"))
                films, extras = [], []
                for li in a.select("li.film"):
                    tel = li.select_one(".title")
                    # direct text only: child spans hold "CM" badges and counters
                    title = clean(" ".join(tel.find_all(string=True, recursive=False))) if tel else None
                    real = _txt(li.select_one(".real"))
                    if real:
                        films.append((title, real))
                    elif title:
                        extras.append(title)
                rems = [_txt(r) for r in a.select(".rem")]
                cycle = _txt(a.select_one(".cycle"))
                text = " ".join(filter(None, [*extras, *rems]))
                if not films:
                    # keep programmes of short/student films in cinema rooms, drop talks & workshops
                    if room not in ROOMS or not extras or NOT_FILM_RE.search(text):
                        continue
                out.append({
                    "start": combine(dt, hm),
                    "href": BASE + a["href"].lstrip("/"),
                    "room": room,
                    "cycle": cycle,
                    "films": films,
                    "extras": extras,
                    "text": text,
                })
    return out


def _details(url: str) -> dict:
    s = _soup(url)
    info: dict = {}
    sub = s.select_one(".seance .date h1.sub")
    info["room"] = _txt(sub)
    info["duration"] = parse_duration(_txt(s.select_one(".minTotal")))
    img = s.select_one("figure img.affiche")
    if img and img.get("src"):
        info["poster"] = img["src"]
    for a in s.select('a[href*="billetterie.cinematheque.fr"]'):
        if "identification" not in a["href"]:
            info["booking"] = a["href"]
            break
    films = []
    for f in s.select(".films .film"):
        tech = ""
        intro = f.select_one(".intro")
        if intro:
            for dv in intro.find_all("div", recursive=False):
                t = _txt(dv) or ""
                if "/" in t:
                    tech = t
                    break
        syn = _txt(f.select_one(".synopsys"))
        films.append({
            "title": _txt(f.select_one("a.titre")),
            "original_title": _txt(f.select_one("span.sub")),
            "director": _txt(f.select_one(".realisateur")),
            "tech": tech,
            "synopsis": syn,
        })
    info["films"] = films
    return info


def _version(tech: str) -> str | None:
    parts = {p.strip().upper() for p in tech.split("/")}
    if parts & {"VOSTF", "VOSTA", "VO", "VOSTANG", "VOSTFR", "VOSTA+F"} or any(p.startswith("VOST") for p in parts):
        return "VO"
    if "VF" in parts or "VERSION FRANÇAISE" in parts:
        return "VF"
    return None


# Allociné splits multi-film séances into separate short films: do not add them.
ALLOCINE_COMPLEMENT = False


def scrape() -> list[dict]:
    start = now().date()
    end = start + timedelta(days=DAYS)
    cutoff = now() - timedelta(minutes=15)
    out = []
    for sh in _calendar_shows(start, end):
        if sh["start"] < cutoff:
            continue
        time.sleep(1)
        try:
            det = _details(sh["href"])
        except Exception:
            det = {"films": []}
        films = sh["films"]
        if films:
            names = [t for t, _ in films if t]
            title = " / ".join(names[:3])
            if len(names) > 3:
                title += f" + {len(names) - 3} films"
        else:
            title = sh["extras"][0]
        tags = []
        if sh["cycle"]:
            tags.append(sh["cycle"])
        tags += _rem_tags(sh["text"])
        dfilms = det["films"]
        # first real film of the séance (skip talks listed as "films")
        main = next((f for f in dfilms if f["tech"]), dfilms[0] if dfilms else None)
        techs = " / ".join(f["tech"] for f in dfilms)
        for m in FORMAT_RE.findall(techs):
            fmt = m.replace(" ", "").lower()
            if fmt not in tags:
                tags.append(fmt)
        if "INT.FR" in techs.upper() or "MUET" in techs.upper():
            tags.append("Muet")
        if re.search(r"version restaurée", techs, re.I):
            tags.append("Version restaurée")
        extra = {}
        if len(films) == 1:
            director, _, year = films[0][1].rpartition(",")
            extra["director"] = clean(director) or (main or {}).get("director")
            if year.strip().isdigit():
                extra["year"] = int(year)
            if main:
                extra["original_title"] = main["original_title"]
        if main:
            extra["version"] = _version(main["tech"])
            extra["synopsis"] = main["synopsis"]
        room = det.get("room") or ROOMS.get(sh["room"] or "", sh["room"])
        out.append(show(
            CINEMA.id,
            title,
            sh["start"],
            url=det.get("booking") or sh["href"],
            room=room,
            duration=det.get("duration"),
            poster=det.get("poster"),
            tags=list(dict.fromkeys(tags)),
            **extra,
        ))
    return out
