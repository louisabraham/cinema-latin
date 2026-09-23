"""La Filmothèque du Quartier Latin — https://lafilmotheque.fr/

Data sources (WordPress site):
  * /wp-json/wp/v2/programmation lists one post per week ("20260923 / Semaine du ...").
    Each post page contains a grid per room: seven day columns, one <a class="label">
    per showtime, the column is given by the CSS `left:` percentage.
  * /wp-json/wp/v2/movies?slug=... gives film metadata (original title, year,
    duration, format, synopsis, poster).
  * The home page film tooltips give the cycle badge ("event-badge") of each film.
"""

import html
import re
from datetime import date, timedelta

from ..common import Cinema, clean, combine, get, now, parse_time, show, soup

CINEMA = Cinema(
    id='filmotheque',
    name='La Filmothèque du Quartier Latin',
    address='9 rue Champollion, 75005 Paris',
    lat=48.849578,
    lon=2.342814,
    url='https://lafilmotheque.fr/',
    allocine='C0020',
    group='Quartier Latin',
    tags=['Répertoire'],
)

BASE = "https://lafilmotheque.fr"
BOOKING = "https://lafilmotheque-vad.cotecine.fr/reserver"


def _slug(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _weeks() -> list[tuple[date, str]]:
    """(first day, page url) of the weekly programmes that are not over yet."""
    posts = get(f"{BASE}/wp-json/wp/v2/programmation?per_page=5").json()
    today = now().date()
    out = []
    for p in posts:
        m = re.match(r"(\d{4})(\d{2})(\d{2})", p["title"]["rendered"])
        if not m:
            continue
        start = date(int(m[1]), int(m[2]), int(m[3]))
        if start + timedelta(days=6) >= today:
            out.append((start, p["link"]))
    return sorted(out)


def _grid(page, start: date) -> list[dict]:
    """Parse the room grids of a weekly programme page."""
    out = {}
    for grid in page.select(".grid.programmation"):
        h = grid.find_previous("h2", class_="title")
        room = clean(h.get_text()) if h else None
        for a in grid.select("a.label"):
            m = re.search(r"left:\s*([\d.]+)%", a.get("style", ""))
            strong = a.find("strong")
            hm = parse_time(strong.get_text()) if strong else None
            if not m or not hm:
                continue
            day = start + timedelta(days=round(float(m[1]) / (100 / 7)))
            h5 = a.find(class_="h5")
            d = {
                "title": clean(h5.get_text()) if h5 else "",
                "url": a["href"],
                "start": combine(day, hm),
                "room": room,
            }
            out[(d["url"], d["start"])] = d  # pages repeat the grid (desktop/overlay)
    return list(out.values())


def _badges(home) -> dict[str, list[str]]:
    """film url -> cycle badges, from the home page film tooltips."""
    out = {}
    for item in home.select(".item-content"):
        link = item.select_one("a.more-link[href*='/films/']")
        if not link:
            continue
        badges = [clean(b.get_text()) for b in item.select(".event-badge")]
        out[link["href"]] = [b for b in badges if b]
    return out


def _movies(slugs: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(slugs), 50):
        chunk = ",".join(slugs[i : i + 50])
        url = f"{BASE}/wp-json/wp/v2/movies?slug={chunk}&per_page=100&_embed=wp:featuredmedia"
        for m in get(url).json():
            out[m["slug"]] = m
    return out


def scrape() -> list[dict]:
    home = soup(BASE + "/")
    badges = _badges(home)
    rows = []
    for start, link in _weeks():
        rows += _grid(soup(link), start)

    movies = _movies(sorted({_slug(r["url"]) for r in rows}))
    cutoff = now() - timedelta(minutes=30)
    shows = []
    for r in rows:
        if r["start"] < cutoff:
            continue
        m = movies.get(_slug(r["url"]), {})
        acf = m.get("acf") or {}
        title = html.unescape(m["title"]["rendered"]) if m else r["title"]
        year = acf.get("mov_date") or ""
        media = (m.get("_embedded") or {}).get("wp:featuredmedia") or [{}]
        synopsis = acf.get("mov_synopsis")
        if synopsis:
            synopsis = clean(html.unescape(re.sub(r"<[^>]+>", " ", synopsis)))
        tags = []
        fmt = clean(acf.get("mov_format"))
        if fmt:
            tags.append(fmt)
        tags += badges.get(r["url"], [])
        shows.append(
            show(
                CINEMA.id,
                title,
                r["start"],
                url=r["url"],
                room=r["room"],
                original_title=clean(acf.get("mov_title")),
                year=int(year[:4]) if year[:4].isdigit() else None,
                duration=acf.get("mov_time") or None,
                synopsis=synopsis,
                poster=media[0].get("source_url"),
                tags=tags,
            )
        )
    shows.sort(key=lambda s: s["start"])
    return shows
