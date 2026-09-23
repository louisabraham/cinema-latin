"""Dulac Cinémas (Reflet Médicis, L'Arlequin, Escurial, Majestic Passy, Majestic Bastille).

The site https://www.dulaccinemas.com/ is a React app over a Drupal backend.
One JSON call gives all showtimes of all Dulac cinemas for the next N days:

    GET /api/home-bootstrap?days=14
      -> {seances_week: [...], films_by_id: {...}, salles_by_id: {...}, cinemas_by_id: {...}}

`seances_week[].date` is UTC without offset. Booking links go to ticketingcine.com.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..common import DAYS_AHEAD, clean, get, now, show

BASE = "https://www.dulaccinemas.com"

TAG_MAP = {
    "video 3d": "3D",
    "first session": "Première séance",
    "avant-premiere": "Avant-première",
    "avant-première": "Avant-première",
}


def _bootstrap(days: int) -> dict:
    return get(f"{BASE}/api/home-bootstrap", params={"days": days}).json()


def _tags(s: dict) -> list[str]:
    raw = []
    if s.get("type") and s["type"] != "standard":
        raw.append(s["type"])
    raw += [s.get("event_label") or "", s.get("info") or ""]
    raw += s.get("featured_tags") or []
    raw += s.get("accessibility_modes") or []
    out: list[str] = []
    for t in raw:
        t = clean(t)
        if not t:
            continue
        t = TAG_MAP.get(t.lower(), t)
        if re.match(r"en pr[ée]sence|rencontre|d[ée]bat", t, re.I) and "Rencontre" not in out:
            out.append("Rencontre")
        if t not in out:
            out.append(t)
    return out


def scrape(cinema_id: str, cinema_name: str, days: int = DAYS_AHEAD) -> list[dict]:
    """`cinema_name` is the Dulac cinema title, e.g. "Reflet Medicis" or "L'Arlequin"."""
    data = _bootstrap(days)
    cinemas = data.get("cinemas_by_id") or {}
    target = {k for k, c in cinemas.items() if clean(c.get("title", "")).lower() == cinema_name.lower()}
    if not target:
        raise RuntimeError(f"Dulac cinema {cinema_name!r} not found in {[c.get('title') for c in cinemas.values()]}")
    salles = data.get("salles_by_id") or {}
    films = data.get("films_by_id") or {}

    start_min = now() - timedelta(minutes=30)
    seen = set()
    shows: list[dict] = []
    for s in data.get("seances_week") or []:
        salle = salles.get(str(s.get("salle_id"))) or {}
        if str(salle.get("cinema_id")) not in target or s.get("is_cancelled"):
            continue
        film = films.get(str(s.get("film_id"))) or {}
        # seance title is "<cinema>:<film>:<dd/mm/yyyy hh:mm:ss>"
        parts = (s.get("title") or "").split(":")
        title = film.get("title") or (parts[1] if len(parts) > 2 else None)
        if not title or not s.get("date"):
            continue
        dt = datetime.fromisoformat(s["date"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < start_min:
            continue
        key = (s.get("film_id"), s.get("salle_id"), dt)
        if key in seen:
            continue
        seen.add(key)
        version = {"VOST": "VO", "VOSTF": "VO", "VO": "VO", "VF": "VF"}.get((s.get("version") or "").upper())
        room = re.sub(r"\s*\(.*\)\s*$", "", salle.get("title") or "") or None
        original = film.get("original_title")
        film_url = f"{BASE}/film/id/{film['drupal_internal__nid']}" if film.get("drupal_internal__nid") else None
        shows.append(show(
            cinema_id, title, dt,
            version=version,
            url=s.get("booking_url") or film_url,
            original_title=original if original and original != title else None,
            director=", ".join(film.get("directors") or []) or film.get("director"),
            year=film.get("year") or None,
            duration=film.get("duration") or None,
            room=room,
            tags=_tags(s),
            synopsis=film.get("synopsis"),
            # the API gives the 120px poster; 320px also exists
            poster=re.sub(r"/movie_poster/120/", "/movie_poster/320/", film.get("poster_url") or "") or None,
        ))
    shows.sort(key=lambda x: (x["start"], x["title"]))
    return shows
