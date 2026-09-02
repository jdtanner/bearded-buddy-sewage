#!/usr/bin/env python3
"""Build data/consents.json: every permitted discharge in the parish.

The rest of this site is about storm overflows, because that is what has an
Event Duration Monitor on it and therefore a published number of hours. It is
not the whole picture. A storm overflow is the thing that opens when it rains;
plenty of other things discharge into the same water all the time, with a permit,
and nobody counts the hours because they are not supposed to stop.

This reads the Environment Agency's public register - Consented Discharges to
Controlled Waters with Conditions, 71,000-odd active permits nationally - and
pulls out the ones inside the parish boundary.

Needs the virtualenv, unlike everything else here:

    python3 -m venv .venv && .venv/bin/pip install access-parser pyproj
    .venv/bin/python tools/build_consents.py

The register ships as a Microsoft Access database, which nothing in the standard
library will open, and grid references need a real projection to become
coordinates. Both dependencies are confined to this one script; the rest of the
tooling stays dependency-free.
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, ".cache")

URL = ("https://environment.data.gov.uk/api/file/download"
       "?fileDataSetId=a54fdea1-7769-4b22-a518-10d51fed6f33")
ZIP = os.path.join(CACHE, "consents.zip")

def _letter_index(c):
    """Position of a grid letter, with I skipped as the National Grid does."""
    v = ord(c) - ord("A")
    return v - 1 if v > 7 else v


def ngr_to_en(ref):
    """'SK4572046380' -> (easting, northing) in metres, or None.

    Checked against Milnhay works, whose grid reference in the annual return is
    SK4572046380 and whose coordinates in the live feed are 53.01278, -1.32000.
    """
    ref = (ref or "").strip().upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z]{2})(\d+)", ref)
    if not m:
        return None
    letters, digits = m.groups()
    if len(digits) % 2 or "I" in letters:
        return None
    l1, l2 = _letter_index(letters[0]), _letter_index(letters[1])
    e = (((l1 - 2) % 5) * 5 + (l2 % 5)) * 100000
    n = ((19 - 5 * (l1 // 5)) - (l2 // 5)) * 100000
    half = len(digits) // 2
    scale = 10 ** (5 - half)
    return e + int(digits[:half]) * scale, n + int(digits[half:]) * scale


def in_ring(la, lo, ring):
    c = False
    for i in range(len(ring) - 1):
        y1, x1 = ring[i]
        y2, x2 = ring[i + 1]
        if (y1 > la) != (y2 > la) and lo < x1 + (la - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def main():
    from access_parser import AccessParser
    from pyproj import Transformer

    os.makedirs(CACHE, exist_ok=True)
    if not (os.path.exists(ZIP) and os.path.getsize(ZIP) > 1_000_000):
        print("  downloading the public register (~57 MB) ...", flush=True)
        subprocess.run(["curl", "-sL", "--max-time", "900", "-o", ZIP, "--get", URL,
                        "--data-urlencode",
                        "fileName=Consented Discharges to Controlled Waters "
                        "with Conditions.zip"], check=True)
    db_dir = os.path.join(CACHE, "consents")
    if not os.path.isdir(db_dir):
        subprocess.run(["unzip", "-o", "-q", ZIP, "-d", db_dir], check=True)
    accdb = [os.path.join(db_dir, f) for f in os.listdir(db_dir) if f.endswith(".accdb")][0]

    ring = json.load(open(os.path.join(HERE, "data", "boundary.json")))
    lats = [p[0] for p in ring]
    lons = [p[1] for p in ring]
    to_en = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    to_ll = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    e0, n0 = to_en.transform(min(lons), min(lats))
    e1, n1 = to_en.transform(max(lons), max(lats))
    pad = 500
    e0, e1, n0, n1 = e0 - pad, e1 + pad, n0 - pad, n1 + pad

    print("  reading the register ...", flush=True)
    t = AccessParser(accdb).parse_table("consents_active")
    cols = list(t.keys())
    rows = len(t[cols[0]])
    print(f"  {rows:,} active permits nationally", flush=True)

    def col(name, i):
        v = t.get(name, [None] * rows)[i]
        return v.strip() if isinstance(v, str) else v

    found = []
    for i in range(rows):
        # Cheap grid-square filter before the expensive projection.
        en = ngr_to_en(col("EFFLUENT_GRID_REF", i) or col("DISCHARGE_NGR", i))
        if not en or not (e0 <= en[0] <= e1 and n0 <= en[1] <= n1):
            continue
        lo, la = to_ll.transform(en[0], en[1])
        if not in_ring(la, lo, ring):
            continue
        # Most permits here are Severn Trent's. A handful are private: a
        # household or a small business with its own treatment plant. Their
        # holder name is a person's name and the grid reference is their home,
        # so neither is written to disk. They are counted, not identified.
        holder = col("COMPANY_NAME", i) or ""
        company = holder.upper().endswith(("LIMITED", "LTD", "PLC"))
        found.append({
            "permit": col("PERMIT_NUMBER", i) if company else "private",
            "holder": holder if company else "a private permit holder",
            "site": col("DISCHARGE_SITE_NAME", i) if company else "private discharge",
            "siteType": col("DSI_TYPE_DESCRIPTION", i),
            "effluent": col("EFF_TYPE_DESCRIPTION", i),
            "outlet": col("OUTLET_TYPE_DESCRIPTION", i),
            "receiving": col("RECEIVING_WATER", i),
            "environment": col("REC_ENV_CODE_DESCRIPTION", i),
            # Coordinates only for water-company assets: a private one would
            # locate somebody's house.
            "lat": round(la, 6) if company else None,
            "lon": round(lo, 6) if company else None,
        })

    # One permit can carry several outlets and effluent streams, so the same
    # discharge point appears more than once. Count points, not rows.
    points = {}
    for n, f in enumerate(found):
        points.setdefault((f["permit"], f["lat"], f["lon"], f["permit"] == "private" and n),
                          f)
    out = {
        "permits": len({f["permit"] for f in found}),
        "points": len(points),
        "rows": len(found),
        "discharges": sorted(points.values(), key=lambda f: (f["holder"] or "", f["site"] or "")),
        "source": "Environment Agency public register, Consented Discharges to "
                  "Controlled Waters with Conditions",
    }
    dest = os.path.join(HERE, "data", "consents.json")
    json.dump(out, open(dest, "w"), indent=1)

    print(f"\nwrote {dest}")
    print(f"{out['points']} permitted discharge points inside the parish, "
          f"across {out['permits']} permits\n")
    import collections
    for label, key in (("by holder", "holder"), ("by what is discharged", "effluent")):
        print(f"  {label}:")
        for k, n in collections.Counter(
                (d[key] or "?") for d in points.values()).most_common(12):
            print("     %-58s %d" % (str(k)[:58], n))
        print()


if __name__ == "__main__":
    main()
