#!/usr/bin/env python3
"""One-time bootstrap of the Worker's event record. Run once, then never again.

The Worker keeps its own record of every discharge by polling Severn Trent's
live feed every five minutes, so from the moment it is deployed this site
depends on nobody else's archive. What it cannot do is remember a year that
started before it did.

Severn Trent publish a per-year EDM feature service, but only after the year has
finished (STW_Edm_2025 exists, STW_Edm_2026 does not), and the Environment
Agency's return for a year lands around the following March. So for the months
of the current year that have already passed there is exactly one public record:
Top of the Poops, who have been polling the same feed and keeping the history.

This script reads that once and writes it into the Worker's KV in the Worker's
own format. After that the Worker maintains it, and the seeded portion is
replaced wholesale when the EA publishes the annual return. That is the entire
extent of the dependency, and it ends here.

    ./tools/seed_events.py [year] [--remote]

Writes a file, then prints the wrangler command to load it. Nothing is uploaded
without you running that command.
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_current  # noqa: E402  (reuse its scraping and de-duplication)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    year = int(args[0]) if args else datetime.date.today().year
    remote = "--remote" in sys.argv

    # The Worker keys events on "<id>|<end epoch ms>" with the start epoch ms as
    # the value, so that a start revised while a discharge is running collapses
    # back to one event. Match that exactly.
    store = {}
    print(f"Reading {year} from the live-feed history:")
    for uid, name in build_current.OUTFALLS.items():
        ev = build_current.events(uid, year)
        for start, stop in ev:
            # build_current already returns UTC-aware datetimes, converted from
            # the British local times that page displays.
            s = int(start.timestamp() * 1000)
            e = int(stop.timestamp() * 1000)
            # Same key as the Worker: end time rounded down to the minute, with
            # the exact times in the value. The page these come from only shows
            # minutes, while the live feed reports seconds, so without rounding
            # a seeded event never matches the same event seen live and the
            # discharge is counted twice.
            key = f"{uid}|{e // 60000}"
            if key not in store or s < store[key][0]:
                store[key] = [s, e]
        hours = sum((b - a).total_seconds() / 3600 for a, b in ev)
        print("  %-28s %4d events %8.1f h" % (name, len(ev), hours))

    dest = os.path.join(HERE, ".cache", f"seed-events-{year}.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    json.dump(store, open(dest, "w"), separators=(",", ":"))

    total_h = sum((v[1] - v[0]) / 3600000 for v in store.values())
    print(f"\n{len(store)} events, {total_h:.0f} hours -> {dest}")
    print("\nLoad it with:\n")
    print(f'  npx wrangler kv key put "events:{year}" --path "{dest}" \\')
    print(f'      --binding DATA {"--remote" if remote else "--local"}\n')
    print("The Worker takes over from there. Delete this script once the")
    print("Environment Agency has published the return for this year.")


if __name__ == "__main__":
    main()
