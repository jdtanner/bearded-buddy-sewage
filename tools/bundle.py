#!/usr/bin/env python3
"""Merge the built data into public/data/parish.json, the one file the page reads.

Run after build_history.py and build_spills.py. Keeping the arithmetic here
rather than in the browser means the headline figures are computed once, are
the same for every visitor, and can be checked by reading this file.

    ./tools/bundle.py
"""

import json
import os
import shutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "public", "data")


# Permits that appear in the EDM annual return, so have published spill hours.
# Everything else on the public register discharges here uncounted.
MONITORED_PERMITS = {
    "T/61/21599/O", "T/61/12266/O", "T/61/12267/O",
    "T/61/12268/O", "T/61/02160/O", "T/61/45098/R",
}


def load(name):
    return json.load(open(os.path.join(D, name)))


def main():
    outfalls = load("outfalls.json")
    hist = load("history.json")
    spills = load("spills.json")
    try:
        current = load("current.json")
    except FileNotFoundError:
        current = None
    try:
        catchment = load("catchment.json")
    except FileNotFoundError:
        catchment = None
    try:
        consents = load("consents.json")
    except FileNotFoundError:
        consents = None
    try:
        wfd = load("wfd.json")
    except FileNotFoundError:
        wfd = None
    try:
        river = load("river.json")
    except FileNotFoundError:
        river = None

    by_svt = {o["id"]: o for o in hist["outfalls"]}
    years = hist["years"]

    # Attach the geography from the Top of the Poops clip to the figures from
    # the annual return, joined on the SVT id.
    merged = []
    for h in hist["outfalls"]:
        geo = next((o for o in outfalls if o["svt"] == h["id"]), None)
        if geo is None:
            # Milnhay works (overflow) is SVE1000 in the live feed and has no
            # SVT id there, but does have one in the annual return.
            geo = next((o for o in outfalls if o["name"] == h["name"]), {})
        rows = hist["history"].get(h["id"], {})
        total_h = sum((rows.get(y) or {}).get("hours") or 0 for y in years)
        total_s = sum((rows.get(y) or {}).get("spills") or 0 for y in years)
        merged.append({
            "id": h["id"],
            "sve": geo.get("sve"),
            "name": h["name"],
            "official": h.get("official") or geo.get("official"),
            "permit": h.get("permit"),
            "lat": geo.get("lat"),
            "lon": geo.get("lon"),
            "water": (geo.get("water") or h.get("water") or "").strip(),
            "kind": geo.get("kind", "Combined sewer overflow"),
            "years": rows,
            "totalHours": round(total_h, 1),
            "totalSpills": total_s,
        })
    merged.sort(key=lambda o: -o["totalHours"])

    per_year = {}
    for y in years:
        rows = [(o["years"].get(y) or {}) for o in merged]
        reported = [r for r in rows if r.get("hours") is not None]
        per_year[y] = {
            "hours": round(sum(r["hours"] for r in reported), 1),
            "spills": sum(r.get("spills") or 0 for r in reported),
            # How many of the seven actually filed a figure that year. Where
            # this is under seven the total is an undercount, not a low year.
            "reporting": len(reported),
            "of": len(merged),
        }

    tested = sorted(spills["years"])
    dry_total = sum(
        sum(p["dry"] for p in spills["years"][y].values()) for y in tested)

    bundle = {
        "parish": "Aldercar and Langley Mill",
        "company": "Severn Trent Water",
        "years": years,
        "outfalls": merged,
        "perYear": per_year,
        "totals": {
            "hours": round(sum(v["hours"] for v in per_year.values()), 1),
            "spills": sum(v["spills"] for v in per_year.values()),
            "days": round(sum(v["hours"] for v in per_year.values()) / 24, 1),
            "from": years[0],
            "to": years[-1],
        },
        "dry": {
            "threshold_mm": spills["threshold_mm"],
            "agreement": spills["agreement"],
            "gauges": spills["gauges"],
            "yearsTested": tested,
            "count": dry_total,
            "spills": spills["dry_spills"],
            "rainfallSource": spills["rainfall_source"],
            "sweep": spills.get("sweep"),
            "nearMisses": spills.get("near_misses"),
            # Total discharges the test was actually applied to, so the page can
            # say "2 of 693" rather than a bare 2.
            "tested": sum(p["events"] for y in tested
                          for p in spills["years"][y].values()),
        },
        "rain": spills["annual_rain"],
        # The year in progress, from the live feed. Provisional, and kept out of
        # "totals" on purpose: those are the official returns only.
        "current": current,
        "catchment": catchment,
        "wfd": wfd,
        "river": river,
        # The EA public register: every permitted discharge here, not only the
        # ones with a monitor on them. Individual permit holders are not
        # published - one is a private septic tank and is nobody's business.
        "consents": None if not consents else {
            "points": consents["points"],
            "permits": consents["permits"],
            "byEffluent": sorted({d["effluent"] for d in consents["discharges"] if d["effluent"]}),
            # Locations, for the map. Water-company permits only: the one private
            # permit here is a septic tank discharging to ground rather than to
            # the river, and plotting it would identify a private household.
            "sites": [
                {
                    "permit": d["permit"],
                    "site": (d["site"] or "").title(),
                    "effluent": d["effluent"],
                    "receiving": d["receiving"],
                    "lat": d["lat"], "lon": d["lon"],
                    # Does it have an Event Duration Monitor reporting hours?
                    "monitored": d["permit"] in MONITORED_PERMITS,
                }
                for d in consents["discharges"]
                if "LIMITED" in (d["holder"] or "").upper()
            ],
        },
        "sources": {
            "annualReturn": "https://www.data.gov.uk/dataset/19f6064d-7356-466f-844e-d20ea10ae9fd/event-duration-monitoring-storm-overflows-annual-returns",
            "detailed": "https://www.data.gov.uk/dataset/event-duration-monitoring-storm-overflow-start-stop-detailed-data",
            "live": "https://www.streamwaterdata.co.uk/datasets/stwmaps::severn-trent-water-storm-overflow-activity/about",
            "rainfall": "https://environment.data.gov.uk/hydrology/landing",
            "boundary": "Aldercar and Langley Mill parish boundary, council boundary record 58602",
            "dryDayDefinition": "https://environmentagency.blog.gov.uk/2024/08/28/what-are-dry-day-spills",
        },
    }

    os.makedirs(OUT, exist_ok=True)
    json.dump(bundle, open(os.path.join(OUT, "parish.json"), "w"),
              separators=(",", ":"))
    shutil.copy(os.path.join(D, "boundary.json"), os.path.join(OUT, "boundary.json"))
    for stale in ("history.json", "outfalls.json", "spills.json"):
        p = os.path.join(OUT, stale)
        if os.path.exists(p):
            os.remove(p)

    t = bundle["totals"]
    print(f"wrote {OUT}/parish.json")
    print(f"\n{t['from']}-{t['to']}: {t['spills']} spills, {t['hours']:.0f} hours "
          f"= {t['days']:.0f} days")
    print(f"dry-day spills: {dry_total} (tested {', '.join(tested)})\n")
    for y in years:
        v = per_year[y]
        flag = "" if v["reporting"] == v["of"] else f"   <- only {v['reporting']}/{v['of']} reported"
        print("  %s %4d spills %7.1f h%s" % (y, v["spills"], v["hours"], flag))
    print()
    for o in merged:
        print("  %-28s %5d spills %7.1f h  %s" %
              (o["name"], o["totalSpills"], o["totalHours"], o["water"]))


if __name__ == "__main__":
    main()
