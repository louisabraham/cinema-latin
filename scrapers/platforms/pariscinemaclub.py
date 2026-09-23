"""Paris Cinéma Club (Christine Cinéma Club, Écoles Cinéma Club).

The WordPress site https://pariscinemaclub.com/ has no schedule: it links each
film to the Cotecine ticketing site (<sub>.cotecine.fr). The Cotecine public
pages (horaires, film pages) are disabled, so the schedule comes from the
booking form and its AJAX endpoint:

    GET /reserver/                                  -> <select> with all films on sale
    GET /reserver/ajax/?modresa_film=<id>           -> {"2026-09-24": "jeudi 24 septembre", ...}
    GET /reserver/ajax/?modresa_film=<id>&modresa_jour=<date>
                                                    -> {"<unix ts>/VO/<n>": "18h25 - VO", ...}

Film metadata: /programme/ on Cotecine (duration, Allociné poster) and the
WordPress REST API custom post type `film` (director, synopsis).
Limitation: films without online sale do not appear in the booking form.
"""

from __future__ import annotations

import html
import re
import time
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from ..common import TZ, clean, get, norm_title, now, parse_duration, show, version_of

WP_API = "https://pariscinemaclub.com/wp-json/wp/v2/film"
AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest"}
DELAY = 0.6  # seconds between AJAX calls (about 1 request/second)


def _base(sub: str) -> str:
    return f"https://{sub}.cotecine.fr"


def _programme(sub: str) -> dict[str, dict]:
    """Cotecine /programme/: film id (from the 'Achat' link) -> metadata."""
    out: dict[str, dict] = {}
    try:
        s = BeautifulSoup(get(_base(sub) + "/programme/").content, "lxml")
    except Exception:
        return out
    for ev in s.select("div.vevent"):
        a = ev.select_one("a.resa-link3[href]")
        title = ev.select_one(".summary")
        info: dict = {"title": clean(title.get_text()) if title else None}
        dur = ev.select_one(".duration")
        if dur:
            info["duration"] = parse_duration(dur.get_text())
        link = ev.select_one("a.vignette[href]")
        y = re.search(r"-((?:19|20)\d\d)/$", link["href"]) if link else None
        if y:
            info["year"] = int(y.group(1))  # French release year from the film slug
        img = ev.select_one("img.vignette[src]")
        if img:
            # Allociné thumbnails: drop the resize prefix to get the full poster
            info["poster"] = re.sub(r"/c_\d+_\d+_\d+_\d+/", "/", img["src"])
        m = re.search(r"/reserver/F(\d+)/", a["href"]) if a else None
        key = m.group(1) if m else norm_title(info["title"] or "")
        out[key] = info
    return out


def _wp_films() -> list[dict]:
    films: list[dict] = []
    for page in (1, 2, 3):
        try:
            r = get(WP_API, params={"per_page": 100, "page": page, "_fields": "id,modified,link,title,content,cinema"})
        except Exception:
            break
        films += r.json()
        if page >= int(r.headers.get("X-WP-TotalPages", 1)):
            break
    return films


def _wp_info(post: dict) -> dict:
    s = BeautifulSoup(post["content"]["rendered"], "lxml")
    info: dict = {"wp_title": clean(html.unescape(post["title"]["rendered"])), "modified": post["modified"]}
    paras = [clean(p.get_text(" ", strip=True)) for p in s.find_all("p")]
    paras = [p for p in paras if p]
    if paras and len(paras[0]) > 60:
        info["synopsis"] = paras[0]
    for p in s.find_all("p"):
        txt = p.get_text("\n", strip=True)
        m = re.search(r"R[ée]alisat(?:eur|rice)s?\s*:\s*\n?(.+)", txt, re.I)
        if m:
            info["director"] = clean(m.group(1).split("\n")[0].strip(": "))
            break
    return info


def _wp_index(films: list[dict], wp_cinema: int) -> dict[str, dict]:
    """normalized title -> info, preferring posts of this cinema, then the most recent."""
    idx: dict[str, tuple] = {}
    for p in films:
        title = html.unescape(p["title"]["rendered"])
        base = re.split(r"\s+[–-]\s+|\s*-\s*35\s*mm", title, maxsplit=1)[0]
        key = norm_title(base)
        rank = (wp_cinema in (p.get("cinema") or []), p["modified"])
        if key not in idx or rank > idx[key][0]:
            idx[key] = (rank, p)
    return {k: _wp_info(p) for k, (_, p) in idx.items()}


def _ajax(url: str, **params) -> dict:
    time.sleep(DELAY)
    try:
        data = get(url, params=params, headers=AJAX_HEADERS).json()
    except ValueError:  # the endpoint answers "oups" on bad input
        return {}
    return data if isinstance(data, dict) else {}


def scrape(cinema_id: str, sub: str, wp_cinema: int, days: int = 14) -> list[dict]:
    base = _base(sub)
    s = BeautifulSoup(get(base + "/reserver/").content, "lxml")
    films = [
        (o["value"], clean(o.get_text()))
        for o in s.select("select[name=modresa_film] option")
        if o.get("value")
    ]
    prog = _programme(sub)
    try:
        wp = _wp_index(_wp_films(), wp_cinema)
    except Exception:
        wp = {}

    start = now()
    last_day = (start + timedelta(days=days)).date().isoformat()
    ajax = base + "/reserver/ajax/"
    shows: list[dict] = []
    for fid, title in films:
        day_map = _ajax(ajax, modresa_film=fid)
        meta = prog.get(fid) or prog.get(norm_title(title)) or {}
        w = wp.get(norm_title(title), {})
        tags = []
        recent_wp = w.get("modified", "") >= (start - timedelta(days=90)).strftime("%Y-%m-%d")
        if re.search(r"35\s*mm", title, re.I) or (recent_wp and re.search(r"35\s*mm", w.get("wp_title", ""), re.I)):
            tags.append("35mm")
        for day in sorted(day_map):
            if day > last_day:
                continue
            seances = _ajax(ajax, modresa_film=fid, modresa_jour=day)
            for key, label in seances.items():
                parts = key.split("/")
                try:
                    dt = datetime.fromtimestamp(int(parts[0]), TZ)
                except ValueError:
                    continue
                if dt < start - timedelta(minutes=30):
                    continue
                version = version_of(parts[1] if len(parts) > 1 else "") or version_of(label)
                extra = re.sub(r"^\s*\d{1,2}h\d{2}\s*(-\s*(VOST?F?R?|VO|VF)\b)?\s*-?\s*", "", label or "").strip()
                st_tags = tags + ([extra] if extra else [])
                shows.append(show(
                    cinema_id, title, dt,
                    version=version,
                    url=f"{base}/reserver/F{fid}/",
                    year=meta.get("year"),
                    duration=meta.get("duration"),
                    poster=meta.get("poster"),
                    director=w.get("director"),
                    synopsis=w.get("synopsis"),
                    tags=st_tags,
                ))
    shows.sort(key=lambda x: x["start"])
    return shows
