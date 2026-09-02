#!/usr/bin/env python3
"""Build data/river.json: what the water in the parish actually measures.

The rest of the site counts what goes in. This is what comes out of a bottle.
The Environment Agency samples these waters roughly monthly and publishes every
result in the Water Quality Archive.

Two points matter here:

  * Bailey Brook at Milnhay Road - the parish's own brook, the one Lee Lane
    discharges into, sampled a few hundred metres downstream of it.
  * The Erewash at Shipley Gate - the first sampling point below the parish, so
    the closest measure of what leaves here.

The Erewash point upstream of Milnhay works exists (MD-45217950) and would make a
proper before-and-after pair, but it has no results at all since 2015. Worth
asking the Agency why, and worth re-checking: if it is ever reinstated it is the
single most useful point on this river.

Three determinands, chosen because they are the ones the WFD classification
fails on and the ones sewage moves:

  ammonia    0111  the sharpest signal of sewage in freshwater
  phosphate  0180  nutrient enrichment, feeds the algae
  oxygen     9924  what everything living in the river depends on

API notes are in NOTES-water-quality.md. The short version: the path is
/sampling-point, it refuses Accept: application/json, and limit caps at 250 -
which silently truncates, so query one determinand at a time.

    ./tools/build_river.py
"""

import collections
import json
import os
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, ".cache")
BASE = "https://environment.data.gov.uk/water-quality/sampling-point"

POINTS = {
    "MD-45691150": {
        "name": "Bailey Brook at Milnhay Road",
        "note": "In the parish. Lee Lane discharges into this brook.",
    },
    "MD-45217250": {
        "name": "River Erewash at Shipley Gate",
        "note": "The first sampling point below the parish.",
    },
}
DETERMINANDS = {
    "0111": {"key": "ammonia", "label": "Ammonia", "unit": "mg/l"},
    "0180": {"key": "phosphate", "label": "Phosphate", "unit": "mg/l"},
    "9924": {"key": "oxygen", "label": "Dissolved oxygen", "unit": "mg/l"},
}


def fetch(point, det):
    dest = os.path.join(CACHE, f"river_{point}_{det}.json")
    if not (os.path.exists(dest) and os.path.getsize(dest) > 200):
        url = (f"{BASE}/{point}/observation?determinand={det}"
               f"&dateFrom=2015-01-01&limit=250")
        subprocess.run(["curl", "-sL", "--max-time", "120", "-H",
                        "Accept: application/ld+json", "-o", dest, url], check=True)
    return json.load(open(dest)).get("member", [])


def by_year(rows):
    out = collections.defaultdict(list)
    for m in rows:
        raw = m.get("hasSimpleResult")
        try:
            # Results below the detection limit come through as "<0.03".
            v = float(str(raw).lstrip("<"))
        except (TypeError, ValueError):
            continue
        year = (m.get("phenomenonTime") or "")[:4]
        if year:
            out[year].append(v)
    return {y: {"n": len(v), "mean": round(statistics.mean(v), 3),
                "max": round(max(v), 2), "min": round(min(v), 3)}
            for y, v in sorted(out.items())}


def main():
    os.makedirs(CACHE, exist_ok=True)
    out = {"points": {}, "determinands": DETERMINANDS,
           "source": "Environment Agency Water Quality Archive"}

    for pt, meta in POINTS.items():
        series = {}
        for det, d in DETERMINANDS.items():
            rows = fetch(pt, det)
            if rows:
                series[d["key"]] = by_year(rows)
        out["points"][pt] = {**meta, "series": series}

        print(f"\n{meta['name']}  ({pt})")
        for key in ("ammonia", "phosphate", "oxygen"):
            if key not in series:
                print(f"   {key:<18} no results")
                continue
            yrs = sorted(series[key])
            recent = [y for y in yrs if y >= "2021"]
            print("   %-18s %s" % (key, "  ".join(
                "%s %.2f" % (y, series[key][y]["mean"]) for y in recent)))

    # The thing worth pointing at: ammonia in Bailey Brook against its own
    # baseline, rather than against a standard nobody can picture.
    bb = out["points"]["MD-45691150"]["series"].get("ammonia", {})
    base = [bb[y]["mean"] for y in bb if "2015" <= y <= "2021"]
    if base:
        baseline = round(statistics.mean(base), 3)
        out["baileyBaseline"] = baseline
        out["baileySpikes"] = {y: bb[y] for y in bb
                               if bb[y]["mean"] > baseline * 3}
        print(f"\nBailey Brook ammonia, 2015-2021 average: {baseline} mg/l")
        for y, v in out["baileySpikes"].items():
            print("   %s mean %.3f (%.0fx), peak %.2f"
                  % (y, v["mean"], v["mean"] / baseline, v["max"]))

    dest = os.path.join(HERE, "data", "river.json")
    json.dump(out, open(dest, "w"), indent=1)
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
