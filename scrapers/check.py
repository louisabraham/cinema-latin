"""Run one cinema scraper and compare it with Allociné for the same cinema.

    uv run python -m scrapers.check champo [--days 7] [--json]

Prints: number of showtimes, a sample, per-day counts, and the share of
Allociné showtimes (same day + same HH:MM) also found by the scraper, and the
reverse. A good scraper has both shares close to 100% on days both cover
(the cinema site is the reference: it can contain more than Allociné).
"""

import argparse
import json
from collections import Counter

from . import allocine
from .registry import by_id


def validate(shows: list[dict], cinema_id: str) -> list[str]:
    errs = []
    for s in shows:
        if s.get("cinema") != cinema_id:
            errs.append(f"wrong cinema id: {s}")
        if not s.get("title"):
            errs.append(f"empty title: {s}")
        if s.get("version") not in (None, "VO", "VF"):
            errs.append(f"bad version: {s}")
    keys = [(s["title"], s["start"]) for s in shows]
    dups = [k for k, n in Counter(keys).items() if n > 1]
    if dups:
        errs.append(f"{len(dups)} duplicate (title, start) pairs, e.g. {dups[:3]}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cinema")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true", help="dump all showtimes")
    a = ap.parse_args()

    mod = by_id(a.cinema)
    shows = mod.scrape()
    print(f"{len(shows)} showtimes from site scraper")
    if a.json:
        print(json.dumps(shows, ensure_ascii=False, indent=1))
    else:
        for s in shows[:5]:
            print("  ", json.dumps(s, ensure_ascii=False))
    for e in validate(shows, a.cinema)[:10]:
        print("  INVALID:", e)
    titles = Counter(s["title"] for s in shows)
    print(f"{len(titles)} distinct titles:", ", ".join(list(titles)[:15]))

    if not mod.CINEMA.allocine:
        return
    ref = allocine.theater_showtimes(a.cinema, mod.CINEMA.allocine, a.days)
    days = sorted({s["start"][:10] for s in ref})
    site = {s["start"][:16] for s in shows}
    alloc = {s["start"][:16] for s in ref}
    print(f"\nper day (site / allocine), first {a.days} days:")
    sc = Counter(s[:10] for s in site)
    ac = Counter(s[:10] for s in alloc)
    for d in sorted(set(sc) | set(ac))[: a.days + 3]:
        print(f"  {d}: {sc.get(d, 0):3d} / {ac.get(d, 0):3d}")
    common_days = set(days) & {s[:10] for s in site}
    a_in = {s for s in alloc if s[:10] in common_days}
    s_in = {s for s in site if s[:10] in common_days}
    if a_in:
        print(f"allocine slots found by site scraper: {len(a_in & site)}/{len(a_in)}")
        print(f"site slots found in allocine:        {len(s_in & alloc)}/{len(s_in)}")
        miss = sorted(a_in - site)[:8]
        if miss:
            print("  missing from site scraper, e.g.:", miss)
            by_start = {s["start"][:16]: s["title"] for s in ref}
            print("   ", [by_start[m] for m in miss])


if __name__ == "__main__":
    main()
