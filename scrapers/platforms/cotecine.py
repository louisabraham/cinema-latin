"""Cotecine / Ciné Group booking sites: https://<account>.cotecine.fr/ (or a
custom host such as https://achat.espacesaintmichel.com). Every function takes
`site`: either the site name ("lucernaire-vad") or the base URL.

  GET /reserver/                 HTML form; <select name="modresa_film"> lists every
                                 bookable film (option value = cotecine film id)
  GET /reserver/ajax/?modresa_film=<id>
                                 JSON {"2026-09-24": "jeudi 24 septembre", ...}
  GET /reserver/ajax/?modresa_film=<id>&modresa_jour=<YYYY-MM-DD>
                                 JSON {"<unix ts>/<VO|VF>/<seance id>": "16h10 - VO", ...}
  GET /programme/                HTML list of current films (poster, duration)

Booking link of a film: <base>/reserver/F<id>/
Pages are ISO-8859-1. One request per (film, day), so a full scrape costs
about 2 + films + film-days requests.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime

from bs4 import BeautifulSoup

from ..common import TZ, clean, get, parse_duration, window

PAUSE = 0.2


def _base(site: str) -> str:
    return site.rstrip("/") if site.startswith("http") else f"https://{site}.cotecine.fr"


def _json(url: str, params: dict) -> dict:
    r = get(url, params=params)
    try:
        txt = r.content.decode("utf-8")
    except UnicodeDecodeError:
        txt = r.content.decode("latin-1")
    try:
        d = json.loads(txt)
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def films(site: str) -> dict[str, str]:
    """cotecine film id -> title, from the booking form."""
    s = BeautifulSoup(get(_base(site) + "/reserver/").content, "lxml", from_encoding="latin-1")
    sel = s.find("select", attrs={"name": "modresa_film"})
    out = {}
    for o in sel.find_all("option") if sel else []:
        if o.get("value"):
            out[o["value"]] = clean(o.get_text())
    return out


def programme(site: str) -> dict[str, dict]:
    """cotecine film id -> {"duration", "poster"} from /programme/ (current films only)."""
    s = BeautifulSoup(get(_base(site) + "/programme/").content, "lxml", from_encoding="latin-1")
    out = {}
    for blk in s.select(".fichefilm-mini-block"):
        a = blk.select_one("a[href*='/reserver/F']")
        if not a:
            continue
        fid = re.search(r"/reserver/F(\d+)", a["href"]).group(1)
        dur = blk.select_one(".duration")
        img = blk.select_one("img.vignette")
        poster = img.get("src") if img else None
        if poster:
            poster = re.sub(r"/c_\d+_\d+_[^/]+/", "/", poster)  # full size Allociné image
        out[fid] = {"duration": parse_duration(dur.get_text()) if dur else None, "poster": poster}
    return out


def seances(site: str, film_id: str, days: list[date] | None = None) -> list[tuple[datetime, str | None]]:
    """[(start, "VO"/"VF"/None)] of one film, restricted to `days` (default: window())."""
    days = set(days or window())
    url = _base(site) + "/reserver/ajax/"
    out = []
    for d in sorted(_json(url, {"modresa_film": film_id})):
        try:
            day = date.fromisoformat(d)
        except ValueError:
            continue
        if day not in days:
            continue
        time.sleep(PAUSE)
        for key in _json(url, {"modresa_film": film_id, "modresa_jour": d}):
            parts = key.split("/")
            if not parts[0].isdigit():
                continue
            start = datetime.fromtimestamp(int(parts[0]), TZ)
            version = parts[1] if len(parts) > 1 and parts[1] in ("VO", "VF") else None
            out.append((start, version))
    return out


def booking_url(site: str, film_id: str) -> str:
    return f"{_base(site)}/reserver/F{film_id}/"
