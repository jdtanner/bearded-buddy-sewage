#!/usr/bin/env python3
"""Cut Top of the Poops live asset data by a parish boundary.

Usage:  ./cut_by_parish.py <boundary.kml|.geojson> [out-prefix]

Reads the polygon, queries top-of-the-poops.org's live asset API for the
polygon's bounding box, then keeps only the assets falling inside the polygon.
Writes <prefix>.json, <prefix>.geojson and <prefix>.csv.
"""
import csv
import json
import re
import sys
import urllib.request

API = "https://top-of-the-poops.org/live/stream/assets/{n},{e}/{s},{w}"


def load_rings(path):
    """Return a list of rings, each a closed list of (lon, lat)."""
    text = open(path).read()
    if path.lower().endswith(".kml"):
        blocks = re.findall(r"<coordinates>(.*?)</coordinates>", text, re.S)
        rings = []
        for b in blocks:
            ring = [tuple(float(v) for v in p.split(",")[:2]) for p in b.split()]
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            rings.append(ring)
        return rings

    geo = json.loads(text)
    geoms = []
    if geo.get("type") == "FeatureCollection":
        geoms = [f["geometry"] for f in geo["features"]]
    elif geo.get("type") == "Feature":
        geoms = [geo["geometry"]]
    else:
        geoms = [geo]

    rings = []
    for g in geoms:
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            ring = [tuple(c[:2]) for c in poly[0]]  # outer ring only
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            rings.append(ring)
    return rings


def inside(lon, lat, ring):
    """Ray casting point-in-polygon."""
    c = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > lat) != (y2 > lat):
            if lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                c = not c
    return c


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else "assets"

    rings = load_rings(path)
    pts = [p for r in rings for p in r]
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    pad = 0.005  # small margin so the bbox query can't clip the edge
    url = API.format(n=max(lats) + pad, e=max(lons) + pad,
                     s=min(lats) - pad, w=min(lons) - pad)

    with urllib.request.urlopen(url) as fh:
        assets = json.load(fh)

    rows = []
    for a in assets:
        lat, lon = a["loc"]["lat"], a["loc"]["lon"]
        if any(inside(lon, lat, r) for r in rings):
            rows.append({
                "id": a["id"]["id"],
                "siteName": a["siteName"],
                "receivingWater": a.get("receivingWater"),
                "company": a["company"]["name"],
                "constituency": a["constituency"]["name"],
                "lat": lat,
                "lon": lon,
                "url": "https://top-of-the-poops.org" + a["id"]["uri"],
            })
    rows.sort(key=lambda r: (r["siteName"], r["id"]))

    json.dump(rows, open(prefix + ".json", "w"), indent=2)

    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
         "properties": {k: v for k, v in r.items() if k not in ("lat", "lon")}}
        for r in rows]}
    json.dump(fc, open(prefix + ".geojson", "w"), indent=2)

    with open(prefix + ".csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"{len(assets)} assets in bbox -> {len(rows)} inside boundary")
    print(f"wrote {prefix}.json, {prefix}.geojson, {prefix}.csv")


if __name__ == "__main__":
    main()
