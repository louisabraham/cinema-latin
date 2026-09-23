"""Les 3 Luxembourg — https://www.lestroisluxembourg.com/

Cotecine / Webedia cinema site (pages in windows-1252).
  * /horaires/ lists every film with a 14-day grid (tabs "jour1".."jour14").
    Bookable times link to /reserver/F<film>/D<unix time>/<VO|VF>/<room>/;
    events are marked with the CSS class "fevt".
  * /evenements/ lists the events (ciné-clubs, séances spéciales); each event
    page links the showtimes it covers (same /reserver/F.../D.../ links).
"""

import re
import time
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from ..common import (
    DAYS_AHEAD, TZ, Cinema, clean, combine, get, now, parse_duration, parse_fr_date,
    parse_time, show, strip_accents, version_of,
)

CINEMA = Cinema(
    id='3-luxembourg',
    name='Les 3 Luxembourg',
    address='67 rue Monsieur le Prince, 75006 Paris',
    lat=48.848402,
    lon=2.340845,
    url='https://www.lestroisluxembourg.com/',
    allocine='C0095',
    group='Quartier Latin',
    tags=['Art et essai'],
)

BASE = "https://www.lestroisluxembourg.com"
RESA_RE = re.compile(r"/reserver/F(\w+)/D(\d+)/")
TAG_ALTS = {
    "tag-PATRIMOINEETREPERTOIRE": "Patrimoine et Répertoire",
    "tag-JEUNESPUBLIC": "Jeune public",
}


def _page(url: str) -> BeautifulSoup:
    return BeautifulSoup(get(url).content, "lxml", from_encoding="cp1252")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", strip_accents(s.lower())).strip()


def _first_day(page: BeautifulSoup) -> date:
    """Date of the "jour1" tab: the day number closest to today."""
    today = now().date()
    head = page.select_one(".lesjours .jour1")
    m = re.search(r"(\d{1,2})\s*$", head.get_text(" ", strip=True)) if head else None
    if not m:
        return today
    n = int(m.group(1))
    cands = [today + timedelta(days=k) for k in range(-3, 4)]
    return next((d for d in cands if d.day == n), today)


def _events() -> dict[tuple[str, int], list[str]]:
    """(film id, unix time) -> event tags, from the event pages in the window."""
    out = {}
    try:
        lst = _page(BASE + "/evenements/")
    except Exception:
        return out
    last = now().date() + timedelta(days=DAYS_AHEAD)
    for a in lst.select("a.bloc_fevt"):
        h3 = a.select_one("h3")
        start = parse_fr_date(h3.get_text(" ", strip=True)) if h3 else None
        if start and start > last:
            continue
        kind = clean(a.select_one(".fevt_type_txt").get_text()) if a.select_one(".fevt_type_txt") else None
        name = clean(a.h2.get_text()) if a.h2 else None
        time.sleep(0.5)
        try:
            ev = _page(a["href"])
        except Exception:
            continue
        text = strip_accents(ev.get_text(" ", strip=True).lower())
        rencontre = bool(re.search(r"en presence|rencontre|debat|echange avec", text))
        for film in ev.select(".fevt_film"):
            ftitle = film.select_one("h3")
            ftitle = _norm(ftitle.get_text()) if ftitle else ""
            tags = []
            if kind:
                low = kind.lower()
                tags.append("Ciné-club" if "club" in low else "Séance spéciale" if "cial" in low else kind)
            if name and _norm(name) not in ftitle and ftitle not in _norm(name):
                tags.append(name)
            if rencontre:
                tags.append("Rencontre")
            for r in film.select("a[href*='/reserver/F']"):
                m = RESA_RE.search(r["href"])
                if m:
                    out.setdefault((m[1], int(m[2])), [])
                    out[(m[1], int(m[2]))] += [t for t in tags if t not in out[(m[1], int(m[2]))]]
    return out


def scrape() -> list[dict]:
    page = _page(BASE + "/horaires/")
    day1 = _first_day(page)
    events = _events()
    cutoff = now() - timedelta(minutes=30)
    out = []
    seen = set()
    for f in page.select("div.hr_film"):
        a = f.select_one(".hr_film_infos h2 a")
        if not a:
            continue
        title = clean(a.get_text())
        film_url = a["href"]
        real = f.select_one(".hr_real strong")
        dur = f.select_one(".hr_dur strong")
        img = f.select_one("img.hr_aff")
        poster = img.get("src") if img else None
        if poster:
            poster = re.sub(r"/r_\d+_\d+/", "/", poster)
        for tab in f.select(".tab_seances"):
            m = re.search(r"\bjour(\d+)\b", " ".join(tab.get("class", [])))
            if not m:
                continue
            day = day1 + timedelta(days=int(m.group(1)) - 1)
            for row in tab.select(".frow"):
                vtag = row.select_one(".celtags img")
                version = None
                if vtag:
                    cls = " ".join(vtag.get("class", []))
                    version = "VO" if "VOST" in cls or "tag-VO" in cls else version_of(vtag.get("alt"))
                    if version is None and "tag-VF" in cls:
                        version = "VF"
                for s in row.select(".seance"):
                    hm = parse_time(s.select_one(".hor").get_text()) if s.select_one(".hor") else None
                    if not hm:
                        continue
                    start = combine(day, hm)
                    href = s.get("href")
                    rm = RESA_RE.search(href or "")
                    if rm:
                        start = datetime.fromtimestamp(int(rm[2]), TZ)
                    if start < cutoff or (title, start) in seen:
                        continue
                    seen.add((title, start))
                    tags = []
                    for img_tag in s.select(".infos_seance img"):
                        for c in img_tag.get("class", []):
                            if c in TAG_ALTS:
                                tags.append(TAG_ALTS[c])
                    if rm:
                        tags += events.get((rm[1], int(rm[2])), [])
                    if "fevt" in s.get("class", []) and not tags:
                        tags.append("Séance spéciale")
                    out.append(
                        show(
                            CINEMA.id,
                            title,
                            start,
                            version=version,
                            url=href or film_url,
                            director=clean(real.get_text()) if real else None,
                            duration=parse_duration(dur.get_text()) if dur else None,
                            poster=poster,
                            tags=list(dict.fromkeys(tags)),
                        )
                    )
    out.sort(key=lambda s: s["start"])
    return out
