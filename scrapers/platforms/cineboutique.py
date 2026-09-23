"""cine.boutique / cineoffice ticketing (Cinéo / Monnaie Services).

The booking site https://<account>.cine.boutique/ is a React app. Its HTML has a
<meta name="api_token"> that opens a public JSON API at
https://<account>.cineoffice.fr/vad/ :

  GET /shows?api_token=...   all future showtimes (id, showtime, mediaid, screenid,
                             showsMediaoptionsCollection, premiere, showevent...)
  GET /media?api_token=...   all films (title, director, filmyear, duration in s,
                             storyline, posterpath, allocineid, media options)
  GET /screens?api_token=... rooms (id -> screennumber, screenlabel)

Booking link of a showtime: https://<account>.cine.boutique/media/<mediaid>?showId=<id>
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..common import clean, get, now, show, to_paris

# option labels (mediaoptions) -> our fields
VERSION_LABELS = {"VERSION_ORIGINAL": "VO", "VERSION_ORIGINAL_LOCAL": "VF", "VERSION_LOCAL": "VF"}
FORMAT_LABELS = {"PICTURE_35MM": "35mm", "PICTURE_70MM": "70mm", "PICTURE_4K": "4K", "PICTURE_3D": "3D"}


@dataclass
class Data:
    account: str
    shows: list[dict]
    media: dict[int, dict]
    options: dict[int, dict]  # option id -> {"label", "ticketlabel", ...}
    rooms: dict[int, str]  # screen id -> "Salle 1"

    def booking_url(self, s: dict) -> str:
        return f"https://{self.account}.cine.boutique/media/{s['mediaid']['id']}?showId={s['id']}"

    def show_options(self, s: dict) -> list[str]:
        ids = [o["mediaoptionsid"]["id"] for o in s.get("showsMediaoptionsCollection") or []]
        for key in ("languagemediaoptionsid", "formatmediaoptionsid"):
            if s.get(key):
                ids.append(s[key])
        return [self.options[i]["label"] for i in dict.fromkeys(ids) if i in self.options]


def fetch(account: str) -> Data:
    home = get(f"https://{account}.cine.boutique/").text
    m = re.search(r'name="api_token"\s+content="([^"]+)"', home)
    if not m:
        raise RuntimeError(f"no api_token on {account}.cine.boutique")
    params = {"api_token": m.group(1)}
    base = f"https://{account}.cineoffice.fr/vad"
    shows = get(f"{base}/shows", params=params).json()
    media = {x["id"]: x for x in get(f"{base}/media", params=params).json()}
    options = {}
    for x in media.values():
        for o in x.get("mediaMediaoptionsCollection") or []:
            options[o["idoption"]["id"]] = o["idoption"]
    rooms = {}
    for x in get(f"{base}/screens", params=params).json():
        rooms[x["id"]] = clean(x.get("screenlabel")) or f"Salle {x.get('screennumber') or x['id']}"
    return Data(account, shows, media, options, rooms)


def parse_dt(s: str) -> datetime:
    return to_paris(datetime.fromisoformat(s))


def director(m: dict) -> str | None:
    """'SCIAMMA Céline' -> 'Céline Sciamma'; 'David Lynch' unchanged."""
    d = clean(m.get("director"))
    if not d:
        return None
    out = []
    for part in d.split(","):
        words = part.split()
        last = [w for w in words if w.isupper() and len(w) > 1]
        if last and len(last) < len(words) and words[: len(last)] == last:
            first = words[len(last) :]
            part = " ".join(first + [w.title() for w in last])
        out.append(part.strip())
    return ", ".join(out)


def title(m: dict) -> str:
    """Media title; restores the elided apostrophe of uppercase titles ('L AVENTURE')."""
    t = clean(m.get("displaytitle")) or clean(m.get("title")) or "?"
    return re.sub(r"\b([LD]) (?=[A-ZÀ-Ý])", r"\1'", t)


def film_fields(m: dict) -> dict:
    """Film-level optional fields of a media object."""
    year = str(m.get("filmyear") or "")
    alloc = str(m.get("allocineid") or "")
    return {
        "director": director(m),
        "year": int(year) if year.isdigit() else None,
        "duration": (m.get("duration") or 0) // 60 or None,
        "synopsis": clean(m.get("storyline")),
        "poster": m.get("posterpath") or None,
        "allocine_id": int(alloc) if alloc.isdigit() and int(alloc) < 10**9 else None,
    }


def showtimes(cinema_id: str, account: str, data: Data | None = None) -> list[dict]:
    """All future showtimes of a cine.boutique account, in the standard format."""
    data = data or fetch(account)
    cutoff = now() - timedelta(minutes=30)
    out = []
    for s in data.shows:
        if s.get("canceled") or s.get("deleted") or s.get("draft"):
            continue
        start = parse_dt(s["showtime"])
        if start < cutoff:
            continue
        m = data.media.get(s["mediaid"]["id"]) or {}
        opts = data.show_options(s)
        version = next((VERSION_LABELS[o] for o in opts if o in VERSION_LABELS), None)
        tags = [FORMAT_LABELS[o] for o in opts if o in FORMAT_LABELS]
        if s.get("premiere"):
            tags.append("Avant-première")
        if s.get("showevent") and clean(s.get("showeventtitle")):
            tags.append(clean(s["showeventtitle"]))
        out.append(
            show(
                cinema_id,
                title(m),
                start,
                version=version,
                url=data.booking_url(s),
                room=data.rooms.get((s.get("screenid") or {}).get("id")),
                tags=tags,
                **film_fields(m),
            )
        )
    out.sort(key=lambda x: x["start"])
    return out
