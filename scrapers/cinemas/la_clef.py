"""La Clef — https://laclefrevival.org/

The home page ("Prochainement à La Clef") lists the sessions of the current and
next week as cards: "23/09/2026 @ 20:00", title, "de <director>", excerpt.
Each session is a WordPress "project" post; its page adds the cycles (tags),
a "1926 / Etats-Unis / 1h28 / muet" line and the full text. No booking: entry
is free price at the door. Non-film events (workshops, book launches) are
dropped when the page has no film information line.
"""

import re
import time
from datetime import datetime

from bs4 import BeautifulSoup

from ..common import TZ, Cinema, clean, get, now, parse_duration, show, soup, version_of

CINEMA = Cinema(
    id='la-clef',
    name='La Clef',
    address='34 rue Daubenton, 75005 Paris',
    lat=48.841161,
    lon=2.352431,
    url='https://laclefrevival.org/',
    allocine='C0170',
    group='Quartier Latin',
    tags=['Associatif'],
)

DT_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*@\s*(\d{1,2}):(\d{2})")
NOT_FILM_RE = re.compile(r"\b(atelier|lancement|conférence|concert|débat seul|fête|soirée dansante)\b", re.I)


def _dt(text: str) -> datetime | None:
    m = DT_RE.search(text or "")
    if not m:
        return None
    d, mo, y, h, mi = map(int, m.groups())
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


def _cards() -> list[dict]:
    s = soup(CINEMA.url)
    out = []
    for a in s.select("article.entry-card.project"):
        t, h2 = a.select_one("time"), a.select_one("h2.entry-title a")
        start = _dt(t.get_text()) if t else None
        if not start or not h2:
            continue
        img = a.select_one("img[data-src]") or a.select_one("noscript img") or a.select_one("img")
        poster = img.get("data-src") or img.get("src") if img else None
        out.append({
            "start": start,
            "title": clean(h2.get_text()),
            "url": h2["href"],
            "poster": poster if poster and not poster.startswith("data:") else None,
        })
    return out


def _page(url: str) -> dict:
    s = BeautifulSoup(get(url).content, "lxml")
    body = s.select_one("article .entry-content") or s
    info: dict = {"starts": [_dt(h.get_text()) for h in body.find_all("h5") if _dt(h.get_text())]}
    tags = []
    h2 = body.find("h2")
    if h2:
        d = clean(h2.get_text()) or ""
        if re.search(r"\ben (leur |sa |la )?présence\b|rencontre", d, re.I):
            tags.append("Rencontre")
        d = re.sub(r"\s*\(.*?\)\s*", " ", d)
        if re.match(r"^d[e']\s*", d):  # "de Douglas Fairbanks", not "En présence de..."
            info["director"] = clean(re.sub(r"^d[e']\s*", "", d)) or None
    film_line = None
    for h6 in body.find_all("h6"):
        txt = clean(h6.get_text(" ")) or ""
        if txt.startswith("Cycles"):
            for a in h6.find_all("a"):
                name = clean(a.get_text())
                if name and not name.isdigit():
                    tags.append(name)
        elif "/" in txt:
            film_line = txt
    info["film_line"] = film_line
    if film_line:
        parts = [clean(p) for p in film_line.split("/")]
        years = [int(p) for p in parts if p and re.fullmatch(r"\d{4}", p)]
        info["year"] = years[0] if years else None
        info["duration"] = next((parse_duration(p) for p in parts if p and parse_duration(p)), None)
        for p in parts:
            if p and re.search(r"\b(16|35|70)\s*mm\b", p, re.I):
                tags.append(re.sub(r"\s+", "", p.lower()))
    paras = []
    for p in body.find_all("p", recursive=True):
        t = clean(p.get_text(" "))
        if t and t not in paras and not t.startswith("Informations pratiques"):
            paras.append(t)
        if len(" ".join(paras)) > 800:
            break
    info["synopsis"] = " ".join(paras)[:1200] or None
    info["version"] = version_of(film_line) or version_of(info["synopsis"])
    if re.search(r"\ben (leur |sa |la )?présence\b|\bsuivie? d.une? (rencontre|discussion|débat)", info["synopsis"] or "", re.I):
        tags.append("Rencontre")
    if re.search(r"\b16\s*mm\b", s.title.get_text() if s.title else "", re.I):
        tags.append("16mm")
    info["tags"] = list(dict.fromkeys(tags))
    return info


def scrape() -> list[dict]:
    cutoff = now().replace(hour=0, minute=0, second=0, microsecond=0)
    cards = _cards()
    pages: dict[str, dict] = {}
    seen, shows = set(), []
    for c in cards:
        if c["url"] not in pages:
            try:
                pages[c["url"]] = _page(c["url"])
            except Exception:
                pages[c["url"]] = {}
            time.sleep(0.3)
        p = pages[c["url"]]
        if not p.get("film_line") and NOT_FILM_RE.search(c["title"]):
            continue  # workshop, book launch...
        starts = {c["start"], *[d for d in p.get("starts", []) if d >= cutoff]}
        for start in sorted(starts):
            if start < cutoff or (c["title"], start) in seen:
                continue
            seen.add((c["title"], start))
            shows.append(show(
                CINEMA.id, c["title"], start,
                url=c["url"],
                version=p.get("version"),
                director=p.get("director"),
                year=p.get("year"),
                duration=p.get("duration"),
                tags=p.get("tags"),
                synopsis=p.get("synopsis"),
                poster=c["poster"],
            ))
    shows.sort(key=lambda s: s["start"])
    return shows
