"""Ciné Office (cineoffice.fr) ticketing platform.

The cinema site embeds a React app that reads a public REST API with the token
found in `<meta name="api_token">` of the cinema home page:

    GET https://<account>.cineoffice.fr/vad/shows?api_token=...   -> list of shows
    GET https://<account>.cineoffice.fr/vad/media?api_token=...   -> list of films
    GET https://<account>.cineoffice.fr/vad/screens?api_token=... -> list of rooms

`showtime` has an explicit UTC offset. Media has director, year, duration (s),
storyline, poster, Allociné id.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import urlencode

from ..common import get, now, show

VERSION_BY_OPTION = {"VERSION_ORIGINAL": "VO", "VERSION_LOCAL": "VF", "VERSION_ORIGINAL_LOCAL": "VF"}
TAG_BY_OPTION = {"PICTURE_35MM": "35mm", "PICTURE_3D": "3D", "VERSION_MUET": "Muet", "PICTURE_4K": "4K"}


def api_token(site_url: str) -> str:
    html = get(site_url).text
    m = re.search(r'<meta name="api_token" content="([^"]+)"', html)
    if not m:
        raise RuntimeError(f"no cineoffice api_token on {site_url}")
    return m.group(1)


def _parse_dt(s: str) -> datetime:
    # "2026-09-25T20:30:00.000+0200"
    s = re.sub(r"\.\d+", "", s)
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s)
    return datetime.fromisoformat(s)


def _director(name: str | None) -> str | None:
    """'JARMUSCH Jim' -> 'Jim Jarmusch'; other forms unchanged."""
    if not name:
        return None
    m = re.match(r"^([A-ZÀ-Ý][A-ZÀ-Ý'\- ]+?)\s+([A-ZÀ-Ý][a-zà-ÿ].*)$", name.strip())
    return f"{m.group(2)} {m.group(1).title()}" if m else name


def scrape(cinema_id: str, account: str, token: str, film_url=None, days: int | None = None) -> list[dict]:
    """`film_url(media_id, show_id, title)` builds the page link for a show (optional)."""
    base = f"https://{account}.cineoffice.fr/vad"
    params = {"api_token": token}
    shows_raw = get(f"{base}/shows", params=params).json()
    media = {m["id"]: m for m in get(f"{base}/media", params=params).json()}
    try:
        options = {o["id"]: o["label"] for o in get(f"{base}/mediaoptions", params=params).json()}
    except Exception:
        options = {}
    try:
        screens = {s["id"]: s for s in get(f"{base}/screens", params=params).json()}
    except Exception:
        screens = {}

    start_min = now() - timedelta(minutes=30)
    end = now() + timedelta(days=days) if days else None
    out: list[dict] = []
    for s in shows_raw:
        if s.get("canceled") or s.get("deleted") or s.get("draft"):
            continue
        dt = _parse_dt(s["showtime"])
        if dt < start_min or (end and dt > end):
            continue
        m = media.get((s.get("mediaid") or {}).get("id")) or {}
        title = s.get("showeventtitle") or m.get("displaytitle") or m.get("title")
        if not title:
            continue
        labels = [options.get((o.get("mediaoptionsid") or {}).get("id"), "") for o in s.get("showsMediaoptionsCollection") or []]
        labels.append(options.get(s.get("languagemediaoptionsid"), ""))
        version = next((VERSION_BY_OPTION[x] for x in labels if x in VERSION_BY_OPTION), None)
        tags = []
        for x in labels:
            t = TAG_BY_OPTION.get(x)
            if t and t not in tags:
                tags.append(t)
        if s.get("threed") and "3D" not in tags:
            tags.append("3D")
        if s.get("premiere"):
            tags.append("Avant-première")
        if s.get("showevent") or s.get("event"):
            tags.append("Événement")
        if s.get("showcomment"):
            tags.append(s["showcomment"].strip())
        screen = screens.get((s.get("screenid") or {}).get("id")) or {}
        room = screen.get("screenlabel") or (f"Salle {screen['screennumber']}" if screen.get("screennumber") else None)
        year = m.get("filmyear")
        allocine = m.get("allocineid")
        url = film_url(m.get("id"), s.get("id"), title) if film_url else None
        out.append(show(
            cinema_id, title, dt,
            version=version,
            url=url,
            director=_director(m.get("director")),
            year=int(year) if year and str(year).isdigit() else None,
            duration=round(m["duration"] / 60) if m.get("duration") else None,
            room=room,
            tags=tags,
            allocine_id=int(allocine) if allocine and str(allocine).isdigit() else None,
            synopsis=s.get("showeventstoryline") or m.get("storyline"),
            poster=s.get("showeventposterpath") or m.get("posterpath") or m.get("smallposterpath"),
        ))
    out.sort(key=lambda x: (x["start"], x["title"]))
    return out


def query(**kw) -> str:
    return urlencode({k: v for k, v in kw.items() if v is not None})
