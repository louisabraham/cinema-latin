"""Webedia / Boxoffice "Gatsby" cinema websites (cinemadupantheon.fr, nouvelodeon.com, ...).

The static site is built with Gatsby; showtimes are loaded client side from a
small API served by the same host:

    /page-data/index/page-data.json      -> list of static query hashes
    /page-data/sq/d/<hash>.json          -> theaters, events, attributes, movies
    /api/gatsby-source-boxofficeapi/schedule?theaters={"id":..,"timeZone":..}&from=..&to=..
    /api/gatsby-source-boxofficeapi/movies?ids=..&ids=..

Theater ids and movie ids are Allociné ids (custom films use ids such as "c2202").
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta

from ..common import TZ, get, now, parse_duration, show, strip_accents

API = "/api/gatsby-source-boxofficeapi"
DELAY = 0.4  # seconds between two requests to the same site
DAYS = 28  # the site publishes special screenings several weeks ahead

# Showtime tags turned into free text labels (other tags are ignored).
TAG_LABELS = {
    "Format.Projection.35mm": "35mm",
    "Format.Projection.70mm": "70mm",
    "Format.Projection.Film35mm": "35mm",
    "Format.Projection.Film70mm": "70mm",
    "Format.Projection.Imax": "IMAX",
    "Localization.Subtitle.English": "English subs",
    "Showtime.Accessibility.HearingImpaired": "ST-SME",
    "Showtime.Accessibility.AudioDescription": "Audio description",
}
CYCLE_RE = re.compile(r"cycle|club|r[ée]tro|festival|jeune public", re.I)


class Site:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self._last = 0.0

    def json(self, path: str, **kw):
        wait = self._last + DELAY - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        return get(self.base + path, **kw).json()

    def static_queries(self) -> dict[str, list]:
        """All static query results of the home page, grouped by top-level key."""
        idx = self.json("/page-data/index/page-data.json")
        out: dict[str, list] = {}
        for h in idx.get("staticQueryHashes") or []:
            try:
                data = self.json(f"/page-data/sq/d/{h}.json").get("data") or {}
            except Exception:
                continue
            for k, v in data.items():
                out.setdefault(k, []).append(v)
        return out


def _nodes(sq: dict, key: str) -> list[dict]:
    return [n for v in sq.get(key, []) if v for n in v.get("nodes") or []]


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace(" ", "T")).replace(tzinfo=TZ)


def _has_time(s: str | None) -> bool:
    return bool(s) and len(s) > 10


def _camel(s: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", s)


def _event_rules(events: list[dict], theater_id: str) -> list[tuple]:
    """(movie_id, start, end, exact, labels) rules telling which showtimes belong to an event."""
    rules = []
    for e in events:
        ths = {t.get("id") for t in e.get("theaters") or []}
        if ths and theater_id not in ths:
            continue
        typ = re.sub(r"^\W+", "", e.get("type") or "").strip()
        title = (e.get("title") or "").split(" · ")[0].strip()
        related = [r for r in e.get("relatedMovies") or [] if r.get("movie")]
        labels = [typ] if typ else []
        if title and title.lower() != typ.lower() and (len(related) > 1 or CYCLE_RE.search(typ)):
            labels.append(title)
        if not labels:
            continue
        # default time range of the event
        ev_start = _dt(e.get("startAt"))
        if ev_start:
            ev_start = ev_start.replace(hour=0, minute=0)
        end_s = e.get("endAt") or e.get("visibleEndAt")
        ev_end = _dt(end_s)
        if ev_end and not _has_time(end_s):
            ev_end += timedelta(days=1)
        if not ev_end and _has_time(e.get("startAt")) and len(related) == 1:
            ev_end = ev_start + timedelta(days=1)  # one-off screening
        for r in related:
            mid = str(r["movie"]["id"])
            for rng in r.get("showtimes") or [[None, None]]:
                s, t = (list(rng) + [None, None])[:2]
                if s and not t:
                    rules.append((mid, _dt(s), None, True, labels))
                elif s and t:
                    rules.append((mid, _dt(s), _dt(t), False, labels))
                else:
                    rules.append((mid, ev_start, ev_end, False, labels))
    return rules


def _event_labels(rules, mid: str, start: datetime) -> list[str]:
    out = []
    for rmid, s, t, exact, labels in rules:
        if rmid != mid:
            continue
        if exact:
            ok = s == start
        else:
            ok = (s is None or start >= s) and (t is None or start < t)
        if ok:
            out += labels
    return out


def _person(p: dict) -> str:
    return f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip()


def _movie_meta(m: dict) -> dict:
    exh = m.get("exhibitor") or {}
    directors = [_person(n["person"]) for n in (m.get("directors") or {}).get("nodes") or [] if n.get("person")]
    if not directors:
        directors = m.get("direction") or []
    years = [int(r["releasedAt"][:4]) for r in m.get("releases") or [] if r.get("releasedAt")]
    synopsis = exh.get("synopsis") or m.get("synopsis")
    if synopsis:
        synopsis = re.sub(r"<[^>]+>", " ", synopsis)
    return {
        "title": exh.get("title") or m.get("title"),
        "original_title": m.get("originalTitle"),
        "director": ", ".join(d for d in directors if d) or None,
        # only French release dates are known: trust them for recent films only
        # (a classic's first French release can be a late re-release)
        "year": min(years) if years and min(years) >= now().year - 2 else None,
        "duration": parse_duration(m.get("runtime")),
        "synopsis": synopsis,
        "poster": exh.get("poster") or m.get("poster"),
    }


def scrape(cinema_id: str, base: str, theater_id: str | None = None, days: int = DAYS) -> list[dict]:
    site = Site(base)
    sq = site.static_queries()

    theaters = [t for t in _nodes(sq, "allTheater") if t.get("timeZone")]
    if theater_id:
        theaters = [t for t in theaters if t["id"] == theater_id] or [{"id": theater_id, "timeZone": "Europe/Paris"}]
    theater = theaters[0]
    tid = theater["id"]
    multi = len(theater.get("screens") or []) != 1

    attr_labels = {}
    for a in _nodes(sq, "allAttribute"):
        for loc in a.get("localizations") or []:
            if loc.get("label"):
                attr_labels[a["tag"]] = loc["label"]
    film_paths = {str(m["id"]): m.get("path") for m in _nodes(sq, "allMovie") if m.get("path")}
    rules = _event_rules(_nodes(sq, "allEvent"), tid)

    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    th = json.dumps({"id": tid, "timeZone": theater["timeZone"]}, separators=(",", ":"))
    data = site.json(f"{API}/schedule", params={
        "theaters": th,
        "from": today.strftime("%Y-%m-%dT%H:%M:%S"),
        "to": (today + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
    }) or {}
    schedule = (data.get(tid) or {}).get("schedule") or {}

    metas: dict[str, dict] = {}
    ids = list(schedule)
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        for m in site.json(f"{API}/movies", params=[("ids", x) for x in chunk]) or []:
            metas[str(m["id"])] = _movie_meta(m)

    shows = []
    for mid, by_day in schedule.items():
        meta = metas.get(mid, {})
        title = meta.get("title")
        if not title:
            continue
        page = film_paths.get(mid)
        page = base.rstrip("/") + page if page else None
        for sts in by_day.values():
            for st in sts:
                start = _dt(st["startsAt"])
                tags = st.get("tags") or []
                if "Localization.Version.Original" in tags:
                    version = "VO"
                elif "Localization.Language.French" in tags or "Showtime.Accessibility.Dubbed" in tags:
                    version = "VF"
                else:
                    version = None
                labels = []
                for t in tags:
                    if t in TAG_LABELS:
                        labels.append(TAG_LABELS[t])
                    elif t.startswith("BoostPos.") and "Salle" not in t:
                        labels.append(attr_labels.get(t) or _camel(t.split(".")[-1]))
                labels = _event_labels(rules, mid, start) + labels
                seen, uniq = set(), []
                for lab in labels:
                    k = re.sub(r"[^a-z0-9]", "", strip_accents(lab.lower()))
                    if k not in seen:
                        seen.add(k)
                        uniq.append(lab)
                labels = uniq
                url = None
                for tk in (st.get("data") or {}).get("ticketing") or []:
                    if tk.get("provider") == "default" and tk.get("urls"):
                        url = tk["urls"][0]
                        break
                screen = ((st.get("screen") or {}).get("name") or "").strip()
                room = (f"Salle {screen}" if screen.isdigit() else screen) if multi and screen else None
                shows.append(show(
                    cinema_id, title, start,
                    version=version,
                    url=url or page or base,
                    original_title=meta.get("original_title"),
                    director=meta.get("director"),
                    year=meta.get("year"),
                    duration=meta.get("duration"),
                    room=room,
                    tags=labels,
                    allocine_id=int(mid) if mid.isdigit() else None,
                    synopsis=meta.get("synopsis"),
                    poster=meta.get("poster"),
                ))
    shows.sort(key=lambda s: (s["start"], s["title"]))
    return shows
