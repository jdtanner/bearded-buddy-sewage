#!/usr/bin/env python3
"""Build data/wfd.json: the official condition of the river, and why.

Everything else on this site counts discharges. This is the other half - what
the water is actually like, assessed by the Environment Agency under the Water
Framework Directive, and what the Agency says is causing it.

Two things come out of the Catchment Data Explorer for our reach of the Erewash:

  * The classification history. One status per year, from Moderate down to Poor.

  * RNAG - Reasons for Not Achieving Good. For each failing element the Agency
    records the pressure responsible, the business sector, and a certainty:
    Confirmed, Probable or Suspected. "Sewage discharge (intermittent)" is their
    term for a storm overflow.

    ./tools/build_wfd.py
"""

import csv
import html
import io
import json
import os
import re
import subprocess
import sys
import collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, ".cache")
BASE = "https://environment.data.gov.uk/catchment-planning/WaterBody"

# Our reach. The parish also touches the one above it, but this is the water
# beside the village and it takes Milnhay works.
WATERBODY = "GB104028052511"
NAME = "Erewash from Nethergreen Brook to Gilt Brook"


def get(url, dest):
    if not (os.path.exists(dest) and os.path.getsize(dest) > 200):
        subprocess.run(["curl", "-sL", "--max-time", "120", "-o", dest, url], check=True)
    return open(dest, encoding="utf-8", errors="replace").read()


def classifications():
    raw = get(f"{BASE}/{WATERBODY}/classifications.csv",
              os.path.join(CACHE, f"wfd_{WATERBODY}.csv"))
    rows = list(csv.DictReader(io.StringIO(raw)))

    def f(r, col):
        # The first column arrives with a BOM and quotes attached.
        return (r.get(col) or r.get('﻿"%s"' % col) or "").strip()

    # Two series matter and they do not cover the same years. "Overall
    # Waterbody" is published up to 2019; from 2022 the headline the Catchment
    # Data Explorer shows is the ecological status. Take the overall figure
    # where it exists and fall back to ecological, which is what the Agency's
    # own page leads with.
    overall = {}
    for r in rows:
        lvl = f(r, "Classification Level")
        item = f(r, "Classification Item")
        year, status = f(r, "Year"), f(r, "Status")
        if lvl == "Overall Waterbody":
            overall[year] = status
        elif (lvl == "Ecological, chemical or quantitative status"
              and item.lower().startswith("ecological")
              and year not in overall):
            overall[year] = status

    latest = max((y for y in overall), default=None)
    elements = {}
    for r in rows:
        if f(r, "Year") == "2022" and f(r, "Classification Level") == "Element":
            elements[f(r, "Classification Item")] = f(r, "Status")
    return overall, elements, latest


def reasons():
    """Every RNAG row for the water body, deduplicated."""
    page = get(f"{BASE}/{WATERBODY}", os.path.join(CACHE, f"wfd_{WATERBODY}.html"))
    els = sorted({int(m) for m in re.findall(r"rnag\?cycle=3&amp;element=(\d+)", page)})
    seen, out = set(), []
    for el in els:
        raw = get(f"{BASE}/{WATERBODY}/rnag?cycle=3&element={el}",
                  os.path.join(CACHE, f"wfd_rnag_{el}.html"))
        body = re.sub(r"<(script|style).*?</\1>", "", raw, flags=re.S)
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
            cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                     for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
            cells = [c for c in cells if c]
            if len(cells) < 9 or cells[0] == "ID":
                continue
            rid = cells[0]
            if rid in seen:
                continue
            seen.add(rid)
            out.append({
                "id": rid, "source": cells[1], "sourceCertainty": cells[2],
                "activity": cells[3], "activityCertainty": cells[4],
                "category": cells[5], "categoryCertainty": cells[6],
                "sector": cells[7], "element": cells[8],
            })
    return out


def main():
    os.makedirs(CACHE, exist_ok=True)
    overall, elements, latest = classifications()
    rnag = reasons()

    sewage = [r for r in rnag if "sewage" in r["activity"].lower()]
    confirmed = [r for r in sewage if r["activityCertainty"].lower() == "confirmed"]

    out = {
        "waterbody": WATERBODY,
        "name": NAME,
        "url": f"{BASE}/{WATERBODY}",
        "statusByYear": overall,
        "latestYear": latest,
        "latestStatus": overall.get(latest),
        "elements2022": elements,
        "failingElements": sorted(k for k, v in elements.items()
                                  if v in ("Poor", "Bad", "Moderate", "Fail")),
        "reasons": rnag,
        "sewageReasons": sewage,
        "confirmedSewageReasons": confirmed,
        "intermittent": [r for r in sewage if "intermittent" in r["activity"].lower()],
        "updated": "Catchment Data Explorer, latest data (updated 17 March 2025)",
    }
    dest = os.path.join(HERE, "data", "wfd.json")
    json.dump(out, open(dest, "w"), indent=1)

    print(f"wrote {dest}\n{NAME}\n")
    for y in sorted(overall):
        print("   %s  %s" % (y, overall[y]))
    print("\n2022 elements not at Good or better:")
    for k in out["failingElements"]:
        print("   %-46s %s" % (k[:46], elements[k]))
    print(f"\nreasons for not achieving good: {len(rnag)}")
    by = collections.Counter((r["activity"], r["activityCertainty"]) for r in rnag)
    for (a, c), n in by.most_common():
        mark = "  <-- storm overflows" if "intermittent" in a.lower() else ""
        print("   %-44s %-10s %d%s" % (a[:44], c, n, mark))


if __name__ == "__main__":
    main()
