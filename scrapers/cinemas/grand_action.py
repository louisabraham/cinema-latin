"""Le Grand Action — https://www.legrandaction.com/

Data sources:
  * home page: `scheduleData = {...}` JSON with every showtime
    (film post id -> date -> time -> {room, lang, format, showId}).
  * WordPress REST /wp-json/wp/v2/films?include=... : film title and page URL.
  * cine.boutique ticketing API (platforms/cineboutique.py), matched by showId:
    booking link, director, year, duration, synopsis, poster, Allociné id.
  * film pages, only for films with a cycle / ciné-club tag (class "mct-tag-..."
    in the REST data): tag names and director.
"""

import html
import json
import re
import time
from datetime import datetime, timedelta

from ..common import TZ, Cinema, clean, get, now, show, soup, version_of
from ..platforms import cineboutique

CINEMA = Cinema(
    id='grand-action',
    name='Le Grand Action',
    address='5 rue des Écoles, 75005 Paris',
    lat=48.847521,
    lon=2.352127,
    url='https://www.legrandaction.com/',
    allocine='C0072',
    group='Quartier Latin',
    tags=['Répertoire'],
)

BASE = "https://www.legrandaction.com"
ACCOUNT = "pariscinemagrandaction"


def _schedule() -> dict:
    page = get(BASE + "/").text
    m = re.search(r"scheduleData\s*=\s*(\{.*?\});\s*(?:</script>|\n)", page, re.S)
    if not m:
        raise RuntimeError("scheduleData not found on legrandaction.com")
    return json.loads(m.group(1))["calendar"]["movies"]


def _films(ids: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ",".join(ids[i : i + 50])
        url = (
            f"{BASE}/wp-json/wp/v2/films?include={chunk}&per_page=100"
            "&_fields=id,title,link,class_list,yoast_head_json"
        )
        for f in get(url).json():
            out[str(f["id"])] = f
    return out


GENERIC_TAGS = {"a-laffiche", "prochainement"}


def _page_info(url: str) -> dict:
    """Cycle tags and director from a film page."""
    page = soup(url)
    tags = [clean(a.get_text().strip(" ,")) for a in page.select("a.mct-tag")]
    tags = [x for x in tags if x and not re.search(r"affiche|prochainement", x, re.I)]
    directors = [clean(a.get_text().strip(" ,")) for a in page.select(".directors-container a.mct-director")]
    directors = [d for d in directors if d]
    return {"tags": list(dict.fromkeys(tags)), "director": ", ".join(dict.fromkeys(directors)) or None}


def scrape() -> list[dict]:
    sched = _schedule()
    films = _films(sorted(sched))
    try:
        cb = cineboutique.fetch(ACCOUNT)
    except Exception:
        cb = None
    cb_shows = {str(s["id"]): s for s in cb.shows} if cb else {}

    info = {}
    for film_id, f in films.items():
        special = [
            c for c in f.get("class_list") or []
            if c.startswith("mct-tag-") and c[8:] not in GENERIC_TAGS
        ]
        if special and f.get("link"):
            try:
                info[film_id] = _page_info(f["link"])
            except Exception:
                pass
            time.sleep(0.5)

    cutoff = now() - timedelta(minutes=30)
    out = []
    for film_id, days in sched.items():
        f = films.get(film_id, {})
        title = html.unescape(f["title"]["rendered"]) if f else None
        page = f.get("link")
        og = ((f.get("yoast_head_json") or {}).get("og_image") or [{}])[0].get("url")
        for day, times in days.items():
            for hm, x in times.items():
                start = datetime.fromisoformat(f"{day}T{hm}").replace(tzinfo=TZ)
                if start < cutoff:
                    continue
                s = cb_shows.get(str(x.get("showId")))
                m = cb.media.get(s["mediaid"]["id"], {}) if s else {}
                extra = cineboutique.film_fields(m) if m else {}
                if og and not extra.get("poster"):
                    extra["poster"] = og
                page_info = info.get(film_id, {})
                if page_info.get("director"):
                    extra["director"] = page_info["director"]
                tags = list(page_info.get("tags", []))
                if x.get("format"):
                    tags.append(x["format"])
                if s and s.get("premiere"):
                    tags.append("Avant-première")
                if s and s.get("showevent") and s.get("showeventtitle"):
                    tags.append(s["showeventtitle"])
                out.append(
                    show(
                        CINEMA.id,
                        title or (cineboutique.title(m) if m else "?"),
                        start,
                        version=version_of(x.get("lang")),
                        url=cb.booking_url(s) if s else page,
                        room=f"Salle {x['room']}" if x.get("room") else None,
                        tags=tags,
                        **extra,
                    )
                )
    out.sort(key=lambda s: s["start"])
    return out
