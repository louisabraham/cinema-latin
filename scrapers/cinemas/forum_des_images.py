"""Forum des images — https://www.forumdesimages.fr/

Source: the Drupal agenda `/agenda?date=month` and `/agenda?date=next_month`
(server-rendered, one `article.session-calendar-teaser-item` per séance with
time, cycle, title, directors and session type), then one session page per
film séance in the window for the details (year, duration, VOSTF, format,
booking link, synopsis).
"""

import re
import time
from datetime import timedelta

from bs4 import BeautifulSoup

from ..common import Cinema, clean, combine, get, now, parse_duration, parse_fr_date, parse_time, show

CINEMA = Cinema(
    id='forum-des-images',
    name='Forum des images',
    address='2 rue du Cinéma, 75001 Paris',
    lat=48.8625,
    lon=2.3455,
    url='https://www.forumdesimages.fr/',
    allocine='C0119',
    group='Ailleurs',
    tags=['Répertoire'],
)

BASE = "https://www.forumdesimages.fr"
DAYS = 14
# Session types that are film screenings ("Film", "Film + débat", "Soirée ..."),
# as opposed to VR experiences, lectures, round tables, role-playing games.
FILM_TYPE_RE = re.compile(r"\bfilm|soir[ée]e|ciné", re.I)


def _soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(get(url).content, "lxml")


def _txt(el) -> str | None:
    return clean(el.get_text(" ")) if el is not None else None


def _agenda(start, end) -> list[dict]:
    pages = ["month"]
    if (end - timedelta(days=1)).month != start.month:
        pages.append("next_month")
    out = []
    for i, p in enumerate(pages):
        if i:
            time.sleep(1)
        s = _soup(f"{BASE}/agenda?program=&type=&date={p}")
        for day in s.select(".agenda-grid-day-content"):
            anchor = day.select_one(".agenda-grid-day-name a[id^=day_]")
            if anchor is None:
                continue
            y, m, d = map(int, anchor["id"][4:].split("-"))
            dt = parse_fr_date(f"{d}/{m}/{y}")
            if not (start <= dt < end):
                continue
            for a in day.select("article.session-calendar-teaser-item"):
                hm = parse_time(_txt(a.select_one(".time")) or "")
                link = a.select_one("h3 a")
                if not hm or link is None:
                    continue
                title = _txt(link)
                stype = _txt(a.select_one(".field-type-session")) or ""
                if not FILM_TYPE_RE.search(stype) or re.search(r"annul", title, re.I):
                    continue
                img = a.select_one(".poster img")
                book = a.select_one('.poster a[href*="billetterie"]')
                out.append({
                    "start": combine(dt, hm),
                    "title": title,
                    "href": BASE + link["href"],
                    "type": stype,
                    "cycle": _txt(a.select_one(".cycle-name")),
                    "directors": [_txt(li) for li in a.select(".directors li")],
                    "poster": BASE + img["src"] if img and img.get("src", "").startswith("/") else None,
                    "booking": book["href"] if book else None,
                })
    return out


def _details(url: str) -> dict:
    s = _soup(url)
    info: dict = {}
    book = s.select_one('.ticketing a[href*="billetterie"]')
    if book:
        info["booking"] = book["href"]
    desc = _txt(s.select_one(".session-info .session-description"))
    info["description"] = desc or ""
    info["text"] = _txt(s.select_one(".session-text-info")) or ""
    films = []
    for art in s.select("article.session-projection-default"):
        h = art.select_one(".projection-header")
        if h is None:
            continue
        items = [_txt(li) for ul in h.select("ul.projection-technical-infos") for li in ul.select("li")]
        items = [x for x in items if x]
        year = next((int(x) for x in items if re.fullmatch(r"(18|19|20)\d\d", x)), None)
        dur = next((parse_duration(x) for x in items if re.fullmatch(r"\d+\s*min", x)), None)
        dirs = h.select_one(".directors ul")
        films.append({
            "title": _txt(h.select_one("h2")),
            "director": ", ".join(_txt(li) for li in dirs.select("li")) if dirs else None,
            "year": year,
            "duration": dur,
            "items": items,
            "synopsis": _txt(art.select_one(".field-body")),
        })
    info["films"] = films
    return info


# Allociné also lists VR sessions and talks that this scraper leaves out.
ALLOCINE_COMPLEMENT = False


def scrape() -> list[dict]:
    start = now().date()
    end = start + timedelta(days=DAYS)
    cutoff = now() - timedelta(minutes=15)
    out = []
    for sh in _agenda(start, end):
        if sh["start"] < cutoff:
            continue
        time.sleep(1)
        try:
            det = _details(sh["href"])
        except Exception:
            det = {"films": [], "description": "", "text": ""}
        title = sh["title"]
        tags = [sh["cycle"]] if sh["cycle"] else []
        if re.match(r"avant-premi[èe]re\s*:?\s*", title, re.I):
            tags.append("Avant-première")
            title = re.sub(r"^avant-premi[èe]re\s*:?\s*", "", title, flags=re.I)
        low = f"{sh['type']} {det['description']}".lower()
        if re.search(r"débat|rencontre|table ronde|en présence|dialogue", low):
            tags.append("Rencontre")
        if "ciné-concert" in low or "cine-concert" in low:
            tags.append("Ciné-concert")
        if "animation" in sh["type"].lower():
            tags.append("Jeune public")
        films = det["films"]
        items = [x for f in films for x in f["items"]]
        for x in items:
            if re.fullmatch(r"(35|16|70)\s*mm", x, re.I):
                tags.append(x.replace(" ", "").lower())
        if re.search(r"version restaurée", det["description"] + det["text"], re.I):
            tags.append("Version restaurée")
        version = None
        if any(re.fullmatch(r"VOST\w*|VO", x) for x in items):
            version = "VO"
        elif "VF" in items:
            version = "VF"
        extra = {}
        if len(films) == 1:
            f = films[0]
            extra.update(director=f["director"], year=f["year"], duration=f["duration"],
                         synopsis=f["synopsis"])
        else:
            if sh["directors"]:
                extra["director"] = ", ".join(filter(None, sh["directors"]))
            durs = [f["duration"] for f in films if f["duration"]]
            if durs and len(durs) == len(films):
                extra["duration"] = sum(durs)
        out.append(show(
            CINEMA.id,
            title,
            sh["start"],
            url=det.get("booking") or sh["booking"] or sh["href"],
            version=version,
            poster=sh["poster"],
            tags=list(dict.fromkeys(tags)),
            **extra,
        ))
    return out
