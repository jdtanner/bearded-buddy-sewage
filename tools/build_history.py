#!/usr/bin/env python3
"""Build data/history.json: per-outfall spill count and hours, per year.

Source is the Environment Agency's EDM Storm Overflow Annual Return, one zip
per year on data.gov.uk. Run once a year when the EA publishes the new return
(usually late March). Not part of the Worker's daily job: a return for a closed
year does not change.

    ./tools/build_history.py [--download]

Three things make this fiddly, and all three are handled by reading the header
row rather than trusting column positions:

  * The layout changes every year. Only 2024 and 2025 carry a "Unique ID"
    column, so outfalls are matched on EA permit reference instead, which is
    present in every year. Milnhay works has two monitored assets sharing one
    permit, so the asset type disambiguates them.

  * The duration units change. Up to 2023 the column is headed "(hrs)" and
    holds hours. From 2024 it is headed "(hh:mm:ss)" and holds an Excel day
    fraction, which needs multiplying by 24. Getting this wrong silently
    understates the figures 24-fold, so the header text decides, and the
    result is range-checked against the hours in a year.

  * "Counted spills" is not the number of discharges. The EA groups a block of
    discharges within 12 hours into one spill, then one more per 24 hours, so
    the 106 discharges recorded at Cromford Road No 3 in 2025 are reported as
    63 spills. We publish the EA's number because that is what is in the
    official return and what the company is measured against.
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xlsx  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEARS = range(2020, 2026)
URL = ("https://environment.data.gov.uk/api/file/download"
       "?fileDataSetId=c55e170e-3c75-49a5-8026-a961ff94c8e0")

# Keyed by EA permit reference. Milnhay works has two assets on one permit,
# split by asset type; everything else is one asset per permit.
OUTFALLS = [
    ("SVT01315", "Cromford Road",              "T/61/21599/O", None),
    ("SVT00684", "Cromford Road No 3",         "T/61/12266/O", None),
    ("SVT01317", "Station Road",               "T/61/12267/O", None),
    ("SVT01316", "Milnhay Road",               "T/61/12268/O", None),
    ("SVT01338", "Lee Lane",                   "T/61/02160/O", None),
    ("SVT01570", "Milnhay works (overflow)",   "T/61/45098/R", "inlet"),
    ("SVT01571", "Milnhay works (storm tank)", "T/61/45098/R", "storm tank"),
]
BY_PERMIT = {}
for uid, name, permit, kind in OUTFALLS:
    BY_PERMIT.setdefault(permit, []).append((uid, name, kind))


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def column_map(row):
    """Map a role to a column letter by matching the header text."""
    want = {
        "permit":    lambda h: "permit ref" in h or h.startswith("permit no"),
        "site":      lambda h: h.startswith("site name"),
        "kind":      lambda h: "asset type" in h,
        "hours":     lambda h: "total duration" in h,
        "spills":    lambda h: "counted spills" in h,
        "reporting": lambda h: "edm operational" in h,
        "water":     lambda h: "receiving water" in h,
        "uid":       lambda h: h == "unique id",
    }
    out = {}
    for col, val in row.items():
        h = norm(val)
        for role, test in want.items():
            if role not in out and h and test(h):
                out[role] = col
    return out


def hours_are_day_fractions(header_text):
    """The header says which. 'hh:mm:ss' means an Excel day fraction."""
    h = norm(header_text)
    if "hh:mm" in h:
        return True
    if "(hrs)" in h or "(hours)" in h:
        return False
    return None  # unknown; caller falls back to a magnitude check


def download(cache):
    os.makedirs(cache, exist_ok=True)
    for y in YEARS:
        zp = os.path.join(cache, f"ar{y}.zip")
        if not (os.path.exists(zp) and os.path.getsize(zp) > 1000):
            print(f"  fetching {y} ...", flush=True)
            subprocess.run(
                ["curl", "-sL", "--max-time", "900", "-o", zp, "--get", URL,
                 "--data-urlencode",
                 f"fileName=EDM_{y}_Storm_Overflow_Annual_Return.zip"], check=True)
        subprocess.run(["unzip", "-o", "-q", zp, "-d", os.path.join(cache, f"ar{y}")],
                       check=True)


def workbooks(cache, year):
    """Candidate workbooks for a year, best first."""
    root, out = os.path.join(cache, f"ar{year}"), []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".xlsx") or f.startswith("~$"):
                continue
            low = f.lower()
            rank = 0 if "all water and sewerage" in low else 1 if "severn" in low else 3
            if "summary" in low:
                rank = 9
            out.append((rank, os.path.join(dirpath, f)))
    return [p for _, p in sorted(out)]


def scan(path, hist, meta, year):
    """Pull our outfalls out of one workbook. Returns how many were found."""
    found = 0
    for sheet_name, target in xlsx.sheets(path):
        cols, unit_hdr = None, None
        for r in xlsx.rows(path, target):
            if cols is None:
                m = column_map(r)
                if "permit" in m and "hours" in m and "spills" in m:
                    cols, unit_hdr = m, r.get(m["hours"])
                continue

            permit = (r.get(cols["permit"]) or "").strip()
            cands = BY_PERMIT.get(permit)
            if not cands:
                continue

            if len(cands) == 1:
                uid, name, _ = cands[0]
            else:
                kind = norm(r.get(cols.get("kind"))) if cols.get("kind") else ""
                site = norm(r.get(cols.get("site")))
                pick = [c for c in cands if c[2] and c[2] in (kind + " " + site)]
                if len(pick) != 1:
                    continue
                uid, name, _ = pick[0]

            raw, spills = num(r.get(cols["hours"])), num(r.get(cols["spills"]))
            frac = hours_are_day_fractions(unit_hdr)
            if raw is not None:
                if frac is None:
                    # Unlabelled: a year has 8760 hours, so anything under 366
                    # that also looks like a day fraction is one.
                    frac = raw < 366 and (spills or 0) > 0 and raw < 32
                hours = round(raw * 24, 2) if frac else round(raw, 2)
            else:
                hours = None

            hist[uid][str(year)] = {
                "hours": hours,
                "spills": int(spills) if spills is not None else None,
                "reporting": num(r.get(cols["reporting"])) if cols.get("reporting") else None,
            }
            meta.setdefault(uid, {
                "name": name, "permit": permit,
                "official": r.get(cols.get("site")) if cols.get("site") else name,
                "water": r.get(cols.get("water")) if cols.get("water") else None,
            })
            found += 1
        if found:
            return found
    return found


def main():
    cache = os.path.join(HERE, ".cache")
    if "--download" in sys.argv or not os.path.isdir(cache):
        download(cache)

    hist = {uid: {} for uid, *_ in OUTFALLS}
    meta = {}
    for y in YEARS:
        n = 0
        for wb in workbooks(cache, y):
            n = scan(wb, hist, meta, y)
            if n:
                print(f"{y}: {n}/{len(OUTFALLS)} outfalls  <- {os.path.basename(wb)}")
                break
        if not n:
            print(f"{y}: NOT FOUND")

    out = {
        "outfalls": [dict(id=uid, **meta.get(uid, {"name": name}))
                     for uid, name, *_ in OUTFALLS],
        "years": [str(y) for y in YEARS],
        "history": hist,
    }
    dest = os.path.join(HERE, "data", "history.json")
    json.dump(out, open(dest, "w"), indent=1)
    print(f"\nwrote {dest}\n")

    print("%-28s %s" % ("outfall", " ".join("%13d" % y for y in YEARS)))
    for uid, name, *_ in OUTFALLS:
        cells = []
        for y in YEARS:
            d = hist[uid].get(str(y))
            cells.append("        -    " if not d or d["hours"] is None
                         else "%3s sp %6.1fh" % (d["spills"], d["hours"]))
        print("%-28s %s" % (name, " ".join(cells)))
    print()
    for y in YEARS:
        ds = [d[str(y)] for d in hist.values() if d.get(str(y))]
        hrs = sum(d["hours"] or 0 for d in ds)
        sp = sum(d["spills"] or 0 for d in ds)
        print("  %d: %3d spills, %6.1f hours (%4.1f days)" % (y, sp, hrs, hrs / 24))


if __name__ == "__main__":
    main()
