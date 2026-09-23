"""Espace Saint-Michel — https://espacesaintmichel.com/

Showtimes: the Cotecine booking site https://achat.espacesaintmichel.com/reserver/
(exact datetimes and VO/VF, see platforms/cotecine.py). Its titles are the
French release titles ("Boule de feu").

Details: the WordPress film pages /films-a-l-affiche/<slug>/ linked from the
home page (original title, year, director, duration, synopsis, poster, and
hand-written schedules such as "Jeudi, Lundi : 18h30" or special sessions
"Mardi 29 septembre à 20h ... En présence de ..."). A WordPress page is matched
to a Cotecine film by title, else by the time slots they share.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from ..common import (
    TZ, Cinema, clean, get, norm_title, parse_duration, parse_fr_date, show, soup, strip_accents,
)
from ..platforms import cotecine

CINEMA = Cinema(
    id='espace-saint-michel',
    name='Espace Saint-Michel',
    address='7 place Saint-Michel, 75005 Paris',
    lat=48.853066,
    lon=2.344186,
    url='https://espacesaintmichel.com/',
    allocine='C0117',
    group='Quartier Latin',
    tags=['Art et essai'],
)

SITE = "https://achat.espacesaintmichel.com"
WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
TIME_RE = re.compile(r"(\d{1,2})\s*h\s*(\d{2})?")


def _times(text: str) -> list[tuple[int, int]]:
    return [(int(h), int(m or 0)) for h, m in TIME_RE.findall(text) if int(h) < 24]


def _week_slots(start: date, line: str) -> list[datetime]:
    """'Jeudi, Lundi : 18h30' or 'Tous les jours (sauf vendredi) : 14h30, 16h20' in the week from `start`."""
    if ":" not in line:
        return []
    days_txt, times_txt = line.split(":", 1)
    d = strip_accents(days_txt.lower())
    if "tous les jours" in d:
        sauf = d.split("sauf", 1)[1] if "sauf" in d else ""
        wds = [i for i, w in enumerate(WEEKDAYS) if w not in sauf]
    else:
        wds = [i for i, w in enumerate(WEEKDAYS) if re.search(rf"\b{w}\b", d)]
    out = []
    for i in range(7):
        day = start + timedelta(days=i)
        if day.weekday() in wds:
            out += [datetime(day.year, day.month, day.day, h, m, tzinfo=TZ) for h, m in _times(times_txt)]
    return out


def _wp_film(url: str) -> dict:
    s = BeautifulSoup(get(url).content, "lxml")
    info: dict = {"url": url, "slots": {}, "tags": set()}
    h2 = s.select_one("h2.edgtf-st-title")
    info["original_title"] = clean(h2.get_text()) if h2 else None
    p = s.select_one(".edgtf-eh-item-content .wpb_text_column p")
    info["synopsis"] = clean(p.get_text(" ")) if p else None
    for box in s.select(".edgtf-iwt-content"):
        k = strip_accents(clean(box.select_one(".edgtf-iwt-title").get_text()) or "").lower()
        v = clean(box.select_one(".edgtf-iwt-text").get_text(" ")) if box.select_one(".edgtf-iwt-text") else None
        if not v:
            continue
        if k == "annee" and v[:4].isdigit():
            info["year"] = int(v[:4])
        elif k.startswith("realisation"):
            # "Howard HAWKS" -> "Howard Hawks"
            info["director"] = " ".join(w.title() if w.isupper() and len(w) > 2 else w for w in v.split())
        elif k.startswith("fiche technique"):
            info["duration"] = parse_duration(v)
            if re.search(r"\b35\s*mm\b", v, re.I):
                info["tags"].add("35mm")
    img = s.select_one(".edgtf-video-button-image img") or s.find("meta", property="og:image")
    if img:
        info["poster"] = img.get("src") or img.get("content")
    # schedules: {datetime: set(tags)}
    for panel in s.select(".vc_tta-panel"):
        title = clean(panel.select_one(".vc_tta-title-text").get_text()) or ""
        lines = [clean(x.get_text(" ")) for x in panel.select(".vc_tta-panel-body p")]
        lines = [x for x in lines if x]
        m = re.match(r"Horaires du (\d{1,2})(?:er)?\s*(\w*)\s*au\s*(\d{1,2})\s*(\w+)\s*(\d{4})?", title, re.I)
        if m:
            end = parse_fr_date(f"{m.group(3)} {m.group(4)} {m.group(5) or ''}")
            if not end:
                continue
            start = end - timedelta(days=6)
            for line in lines:
                for dt in _week_slots(start, line):
                    info["slots"].setdefault(dt, set())
            continue
        # special sessions: "Mardi 29 septembre à 20h Animée par ... En présence de ..."
        for line in lines:
            dm = re.search(r"(\d{1,2})(?:er)?\s+([a-zéû]+)\s*(\d{4})?[^0-9]{0,150}?à\s*(\d{1,2})\s*h\s*(\d{2})?", line, re.I)
            if not dm:
                continue
            d = parse_fr_date(f"{dm.group(1)} {dm.group(2)} {dm.group(3) or ''}")
            if not d:
                continue
            dt = datetime(d.year, d.month, d.day, int(dm.group(4)), int(dm.group(5) or 0), tzinfo=TZ)
            tags = info["slots"].setdefault(dt, set())
            low = (title + " " + line).lower()
            if "débat" in low:
                tags.add("Ciné-débat")
            elif "spéciale" in low:
                tags.add("Séance spéciale")
            if "en présence" in low:
                tags.add("Rencontre")
    return info


def _wp_films() -> list[dict]:
    """All film pages linked from the home page. The WordPress server takes
    ~3 s per page, so pages are fetched by 3 workers (below 1 request/s)."""
    home = soup(CINEMA.url)
    urls = sorted({a["href"] for a in home.select("a[href*='/films-a-l-affiche/']")})

    def one(u):
        try:
            return _wp_film(u)
        except Exception:
            return None

    with ThreadPoolExecutor(3) as ex:
        return [w for w in ex.map(one, urls) if w]


def _cotecine() -> tuple[dict, dict, dict]:
    films = cotecine.films(SITE)
    try:
        prog = cotecine.programme(SITE)
    except Exception:
        prog = {}
    seances = {}
    for fid in films:
        seances[fid] = cotecine.seances(SITE, fid)
        time.sleep(cotecine.PAUSE)
    return films, prog, seances


def _match(films: dict, prog: dict, seances: dict, wp: list[dict]) -> dict[str, dict]:
    """Cotecine film id -> WordPress page. Greedy on a score: same title (+2),
    Jaccard index of the time slots, same duration within 3 min (+0.5)."""
    pairs = []
    for fid, title in films.items():
        slots = {dt for dt, _ in seances[fid]}
        dur = (prog.get(fid) or {}).get("duration")
        for i, w in enumerate(wp):
            same_title = bool(w.get("original_title")) and norm_title(w["original_title"]) == norm_title(title)
            ws = set(w["slots"])
            common = len(slots & ws)
            if not same_title and not common:
                continue
            score = 2 * same_title + common / len(slots | ws)
            if dur and w.get("duration") and abs(dur - w["duration"]) <= 3:
                score += 0.5
            pairs.append((score, fid, i))
    match, used = {}, set()
    for score, fid, i in sorted(pairs, reverse=True):
        if fid in match or i in used:
            continue
        match[fid] = wp[i]
        used.add(i)
    return match


def scrape() -> list[dict]:
    with ThreadPoolExecutor(1) as ex:  # WordPress and Cotecine are on different hosts
        wp_future = ex.submit(_wp_films)
        films, prog, seances = _cotecine()
        try:
            wp = wp_future.result()
        except Exception:
            wp = []
    match = _match(films, prog, seances, wp)

    shows = []
    for fid, title in films.items():
        w = match.get(fid, {})
        p = prog.get(fid, {})
        orig = w.get("original_title")
        if orig and orig.isupper():
            orig = orig.title()
        for start, version in seances[fid]:
            tags = set(w.get("tags", set())) | w.get("slots", {}).get(start, set())
            shows.append(show(
                CINEMA.id, title, start,
                version=version,
                url=cotecine.booking_url(SITE, fid),
                original_title=orig if orig and norm_title(orig) != norm_title(title) else None,
                director=w.get("director"),
                year=w.get("year"),
                duration=p.get("duration") or w.get("duration"),
                tags=sorted(tags),
                synopsis=w.get("synopsis"),
                poster=w.get("poster") or p.get("poster"),
            ))
    shows.sort(key=lambda s: s["start"])
    return shows
