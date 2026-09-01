#!/usr/bin/env python3
"""Build data/current.json: the year in progress, from the live feed.

The Environment Agency's annual return is the authority, but it lands months
after the year ends - the 2026 return will not appear until around March 2027.
Without this the page would sit there in late 2026 with 2025 as its newest
figure, which is not much use to anyone.

Severn Trent's own live feed reports only the *latest* event per outfall, so it
cannot be asked what happened in March. Top of the Poops polls that feed and
keeps the history, so this reads their per-overflow pages.

How much can that be trusted? Checked against the official EDM return for
December 2025 - the first month where both sources have complete coverage,
because Top of the Poops only began polling these outfalls on 15 November 2025:

    Top of the Poops   136.5 h across the parish
    Official EDM       130.3 h
                       105%

Within about 5%, with the difference being events split or merged differently
rather than missed. Good enough to publish as provisional, nowhere near good
enough to present as the official figure, so the page labels it clearly and
keeps it out of the headline totals.

Do not use this for a year the EA has already published. For 2025 the same
method returns 231 hours against an official 700, because Top of the Poops was
not polling for the first ten months of it.

    ./tools/build_current.py [year]
"""

import datetime
import html
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Only the outfalls that appear in the live feed. The Milnhay works inlet
# overflow (SVT01570) is absent because it was decommissioned in January 2025.
OUTFALLS = {
    "SVT01571": "Milnhay works (storm tank)",
    "SVT00684": "Cromford Road No 3",
    "SVT01317": "Station Road",
    "SVT01316": "Milnhay Road",
    "SVT01338": "Lee Lane",
    "SVT01315": "Cromford Road",
}


def fetch(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "sewage.beardedbuddy.com"})
            with urllib.request.urlopen(req, timeout=60) as fh:
                return fh.read().decode("utf-8", "replace")
        except Exception as exc:
            if i == tries - 1:
                print(f"    failed: {type(exc).__name__}")
                return None
            time.sleep(min(2 ** i, 15))
    return None


def events(uid, year):
    """Distinct discharges as (start, stop).

    Each table row is one poll of the water-industry API, not one event, and the
    reported start of an event gets revised as it runs. So group by the event's
    END time and keep the earliest start seen for it: distinct ends are distinct
    events, and a revised start collapses back to the true one.
    """
    page = fetch(f"https://top-of-the-poops.org/overflow/{uid}?year={year}")
    if page is None:
        return []
    by_end = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        cells = [c for c in cells if c]
        if len(cells) < 5 or not re.match(r"\d\d/\d\d/\d{4}", cells[0]):
            continue
        try:
            start = datetime.datetime.strptime(cells[3], "%d/%m/%Y, %H:%M")
            stop = datetime.datetime.strptime(cells[4], "%d/%m/%Y, %H:%M")
        except ValueError:
            continue
        if stop <= start or start.year != year:
            continue
        if stop not in by_end or start < by_end[stop]:
            by_end[stop] = start
    return sorted((s, e) for e, s in by_end.items())


def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today().year
    per, latest = {}, None
    print(f"Reading the live-feed history for {year}:")
    for uid, name in OUTFALLS.items():
        ev = events(uid, year)
        hours = sum((e - s).total_seconds() / 3600 for s, e in ev)
        per[uid] = {"name": name, "events": len(ev), "hours": round(hours, 1),
                    "last": ev[-1][0].isoformat() if ev else None}
        if ev and (latest is None or ev[-1][0] > latest):
            latest = ev[-1][0]
        print("  %-28s %4d events %8.1f h" % (name, len(ev), hours))

    out = {
        "year": year,
        "asOf": datetime.date.today().isoformat(),
        "latestDischarge": latest.isoformat() if latest else None,
        "events": sum(p["events"] for p in per.values()),
        "hours": round(sum(p["hours"] for p in per.values()), 1),
        "outfalls": per,
        "provisional": True,
        "source": "Severn Trent live feed, history via top-of-the-poops.org",
        "accuracy": "Checked against the official return for December 2025, the "
                    "first month both sources cover in full: 136.5 h against "
                    "130.3 h, or 105%.",
    }
    dest = os.path.join(HERE, "data", "current.json")
    json.dump(out, open(dest, "w"), indent=1)
    print(f"\nwrote {dest}")
    print("%d: %d discharges, %.0f hours (%.1f days) to %s"
          % (year, out["events"], out["hours"], out["hours"] / 24, out["asOf"]))


if __name__ == "__main__":
    main()
