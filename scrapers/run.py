"""Run every cinema scraper, merge, enrich, and write the site data.

    uv run python -m scrapers.run [--only champo,christine] [--prev URL_OR_PATH]

Output:
  site/data/showtimes.json         merged file read by the web page
  site/data/cinemas/<id>.json      raw standard showtimes of each cinema

Per cinema, the source is chosen in this order:
  1. the cinema's own website scraper,
  2. Allociné (if the scraper fails or returns nothing),
  3. the previous published data (future showtimes only).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import requests

from . import allocine
from .check import validate
from .common import UA, clean, iso, norm_title, now, strip_accents, window
from .registry import modules

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
PAGES_URL = "https://louisabraham.github.io/cinema-latin/data/showtimes.json"
DAYS = 14


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- scraping

def keep(shows: list[dict]) -> list[dict]:
    """Drop past / far-future / duplicate showtimes."""
    lo = iso(now() - timedelta(hours=3))
    hi = iso(now() + timedelta(days=DAYS + 7))
    seen, out = set(), []
    for s in sorted(shows, key=lambda s: s["start"]):
        k = (norm_title(s["title"]), s["start"][:16])
        if lo <= s["start"] <= hi and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def scrape_one(mod, prev: dict) -> tuple[dict, list[dict]]:
    c = mod.CINEMA
    status = {"source": None, "count": 0}
    shows: list[dict] = []
    try:
        shows = keep(mod.scrape())
        errs = validate(shows, c.id)
        shows = [s for s in shows if s.get("title") and s.get("cinema") == c.id]
        if shows:
            status["source"] = "site"
        if errs:
            status["warnings"] = errs[:3]
    except NotImplementedError:
        status["error"] = "no site scraper"
    except Exception as e:  # noqa: BLE001
        status["error"] = f"{type(e).__name__}: {e}"[:300]
        log(f"[{c.id}] site scraper failed:\n{traceback.format_exc()}")
    if shows and c.allocine and getattr(mod, "ALLOCINE_COMPLEMENT", True):
        try:
            extra = complement(shows, keep(allocine.theater_showtimes(c.id, c.allocine, DAYS)))
            if extra:
                status["allocine_added"] = len(extra)
                shows = sorted(shows + extra, key=lambda s: s["start"])
        except Exception as e:  # noqa: BLE001
            status["error_allocine"] = f"{type(e).__name__}: {e}"[:300]
    if not shows and c.allocine:
        try:
            shows = keep(allocine.theater_showtimes(c.id, c.allocine, DAYS))
            if shows:
                status["source"] = "allocine"
        except Exception as e:  # noqa: BLE001
            status["error_allocine"] = f"{type(e).__name__}: {e}"[:300]
    if not shows and prev.get(c.id):
        shows = keep(prev[c.id])
        if shows:
            status["source"] = "previous"
    status["count"] = len(shows)
    log(f"[{c.id}] {status['source']} {len(shows)} showtimes {status.get('error', '')}")
    return status, shows


def complement(site: list[dict], alloc: list[dict]) -> list[dict]:
    """Allociné showtimes that the site scraper does not have.

    Some sites only list films on sale online, or only the current week. An
    Allociné showtime is kept if no site showtime of a similar title starts
    within 20 minutes of it, and only on days after the first site showtime.
    """
    if not site:
        return []
    first_day = site[0]["start"][:10]
    parsed = [(datetime.fromisoformat(s["start"]), s) for s in site]
    out = []
    for a in alloc:
        if a["start"][:10] < first_day:
            continue
        t = datetime.fromisoformat(a["start"])
        covered = False
        for st, s in parsed:
            if abs((st - t).total_seconds()) > 20 * 60:
                continue
            if s.get("allocine_id") and s["allocine_id"] == a.get("allocine_id"):
                covered = True
            else:
                covered = same_film(s["title"], a["title"]) or (
                    bool(a.get("original_title")) and same_film(s["title"], a["original_title"]))
            if covered:
                break
        if not covered:
            out.append(a)
    return out


def same_film(site_title: str, other: str) -> bool:
    """Loose test: could these two labels name the same film (or séance)?"""
    b = norm_title(other)
    for part in site_title.split(" / "):
        q = search_title(part)[0]
        a = norm_title(q)
        if not a or not b:
            continue
        if a in b or b in a or sim(q, other) >= 0.5:
            return True
        if sim(q.split(":")[0], other.split(":")[0]) >= 0.8:
            return True
    return False


def load_prev(src: str | None) -> dict[str, list[dict]]:
    """Previous showtimes per cinema, rebuilt into standard dicts."""
    if not src:
        return {}
    try:
        if src.startswith("http"):
            data = requests.get(src, headers={"User-Agent": UA}, timeout=30).json()
        else:
            data = json.loads(Path(src).read_text())
    except Exception as e:  # noqa: BLE001
        log(f"no previous data ({e})")
        return {}
    films = data.get("films", {})
    out = defaultdict(list)
    for s in data.get("showtimes", []):
        f = films.get(s["film"], {})
        d = {k: v for k, v in s.items() if k != "film"}
        d["title"] = s.get("title") or f.get("title")
        if f.get("allocine_id"):
            d["allocine_id"] = f["allocine_id"]
        out[s["cinema"]].append(d)
    return out


# ---------------------------------------------------------------- film matching

NOISE = re.compile(
    r"\b(vost?fr?|vo|vf|version restaur[ée]e|restaur[ée]|4k|35 ?mm|70 ?mm|avant[- ]premi[eè]re|"
    r"cin[ée][- ]club|reprise|copie neuve|en pr[ée]sence de.*|rencontre.*|d[ée]bat.*|\+ .*)\b",
    re.I,
)


def search_title(title: str) -> tuple[str, int | None]:
    """Cleaned title for search and a year hint, from a raw site title."""
    t = title
    year = None
    m = re.search(r"\((\d{4})\)", t)
    if m:
        year = int(m.group(1))
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", t)
    t = re.split(r"\s[–—|]\s|\s-\s", t)[0]  # "Film – 35mm" / "Film | Ciné-club"
    t = re.sub(r"^[^:]{0,30}(?:pr[ée]sente|cycle|ciné-club|festival)[^:]*:\s*", "", t, flags=re.I)
    t = NOISE.sub(" ", t)
    t = clean(t) or title
    if t.isupper():
        t = t.title()
    return t, year


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()


def best_candidate(title: str, cands: list[dict], year=None, director=None) -> dict | None:
    best, best_score = None, 0.0
    for c in cands:
        s = max(sim(title, c.get("title") or ""), sim(title, c.get("original_title") or ""))
        if year and c.get("year"):
            # a site year can be a re-release year (later), never an earlier one
            if abs(c["year"] - year) <= 1:
                s += 0.15
            elif year < c["year"]:
                s -= 0.3
        if director and c.get("directors"):
            d1 = strip_accents(director.lower())
            if any(strip_accents(d.lower()).split()[-1] in d1 for d in c["directors"] if d):
                s += 0.2
        if s > best_score:
            best, best_score = c, s
    return best if best_score >= 0.85 else None


class Matcher:
    """Resolve (cinema, title) pairs to Allociné ids."""

    def __init__(self, cinemas: dict):
        self.cinemas = cinemas
        self.metas: dict[int, dict] = {}
        self.slots: dict[tuple[str, str], int] = {}  # (cinema, start[:16]) -> id
        self.by_cinema: dict[str, list[dict]] = defaultdict(list)

    def load_feeds(self):
        def feed(c):
            if not c.allocine:
                return c.id, []
            out = []
            try:
                for day in window(DAYS):
                    for res in allocine.theater_day(c.allocine, day):
                        meta = allocine.movie_meta(res["movie"])
                        starts = [st["startsAt"][:16] for sts in (res.get("showtimes") or {}).values() for st in sts]
                        out.append((meta, starts))
            except Exception as e:  # noqa: BLE001
                log(f"[{c.id}] allocine feed failed: {e}")
            return c.id, out

        with ThreadPoolExecutor(6) as ex:
            for cid, items in ex.map(feed, self.cinemas.values()):
                for meta, starts in items:
                    self.metas[meta["allocine_id"]] = meta
                    self.by_cinema[cid].append(meta)
                    for st in starts:
                        self.slots[(cid, st)] = meta["allocine_id"]
        log(f"allocine feeds: {len(self.metas)} films")

    def resolve(self, cinema_id: str, title: str, starts: list[str], hint: dict) -> int | None:
        if hint.get("allocine_id"):
            return int(hint["allocine_id"])
        if " / " in title:  # several films in one séance: use the first one found
            for part in re.sub(r"\s\+ \d+ films?$", "", title).split(" / ")[:4]:
                aid = self.resolve(cinema_id, part, starts, hint)
                if aid:
                    return aid
            return None
        q, year = search_title(title)
        year = hint.get("year") or year
        # 1. same cinema, same film title in the Allociné feed
        c = best_candidate(q, [
            {"id": m["allocine_id"], "title": m["title"], "original_title": m["original_title"],
             "year": m["year"], "directors": m["directors"]}
            for m in self.by_cinema.get(cinema_id, [])
        ], year, hint.get("director"))
        if c:
            return c["id"]
        # 2. same cinema, same time slot, and a title that is not too different
        votes = defaultdict(int)
        for st in starts:
            if (cinema_id, st[:16]) in self.slots:
                votes[self.slots[(cinema_id, st[:16])]] += 1
        if votes:
            aid = max(votes, key=votes.get)
            m = self.metas[aid]
            if votes[aid] >= max(2, len(starts) // 2) and max(sim(q, m["title"]), sim(q, m["original_title"] or "")) > 0.5:
                return aid
        # 3. Allociné search
        cands = allocine.search(q)
        if not cands and hint.get("original_title"):
            cands = allocine.search(hint["original_title"])
        c = best_candidate(q, cands, year, hint.get("director"))
        if c is None and hint.get("original_title"):
            c = best_candidate(hint["original_title"], cands, year, hint.get("director"))
        return c["id"] if c else None

    def meta(self, aid: int) -> dict:
        if aid not in self.metas:
            try:
                self.metas[aid] = allocine.movie_page(aid)
            except Exception as e:  # noqa: BLE001
                log(f"allocine page {aid} failed: {e}")
                self.metas[aid] = {"allocine_id": aid}
        return self.metas[aid]


# ---------------------------------------------------------------- ratings

def paris_cine() -> tuple[dict[int, dict], dict[str, dict]]:
    """Ratings from paris-cine.info, by Allociné id and by normalized title."""
    try:
        r = requests.get("https://paris-cine.info/get_movies.php",
                         headers={"User-Agent": UA}, timeout=60)
        rows = r.json()["data"]
    except Exception as e:  # noqa: BLE001
        log(f"paris-cine.info failed: {e}")
        return {}, {}
    by_id, by_title = {}, {}
    for m in rows:
        def num(k):
            v = m.get(k)
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            return v or None
        ratings = {
            "imdb": num("im_r"),
            "allocine_press": num("ap_r"),
            "allocine_spect": num("as_r"),
            "senscritique": num("sc_r"),
            "letterboxd": num("lb_r"),
            "rotten_tomatoes": num("rt_r"),
            "metacritic": num("mc_r"),
        }
        links = {}
        if m.get("i_id") and m["i_id"].strip("0"):
            links["imdb"] = f"https://www.imdb.com/title/tt{m['i_id'].zfill(7)}/"
        if m.get("lb_u"):
            links["letterboxd"] = f"https://letterboxd.com/film/{m['lb_u']}/"
        if m.get("sc_u"):
            links["senscritique"] = f"https://www.senscritique.com/film/{m['sc_u']}"
        if m.get("rt_u"):
            links["rotten_tomatoes"] = f"https://rottentomatoes.com{m['rt_u']}"
        rec = {"ratings": {k: v for k, v in ratings.items() if v}, "links": links,
               "year": int(m["ye"]) if str(m.get("ye") or "").isdigit() else None}
        by_id[int(m["id"])] = rec
        for t in (m.get("ti"), m.get("o_ti")):
            if t:
                by_title.setdefault(norm_title(t), rec)
    log(f"paris-cine.info: {len(by_id)} films")
    return by_id, by_title


# ---------------------------------------------------------------- main

def film_key(aid: int | None, title: str) -> str:
    if aid:
        return f"a{aid}"
    return "t-" + re.sub(r"[^a-z0-9]+", "-", norm_title(search_title(title)[0])).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma separated cinema ids")
    ap.add_argument("--prev", default=PAGES_URL, help="previous showtimes.json (URL or path)")
    ap.add_argument("--no-enrich", action="store_true")
    a = ap.parse_args()

    mods = modules()
    if a.only:
        wanted = set(a.only.split(","))
        mods = [m for m in mods if m.CINEMA.id in wanted]
    prev = load_prev(a.prev)

    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda m: scrape_one(m, prev), mods))

    (OUT / "cinemas").mkdir(parents=True, exist_ok=True)
    cinemas, all_shows = [], []
    for mod, (status, shows) in zip(mods, results):
        cinemas.append({**mod.CINEMA.to_dict(), **status})
        (OUT / "cinemas" / f"{mod.CINEMA.id}.json").write_text(
            json.dumps(shows, ensure_ascii=False, indent=1))
        all_shows += shows

    matcher = Matcher({m.CINEMA.id: m.CINEMA for m in mods})
    pc_id, pc_title = ({}, {}) if a.no_enrich else paris_cine()
    if not a.no_enrich:
        matcher.load_feeds()

    # group showtimes by (cinema, raw title) and resolve each group once
    groups = defaultdict(list)
    for s in all_shows:
        groups[(s["cinema"], s["title"])].append(s)

    def resolve(item):
        (cid, title), shows = item
        hint = {}
        for s in shows:
            for k in ("allocine_id", "year", "director", "original_title"):
                if s.get(k) and k not in hint:
                    hint[k] = s[k]
        aid = None
        if not a.no_enrich:
            try:
                aid = matcher.resolve(cid, title, [s["start"] for s in shows], hint)
            except Exception as e:  # noqa: BLE001
                log(f"resolve {title!r} failed: {e}")
        return (cid, title), aid

    with ThreadPoolExecutor(6) as ex:
        resolved = dict(ex.map(resolve, groups.items()))

    films: dict[str, dict] = {}
    showtimes = []
    for (cid, title), shows in groups.items():
        aid = resolved[(cid, title)]
        key = film_key(aid, title)
        f = films.get(key)
        if f is None:
            meta = matcher.meta(aid) if aid else {}
            site = next((s for s in shows if s.get("synopsis") or s.get("poster")), shows[0])
            f = {
                "id": key,
                "title": meta.get("title") or search_title(title)[0],
                "original_title": meta.get("original_title") or site.get("original_title"),
                "year": meta.get("year") or site.get("year"),
                "directors": meta.get("directors") or ([site["director"]] if site.get("director") else []),
                "cast": meta.get("cast") or [],
                "duration": meta.get("duration") or site.get("duration"),
                "genres": meta.get("genres") or [],
                "countries": meta.get("countries") or [],
                "synopsis": meta.get("synopsis") or site.get("synopsis"),
                "poster": meta.get("poster") or site.get("poster"),
                "allocine_id": aid,
                "ratings": dict((meta.get("ratings") or {})),
                "links": {},
            }
            if aid:
                f["links"]["allocine"] = f"https://www.allocine.fr/film/fichefilm_gen_cfilm={aid}.html"
            pc = pc_id.get(aid) if aid else None
            if pc is None:
                cand = pc_title.get(norm_title(f["title"]))
                if cand and (not f["year"] or not cand["year"] or abs(cand["year"] - f["year"]) <= 1):
                    pc = cand
            if pc:
                f["ratings"].update(pc["ratings"])
                f["links"].update(pc["links"])
            f["ratings"] = {k: v for k, v in f["ratings"].items() if v}
            films[key] = f
        for s in shows:
            st = {"film": key, "cinema": cid, "start": s["start"]}
            if s["title"] != f["title"]:
                st["title"] = s["title"]  # the cinema's own label (may hold event info)
            for k in ("version", "url", "room", "tags"):
                if s.get(k):
                    st[k] = s[k]
            if st.get("version") == "VO" and f["countries"] and set(f["countries"]) <= {"France"}:
                del st["version"]  # some ticketing APIs mark every showtime VO
            showtimes.append(st)

    showtimes.sort(key=lambda s: (s["start"], s["cinema"]))
    data = {
        "generated_at": iso(now()),
        "cinemas": cinemas,
        "films": films,
        "showtimes": showtimes,
    }
    (OUT / "showtimes.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    matched = sum(1 for f in films.values() if f["allocine_id"])
    rated = sum(1 for f in films.values() if f["ratings"])
    log(f"\n{len(showtimes)} showtimes, {len(films)} films ({matched} matched on Allociné, {rated} with ratings)")
    for c in cinemas:
        log(f"  {c['id']:22s} {str(c['source']):9s} {c['count']:4d}  {c.get('error', '')}")


if __name__ == "__main__":
    main()
