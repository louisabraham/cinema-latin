"""Fondation Jérôme Seydoux-Pathé — https://www.fondation-jeromeseydoux-pathe.com/

Source: the `/agenda` page lists one tile per upcoming event (tags such as
SÉANCES, CYCLES, CONFÉRENCES, first/last date, title like
`"Rosita" ("Rosita, chanteuse des rues"), Ernst Lubitsch, 1923 (1h35)`).
Each film event page `/event/<id>` lists all its séances (day, month, hour,
Digitick booking link), the linked cycle and the film sheet.
"""

import re
import time
from datetime import timedelta

from bs4 import BeautifulSoup

from ..common import Cinema, clean, combine, get, now, parse_duration, parse_fr_date, parse_time, show

CINEMA = Cinema(
    id='fondation-pathe',
    name='Fondation Jérôme Seydoux-Pathé',
    address='73 avenue des Gobelins, 75013 Paris',
    lat=48.833378,
    lon=2.354526,
    url='https://www.fondation-jeromeseydoux-pathe.com/',
    allocine='W7513',
    group='Ailleurs',
    tags=['Muet', 'Répertoire'],
)

BASE = "https://www.fondation-jeromeseydoux-pathe.com"
DAYS = 14
FILM_TAGS = {"SÉANCES", "CINÉ-SPECTACLES"}
QUOTE_RE = re.compile(r'"([^"]+)"|«\s*([^»]+?)\s*»|“([^”]+)”')
DUR_RE = re.compile(r"[,(]\s*(\d+\s*h\s*\d*|\d+\s*min|\d+\s*')\s*\)?\s*$")


def _soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(get(url).content, "lxml")


def _txt(el) -> str | None:
    return clean(el.get_text(" ")) if el is not None else None


def parse_title(raw: str) -> dict:
    """'"Rosita" ("Rosita, chanteuse des rues"), Ernst Lubitsch, 1923 (1h35)' -> fields."""
    out: dict = {"title": raw}
    t = raw.strip()
    m = DUR_RE.search(t)
    if m:
        d = m.group(1).replace("'", " min")
        out["duration"] = parse_duration(d)
        t = t[: m.start()].strip(" ,")
    q = QUOTE_RE.search(t) or re.search(r"\[([^\]]+)\]", t)
    if not q:
        out["title"] = t
        return out
    prefix = t[: q.start()].strip()
    first = next(g for g in q.groups() if g)
    rest = t[q.end():]
    # French title in parentheses right after the original one
    fr = re.match(r'\s*\(\s*(?:"([^"]+)"|«\s*([^»]+?)\s*»|\[([^\]]+)\])\s*\)', rest)
    french = None
    if fr:
        french = next(g for g in fr.groups() if g)
        rest = rest[fr.end():]
    if prefix.lower().rstrip(" :") == "programme":
        out["title"] = f"Programme « {first} »"
    elif french:
        out["title"], out["original_title"] = french, first
    else:
        out["title"] = first
        if prefix.endswith(":"):
            out["label"] = prefix.rstrip(" :")
        elif re.search(r"[\u3000-\u9fff]", prefix):
            out["original_title"] = prefix
    # ', Director[, Director], 1923'
    parts = [p.strip() for p in rest.split(",") if p.strip()]
    years = [p for p in parts if re.fullmatch(r"(18|19|20)\d\d(-\d{4})?", p)]
    if years:
        out["year"] = int(years[0][:4])
        dirs = parts[: parts.index(years[0])]
        if dirs:
            out["director"] = ", ".join(dirs)
    return out


def _agenda_events(start, end) -> list[dict]:
    s = _soup(f"{BASE}/agenda")
    events = []
    for tile in s.select(".sw-agenda-event-wrapper"):
        a = tile.select_one("a.programmation-tile")
        if a is None:
            continue
        tags = {clean(x) for x in (_txt(tile.select_one(".tags .text")) or "").split(";")}
        if not tags & FILM_TAGS:
            continue
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", _txt(tile.select_one(".dates")) or "")
        if dates and parse_fr_date(dates[0]) >= end:
            continue
        img = tile.select_one(".programmation-tile-image")
        poster = None
        if img:
            m = re.search(r"url\(([^)]+)\)", img.get("style", ""))
            if m:
                poster = BASE + m.group(1).strip("'\"") if m.group(1).startswith("/") else m.group(1)
        events.append({
            "href": a["href"] if a["href"].startswith("http") else BASE + a["href"],
            "title": _txt(tile.select_one(".title")),
            "tags": tags,
            "poster": poster,
        })
    return events


MUSIC_RE = re.compile(r"accompagnée? (au piano|par un pianiste|en musique|musicalement)|ciné-concert|pianiste|au piano|musique live", re.I)
PRESENT_RE = re.compile(r"présentée? par", re.I)
MEET_RE = re.compile(r"rencontre avec|en présence d|suivie? d.une? (rencontre|discussion|débat)|dialogue avec", re.I)


def _dated(desc_ps: list[str], pattern: re.Pattern) -> tuple[bool, set]:
    """Paragraphs matching `pattern`, e.g. 'La séance du 24 septembre est accompagnée
    au piano'. Returns (applies to all séances, set of specific dates)."""
    everywhere, dates = False, set()
    for p in desc_ps:
        if not pattern.search(p):
            continue
        ds = re.findall(r"(\d{1,2}(?:er)?\s+[a-zéû]+)", p, re.I)
        parsed = {parse_fr_date(d) for d in ds} - {None}
        if parsed:
            dates |= parsed
        else:
            everywhere = True
    return everywhere, dates


def _event(url: str) -> dict:
    s = _soup(url)
    ev = s.select_one("[data-controller=event]")
    info: dict = {"h1": _txt(ev.select_one("h1.event-title")) if ev else None}
    seances = []
    for card in s.select(".seances-cards .seance"):
        day = _txt(card.select_one(".day"))
        month = _txt(card.select_one(".month"))
        hour = _txt(card.select_one(".hour"))
        d = parse_fr_date(f"{day} {month}") if day and month else None
        hm = parse_time(hour or "")
        if d and hm:
            seances.append((combine(d, hm), card.get("href")))
    info["seances"] = seances
    ps = [_txt(p) or "" for p in (ev.select(".hit-desc .ql-editor p") if ev else [])]
    ps = [p for p in ps if p]
    info["paragraphs"] = ps
    syn = [p for p in ps if len(p) > 120 and not p.startswith(("Avec", "Format", "Provenance"))]
    info["synopsis"] = syn[0] if syn else None
    fmt = next((p for p in ps if p.lower().startswith("format de la copie")), "")
    info["format"] = fmt
    cycle = None
    for tile in s.select(".event-linked .programmation-tile"):
        if "CYCLES" in (_txt(tile.select_one(".tags .text")) or ""):
            cycle = _txt(tile.select_one(".title"))
            break
    info["cycle"] = cycle
    buy = s.select_one('.infos .link a[href*="digitick"]')
    info["booking"] = buy["href"] if buy else None
    return info


def scrape() -> list[dict]:
    start = now().date()
    end = start + timedelta(days=DAYS)
    cutoff = now() - timedelta(minutes=15)
    out = []
    seen = set()
    for e in _agenda_events(start, end):
        time.sleep(1)
        try:
            info = _event(e["href"])
        except Exception:
            continue
        f = parse_title(info["h1"] or e["title"])
        tags = []
        if info["cycle"]:
            tags.append(info["cycle"])
        if f.get("label"):
            tags.append(f["label"])
        if "CINÉ-SPECTACLES" in e["tags"]:
            tags.append("Ciné-spectacle")
        if "JEUNE-PUBLIC" in e["tags"]:
            tags.append("Jeune public")
        for m in re.findall(r"\b(35|16|9,5|70)\s*mm\b", info["format"] + " " + (info["h1"] or "")):
            tags.append(f"{m}mm")
        flags = {
            "Ciné-concert": _dated(info["paragraphs"], MUSIC_RE),
            "Présentation": _dated(info["paragraphs"], PRESENT_RE),
            "Rencontre": _dated(info["paragraphs"], MEET_RE),
        }
        text = " ".join(info["paragraphs"])
        version = "VO" if re.search(r"\bVOSTF\b|sous-titr", text, re.I) else None
        for dt, href in info["seances"]:
            if dt < cutoff or dt.date() >= end:
                continue
            key = (f["title"], dt)
            if key in seen:
                continue
            seen.add(key)
            stags = list(tags)
            for tag, (always, dates) in flags.items():
                if always or dt.date() in dates:
                    stags.append(tag)
            out.append(show(
                CINEMA.id,
                f["title"],
                dt,
                url=href or info["booking"] or e["href"],
                original_title=f.get("original_title"),
                director=f.get("director"),
                year=f.get("year"),
                duration=f.get("duration"),
                version=version,
                synopsis=info["synopsis"],
                poster=e["poster"],
                tags=list(dict.fromkeys(stags)),
            ))
    out.sort(key=lambda s: s["start"])
    return out
