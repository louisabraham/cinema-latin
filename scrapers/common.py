"""Shared helpers for all cinema scrapers.

Every cinema module in `scrapers/cinemas/` exposes:

    CINEMA = Cinema(...)
    def scrape() -> list[dict]   # list of showtimes built with `show(...)`

A showtime dict has this standard shape (optional keys are omitted when unknown):

    {
      "cinema": "champo",                       # Cinema.id
      "title": "La Horde sauvage",              # title as displayed by the cinema
      "start": "2026-09-23T20:00:00+02:00",     # ISO 8601, Europe/Paris offset
      "version": "VO" | "VF",                   # optional
      "url": "https://...",                     # optional, booking or film page
      "original_title": "The Wild Bunch",       # optional
      "director": "Sam Peckinpah",              # optional
      "year": 1969,                             # optional
      "duration": 145,                          # optional, minutes
      "room": "Salle 1",                        # optional
      "tags": ["35mm", "Rencontre"],            # optional, free text labels
      "allocine_id": 1276,                      # optional, when the site gives it
      "synopsis": "...", "poster": "https://...",  # optional
    }
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("Europe/Paris")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
DAYS_AHEAD = 14

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5"})


@dataclass
class Cinema:
    id: str
    name: str
    address: str
    lat: float
    lon: float
    url: str
    allocine: str | None = None  # Allociné theater code, e.g. "C0015"
    group: str = "Quartier Latin"  # "Quartier Latin" or "Ailleurs"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def get(url: str, retries: int = 3, **kw) -> requests.Response:
    kw.setdefault("timeout", 30)
    for i in range(retries):
        try:
            r = SESSION.get(url, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))
    raise AssertionError


def soup(url: str, **kw) -> BeautifulSoup:
    r = get(url, **kw)
    return BeautifulSoup(r.content, "lxml")


def now() -> datetime:
    return datetime.now(TZ)


def to_paris(dt: datetime) -> datetime:
    """Attach Paris tz to a naive datetime, or convert an aware one."""
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def iso(dt: datetime) -> str:
    return to_paris(dt).replace(microsecond=0).isoformat()


VO_RE = re.compile(r"\b(vost?f?r?|vo|v\.o\.|version originale)\b", re.I)
VF_RE = re.compile(r"\b(vf|v\.f\.|version fran[cç]aise)\b", re.I)


def version_of(text: str | None) -> str | None:
    if not text:
        return None
    if VO_RE.search(text):
        return "VO"
    if VF_RE.search(text):
        return "VF"
    return None


def parse_duration(text) -> int | None:
    """'2h 25min', '1h32', '145 min', 'PT2H25M', 8700 (seconds) -> minutes."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text // 60) if text > 600 else int(text)
    t = str(text)
    m = re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?", t)
    if m and (m.group(1) or m.group(2)):
        return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    m = re.search(r"(\d+)\s*h\s*(\d+)?", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2) or 0)
    m = re.search(r"(\d+)\s*min", t)
    if m:
        return int(m.group(1))
    return None


FR_MONTHS = {
    "janvier": 1, "janv": 1, "jan": 1,
    "fevrier": 2, "fevr": 2, "fev": 2,
    "mars": 3, "mar": 3,
    "avril": 4, "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7, "juil": 7,
    "aout": 8,
    "septembre": 9, "sept": 9, "sep": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "decembre": 12, "dec": 12,
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def parse_fr_date(text: str, ref: date | None = None) -> date | None:
    """'mercredi 23 septembre', '23 sept. 2026', '23/09' -> date. Year inferred if missing."""
    ref = ref or now().date()
    t = strip_accents(text.lower())
    m = re.search(r"(\d{1,2})(?:er)?\s+([a-z]+)\.?(?:\s+(\d{4}))?", t)
    day = month = year = None
    if m and m.group(2).rstrip(".") in FR_MONTHS:
        day, month = int(m.group(1)), FR_MONTHS[m.group(2).rstrip(".")]
        year = int(m.group(3)) if m.group(3) else None
    else:
        m = re.search(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", t)
        if not m:
            return None
        day, month = int(m.group(1)), int(m.group(2))
        if m.group(3):
            year = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
    if year is None:
        # choose the year that puts the date closest to ref (handles Dec -> Jan)
        cands = [date(y, month, day) for y in (ref.year - 1, ref.year, ref.year + 1)]
        return min(cands, key=lambda d: abs((d - ref).days))
    return date(year, month, day)


def parse_time(text: str) -> tuple[int, int] | None:
    m = re.search(r"(\d{1,2})\s*[h:H]\s*(\d{2})?", text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2) or 0)


def combine(d: date, hm: tuple[int, int]) -> datetime:
    return datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=TZ)


def clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def show(cinema: str, title: str, start: datetime, **extra) -> dict:
    """Build a standard showtime dict. Unknown keys raise, None values are dropped."""
    allowed = {
        "version", "url", "original_title", "director", "year", "duration",
        "room", "tags", "allocine_id", "synopsis", "poster",
    }
    bad = set(extra) - allowed
    if bad:
        raise ValueError(f"unknown showtime keys: {bad}")
    d = {"cinema": cinema, "title": clean(title), "start": iso(start)}
    for k, v in extra.items():
        if isinstance(v, str):
            v = clean(v)
        if v in (None, "", []):
            continue
        d[k] = v
    return d


def norm_title(s: str) -> str:
    """Normalized key for title matching."""
    s = strip_accents(s.lower())
    s = re.sub(r"\((vo|vf|vostf|version restauree|4k|reprise)[^)]*\)", " ", s)
    s = re.sub(r"^(le|la|les|l'|the|un|une|a)\s+", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def window(days: int = DAYS_AHEAD) -> list[date]:
    today = now().date()
    return [today + timedelta(days=i) for i in range(days)]
