"""Saint-André des Arts — https://cinemasaintandre.com/

Showtimes: the cine.boutique ticketing JSON API (see platforms/cineboutique.py).
Tags: the WordPress posts of type "evenements" and "cycles" (REST API) describe the
special screenings. A post tags the showtimes of the films whose (uppercase) title
it quotes, on the dates it mentions.
"""

import html
import re
from datetime import date

from ..common import FR_MONTHS, Cinema, clean, get, now, strip_accents
from ..platforms import cineboutique

CINEMA = Cinema(
    id='saint-andre-des-arts',
    name='Saint-André des Arts',
    address='30 rue Saint-André des Arts, 75006 Paris',
    lat=48.853354,
    lon=2.342121,
    url='https://cinemasaintandre.com/',
    allocine='C0100',
    group='Quartier Latin',
    tags=['Art et essai'],
)

ACCOUNT = "parisstandredesarts"
WP = "https://cinemasaintandre.com/wp-json/wp/v2"

MONTHS = "|".join(sorted(FR_MONTHS, key=len, reverse=True))
DATE_RE = re.compile(
    rf"(?:du\s+)?(\d{{1,2}})(?:er)?(?:\s+(et|au)\s+(\d{{1,2}})(?:er)?)?\s+({MONTHS})\b"
)
KEYWORDS = [
    (re.compile(r"avant[- ]premi", re.I), "Avant-première"),
    (re.compile(r"rencontre|echange avec|discussion|debat|en presence|presente par", re.I), "Rencontre"),
    (re.compile(r"atelier", re.I), "Atelier"),
]


def _key(s: str) -> str:
    """Accent-free, apostrophe-free, case kept: 'L’AVENTURE RÊVÉE' -> 'L AVENTURE REVEE'."""
    s = strip_accents(html.unescape(s))
    return re.sub(r"[^\w+]+", " ", s).strip()


def _dates(text: str) -> set[date]:
    t = strip_accents(text.lower())
    today = now().date()
    out = set()
    for m in DATE_RE.finditer(t):
        month = FR_MONTHS[m[4]]
        days = [int(m[1])]
        if m[2] == "et":
            days.append(int(m[3]))
        elif m[2] == "au":
            days = list(range(int(m[1]), int(m[3]) + 1))
        for d in days:
            year = today.year + (1 if month < today.month - 2 else 0)
            try:
                out.add(date(year, month, d))
            except ValueError:
                pass
    return out


def _posts() -> list[dict]:
    out = []
    for kind in ("evenements", "cycles"):
        try:
            out += get(f"{WP}/{kind}?per_page=20&_fields=title,content").json()
        except Exception:
            pass
    return out


def _tag(shows: list[dict]) -> None:
    films = {}
    for s in shows:
        films.setdefault(_key(s["title"]), []).append(s)
    for p in _posts():
        title = html.unescape(p["title"]["rendered"])
        text = clean(html.unescape(re.sub(r"<[^>]+>", " ", p["content"]["rendered"]))) or ""
        key_text = f" {_key(title)} {_key(text)} "
        dates = _dates(text)
        plain = strip_accents(f"{title} {text}")
        kw = [label for rx, label in KEYWORDS if rx.search(plain)]
        for film, fshows in films.items():
            if len(film) < 4 or f" {film} " not in key_text:
                continue
            # event label: title parts that are not the film title nor a keyword
            parts = [x.strip() for x in title.split(":")]
            parts = [
                x for x in parts
                if x and film not in _key(x).upper() and _key(x).upper() not in film
                and not any(rx.search(strip_accents(x)) for rx, _ in KEYWORDS)
            ]
            labels = [" : ".join(parts)] if parts else []
            labels += kw
            for s in fshows:
                if dates and date.fromisoformat(s["start"][:10]) not in dates:
                    continue
                tags = s.setdefault("tags", [])
                tags += [x for x in labels if x not in tags]


def scrape() -> list[dict]:
    shows = cineboutique.showtimes(CINEMA.id, ACCOUNT)
    _tag(shows)
    return shows
