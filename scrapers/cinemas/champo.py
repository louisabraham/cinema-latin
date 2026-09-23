"""Le Champo — https://cinema-lechampo.com/

Showtimes from the Ciné Office API (see platforms/cineoffice.py). The site only
publishes the current week (Wednesday to Tuesday) plus a few special dates.
Talks and ciné-club sessions are listed as text on two event pages; they are
matched to showtimes by date and title to add "Rencontre" / "Ciné-club" tags.
"""

import re
from difflib import SequenceMatcher

from bs4 import BeautifulSoup

from ..common import Cinema, get, norm_title, parse_fr_date, parse_time
from ..platforms import cineoffice

CINEMA = Cinema(
    id='champo',
    name='Le Champo',
    address='51 rue des Écoles, 75005 Paris',
    lat=48.849989,
    lon=2.343227,
    url='https://cinema-lechampo.com/',
    allocine='C0073',
    group='Quartier Latin',
    tags=['Répertoire'],
)

SITE = "https://www.cinema-lechampo.com"
ACCOUNT = "pariscinemalechampo"
EVENT_PAGES = {
    "/evenements/seances-speciales.html": ["Rencontre"],
    "/evenements/cine-clubs.html": ["Ciné-club", "Rencontre"],
}


def _film_url(media_id, show_id, title):
    return f"{SITE}/film.html#/media/{media_id}?" + cineoffice.query(showId=show_id, title=title)


def _event_entries(path: str) -> list[tuple]:
    """[(date, (h, m) | None, normalized text after the date)] from an event page."""
    try:
        s = BeautifulSoup(get(SITE + path).content, "lxml")
    except Exception:
        return []
    main = s.find(id="tm-main") or s.body
    text = main.get_text(" ", strip=True)
    out = []
    for chunk in text.split("📍")[1:]:
        head = chunk[:60]
        d = parse_fr_date(head)
        if not d:
            continue
        m = re.search(r"\b(\d{1,2}h\d{0,2})\b", head)
        out.append((d, parse_time(m.group(1)) if m else None, norm_title(chunk[:250])))
    return out


def _tag_events(shows: list[dict]) -> None:
    for path, tags in EVENT_PAGES.items():
        for d, hm, text in _event_entries(path):
            for s in shows:
                if s["start"][:10] != d.isoformat():
                    continue
                if hm and s["start"][11:16] != f"{hm[0]:02d}:{hm[1]:02d}":
                    continue
                key = norm_title(s["title"])
                if not key:
                    continue
                found = re.search(rf"\b{re.escape(key)}\b", text)
                if not found and hm:
                    # same date and time: accept a close title (the page has typos)
                    lcs = SequenceMatcher(None, key, text).find_longest_match(0, len(key), 0, len(text))
                    found = lcs.size >= 0.6 * len(key)
                if found:
                    s["tags"] = s.get("tags", []) + [t for t in tags if t not in s.get("tags", [])]


def scrape() -> list[dict]:
    token = cineoffice.api_token(SITE + "/")
    shows = cineoffice.scrape(CINEMA.id, ACCOUNT, token, film_url=_film_url)
    _tag_events(shows)
    return shows
