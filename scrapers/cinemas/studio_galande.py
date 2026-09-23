"""Studio Galande — http://www.studiogalande.fr/

Erakys / moncinepack site ("faisan" theme). The "horaires" page shows the current
week as a grid (one block per film, seven day columns); other weeks come from
GET /FR/ajax/cine/faisan.horaires.journalier?idMS=&dprog=<week start>, which
returns the same HTML fragment. Each time links to ticketingcine.com.
"""

import re
import time
from datetime import date, timedelta

from ..common import (
    DAYS_AHEAD, Cinema, clean, combine, now, parse_duration, parse_time, show, soup, version_of,
)

CINEMA = Cinema(
    id='studio-galande',
    name='Studio Galande',
    address='42 rue Galande, 75005 Paris',
    lat=48.851634,
    lon=2.347107,
    url='http://www.studiogalande.fr/',
    allocine='C0016',
    group='Quartier Latin',
    tags=['Art et essai'],
)

BASE = "http://www.studiogalande.fr"
HORAIRES = BASE + "/FR/43/horaires-cinema-studio-galande-beruchetparis.html"
AJAX = BASE + "/FR/ajax/cine/faisan.horaires.journalier"


def _parse_week(page, start: date) -> list[dict]:
    out = []
    for block in page.select("div.esp-fiche-horaire"):
        h3 = block.select_one("h3")
        grid = block.select_one(".div-horaire")
        if not h3 or not grid:
            continue
        title = clean(h3.get_text())
        link = block.select_one("a[href*='fiche-film-cinema']")
        img = block.select_one("img.vignette-aff")
        genre = block.select_one(".genre-film")
        rea = block.select_one(".rea-film")
        director = None
        if rea:
            m = re.search(r"Réalisation\s*:\s*(.+?)(?:Acteurs\s*:|$)", rea.get_text(" ", strip=True))
            director = clean(m.group(1)) if m else None
        syn = block.select_one(".zone-extra-detail-plus")
        synopsis = None
        if syn:
            syn = syn.__copy__()
            for x in syn.select(".rea-film"):
                x.decompose()
            synopsis = clean(syn.get_text(" "))
        film = {
            "url": link["href"] if link else None,
            "poster": img.get("data-original") if img else None,
            "duration": parse_duration(genre.get_text()) if genre else None,
            "director": director,
            "synopsis": synopsis,
        }
        # day columns: check the day numbers against the week start
        days = []
        for i, d in enumerate(grid.select(".jour-seance")):
            day = start + timedelta(days=i)
            num = d.select_one(".jour-mob")
            if num and num.get_text(strip=True).isdigit() and int(num.get_text(strip=True)) != day.day:
                day = None  # unexpected layout, skip this column
            days.append(day)
        version = None
        for el in grid.find_all(class_=re.compile(r"^(version-seance|ligne_ach)")):
            classes = " ".join(el.get("class", []))
            if "version-seance" in classes:
                b = el.select_one(".b-seance")
                version = version_of(b.get_text(" ", strip=True).replace("VOST", "VOST ")) if b else None
                continue
            for i, cell in enumerate(el.select(".heure-seance")):
                if i >= len(days) or days[i] is None:
                    continue
                for a in cell.select("a"):
                    hm = parse_time(a.get_text())
                    if hm:
                        out.append(dict(film, title=title, start=combine(days[i], hm),
                                        version=version, booking=a.get("href")))
                if not cell.select("a"):
                    hm = parse_time(cell.get_text())
                    if hm:
                        out.append(dict(film, title=title, start=combine(days[i], hm),
                                        version=version, booking=None))
    return out


def scrape() -> list[dict]:
    first = soup(HORAIRES)
    weeks = [
        date.fromisoformat(o["value"])
        for o in first.select("#selecteurSemaine option")
        if re.match(r"\d{4}-\d{2}-\d{2}$", o.get("value", ""))
    ]
    if not weeks:
        return []
    today = now().date()
    rows = _parse_week(first, weeks[0])
    for w in weeks[1:]:
        if w > today + timedelta(days=DAYS_AHEAD):
            break
        time.sleep(0.5)
        rows += _parse_week(soup(AJAX, params={"idMS": "", "dprog": w.isoformat()}), w)

    cutoff = now() - timedelta(minutes=30)
    seen = set()
    out = []
    for r in rows:
        key = (r["title"], r["start"])
        if r["start"] < cutoff or key in seen:
            continue
        seen.add(key)
        out.append(
            show(
                CINEMA.id,
                r["title"],
                r["start"],
                version=r["version"],
                url=r["booking"] or r["url"],
                director=r["director"],
                duration=r["duration"],
                synopsis=r["synopsis"],
                poster=r["poster"],
            )
        )
    out.sort(key=lambda s: s["start"])
    return out
