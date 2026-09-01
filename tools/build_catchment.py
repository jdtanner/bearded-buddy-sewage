#!/usr/bin/env python3
"""Build data/catchment.json: which outfalls drain through this parish.

The first version of this sorted outfalls by latitude, on the reasoning that the
Erewash runs north to south. That is roughly true and gave roughly the right
answer, but it cannot tell a tributary from the main river, and it swept in a
Bailey Brook in Shropshire that happens to share a name with ours.

This does it properly, from two authoritative pieces:

  * Every outfall in the EA's annual return carries a WFD waterbody id - the
    Agency's own hydrological segmentation of the river. The Erewash is cut into
    three reaches whose names give the order outright: source to Nethergreen
    Brook, Nethergreen Brook to Gilt Brook, Gilt Brook to Trent. Tributary
    catchments are named as such.

  * The river geometry itself, from OpenStreetMap. Waterway ways are drawn in
    the direction of flow, so they chain head to tail into one ordered line from
    source to mouth. That gives every point on the river a distance downstream,
    including the points where the parish boundary runs along it.

An outfall is upstream when its water enters the river above the point where the
river enters the parish. For the main river that is a comparison of distances
along it. For Bailey Brook and Nethergreen Brook, which flow into the parish
before meeting the Erewash, an outfall on them outside the parish is upstream by
construction.

    ./tools/build_catchment.py

One caveat kept in the output: OpenStreetMap maps only the last 0.9 km of Bailey
Brook under that name; above Heanor it is unnamed or culverted. So Bailey Brook
outfalls are placed by the parish polygon rather than by distance along the brook.
Every one of them turns out to be west of the parish, in Codnor, Loscoe and
Heanor, which is unambiguously upstream.
"""

import glob
import json
import math
import os
import re
import subprocess
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xlsx  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, ".cache")

LIVE = ("https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/"
        "Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0/query")
OVERPASS = "https://overpass-api.de/api/interpreter"

# The Environment Agency's reaches. Order is given by the names themselves.
MAINSTEM = {
    "GB104028052740": "Erewash from Source to Nethergreen Brook",
    "GB104028052511": "Erewash from Nethergreen Brook to Gilt Brook",
    "GB104028052480": "Erewash from Gilt Brook to Trent",
}
# Tributaries that reach the parish before joining the Erewash.
TRIBS_ABOVE = {
    "GB104028052590": "Bailey Brook",
    "GB104028052620": "Nethergreen Brook",
}
# Joins the Erewash well below the parish.
TRIBS_BELOW = {"GB104028052520": "Nut Brook"}

OURS = {"SVT01571", "SVT00684", "SVT01317", "SVT01316",
        "SVT01338", "SVT01315", "SVT01570"}


def metres(a, b):
    (la1, lo1), (la2, lo2) = a, b
    x = math.radians(lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2))
    y = math.radians(la2 - la1)
    return math.hypot(x, y) * 6371000


def fetch(url, dest, post=None):
    if os.path.exists(dest) and os.path.getsize(dest) > 500:
        return dest
    cmd = ["curl", "-sL", "--max-time", "300", "-o", dest]
    if post:
        cmd += ["-X", "POST", "-d", post, url]
    else:
        cmd += [url]
    subprocess.run(cmd, check=True)
    return dest


def river_network():
    """The Erewash, chained downstream, as [(lat, lon)] with cumulative metres."""
    q = ('[out:json][timeout:180];(way["waterway"~"^(river|stream)$"]'
         '["name"~"Erewash",i](52.85,-1.52,53.20,-1.15););(._;>;);out body;')
    d = json.load(open(fetch(OVERPASS, os.path.join(CACHE, "osm_erewash.json"), post=q)))
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in d["elements"] if e["type"] == "node"}
    ways = [e for e in d["elements"] if e["type"] == "way"
            and (e.get("tags", {}).get("name") or "") in ("River Erewash", "Erewash")]

    by_start = collections.defaultdict(list)
    starts, ends = set(), set()
    for w in ways:
        by_start[w["nodes"][0]].append(w)
        starts.add(w["nodes"][0])
        ends.add(w["nodes"][-1])

    best = []
    for head in (starts - ends):          # a source: nobody flows into it
        seq, cur, seen = [], head, set()
        while cur in by_start and cur not in seen:
            seen.add(cur)
            w = by_start[cur][0]
            seq += w["nodes"] if not seq else w["nodes"][1:]
            cur = w["nodes"][-1]
        if len(seq) > len(best):
            best = seq

    pts = [nodes[n] for n in best if n in nodes]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + metres(a, b))
    return pts, cum


def along(pt, pts, cum):
    """Distance downstream of the nearest point on the river, and how far off it."""
    best_i, best_d = 0, float("inf")
    for i, p in enumerate(pts):
        d = metres(pt, p)
        if d < best_d:
            best_i, best_d = i, d
    return cum[best_i] / 1000, best_d


def in_parish(la, lo, ring):
    c = False
    for i in range(len(ring) - 1):
        y1, x1 = ring[i]
        y2, x2 = ring[i + 1]
        if (y1 > la) != (y2 > la) and lo < x1 + (la - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def outfalls():
    """Every Severn Trent outfall in this catchment, from the annual return."""
    wb = set(MAINSTEM) | set(TRIBS_ABOVE) | set(TRIBS_BELOW)
    books = glob.glob(os.path.join(CACHE, "ar2025", "**",
                                   "*all water and sewerage companies.xlsx"), recursive=True)
    if not books:
        raise SystemExit("run tools/build_history.py --download first")
    seen_header, out = False, []
    for r in xlsx.rows(books[0]):
        if not seen_header:
            seen_header = (r.get("A") or "").strip() == "Unique ID"
            continue
        if r.get("J") in wb and (r.get("B") or "").startswith("Severn"):
            out.append({"id": r.get("A"), "site": r.get("C"),
                        "wb": r.get("J"), "catchment": r.get("K")})
    return out


def coords(ids):
    """Coordinates for the given outfall ids only.

    Not a fetch-everything-and-filter: Severn Trent have more than 2,000
    monitored outfalls and the service caps a response at 2,000, silently, with
    exceededTransferLimit set. Asking for exactly what we need, in batches,
    avoids quietly losing the ones that fall off the end - which it did, and
    which moved the headline count by two.
    """
    import urllib.parse
    out = {}
    ids = sorted(ids)
    for i in range(0, len(ids), 60):
        batch = ids[i:i + 60]
        where = "Id IN (%s)" % ",".join("'%s'" % x for x in batch)
        q = "?" + urllib.parse.urlencode({
            "where": where, "outFields": "Id,Latitude,Longitude",
            "returnGeometry": "false", "f": "json"})
        dest = os.path.join(CACHE, "live_batch_%02d.json" % (i // 60))
        d = json.load(open(fetch(LIVE + q, dest)))
        if d.get("exceededTransferLimit"):
            raise SystemExit("batch %d hit the transfer limit; make batches smaller" % i)
        for f in d.get("features", []):
            out[f["attributes"]["Id"]] = f["attributes"]
    return out


def main():
    os.makedirs(CACHE, exist_ok=True)
    pts, cum = river_network()
    ring = json.load(open(os.path.join(HERE, "data", "boundary.json")))

    # Where the parish sits on the river: the stretch of boundary that actually
    # runs along the channel, within 60 m of it.
    on = [along((la, lo), pts, cum)[0] for la, lo in ring
          if along((la, lo), pts, cum)[1] < 60]
    top, bottom = min(on), max(on)

    assets = outfalls()
    live = coords([o["id"] for o in assets])
    counts = collections.Counter()
    where = collections.defaultdict(list)
    excluded = collections.Counter()

    for o in assets:
        a = live.get(o["id"])
        if not a or a.get("Latitude") is None:
            excluded["not in the live feed"] += 1
            continue
        la, lo = a["Latitude"], a["Longitude"]
        if in_parish(la, lo, ring):
            k = "inside"
        elif o["wb"] in MAINSTEM:
            k = "upstream" if along((la, lo), pts, cum)[0] < top else "below"
        elif o["wb"] in TRIBS_ABOVE:
            k = "upstream"
        else:
            k = "below"
        counts[k] += 1
        where[k].append({"id": o["id"], "site": o["site"],
                         "catchment": o["catchment"], "ours": o["id"] in OURS})

    by_water = collections.Counter(x["catchment"] for x in where["upstream"])
    out = {
        "river": "River Erewash",
        "riverLengthKm": round(cum[-1] / 1000, 1),
        "parishFromKm": round(top, 1),
        "parishToKm": round(bottom, 1),
        "parishFrontageKm": round(bottom - top, 1),
        "upstream": counts["upstream"],
        "inside": counts["inside"],
        "below": counts["below"],
        "total": sum(counts.values()),
        "upstreamByWater": dict(by_water),
        "excluded": dict(excluded),
        "method": ("EA WFD waterbody per outfall, positioned along the river "
                   "network from OpenStreetMap"),
    }
    dest = os.path.join(HERE, "data", "catchment.json")
    json.dump(out, open(dest, "w"), indent=1)

    print(f"wrote {dest}\n")
    print("Erewash: %.1f km source to Trent" % out["riverLengthKm"])
    print("parish occupies %.1f - %.1f km (%.1f km of frontage)\n"
          % (top, bottom, bottom - top))
    print("  upstream, drains through the parish : %d" % counts["upstream"])
    print("  inside the parish                   : %d" % counts["inside"])
    print("  enters at or below                  : %d" % counts["below"])
    print("\nupstream by watercourse:")
    for k, v in by_water.most_common():
        print("   %-52s %d" % ((k or "?")[:52], v))
    for k, v in excluded.items():
        print("  excluded: %s %d" % (k, v))


if __name__ == "__main__":
    main()
