#!/usr/bin/env python3
"""Build data/spills.json: individual discharges, and which began on a dry day.

Two sources, both run once a year rather than daily, because both are annual
publications that do not change once out:

  * Severn Trent's detailed EDM return (start and stop of every discharge),
    from the EA's "Event Duration Monitoring - Storm Overflow - Start/Stop
    Detailed Data" dataset on data.gov.uk. Published from 2024 onwards only.
    Before 2024 there is no public per-discharge data for these outfalls, so
    no dry-day test is possible for those years and the page must say so.

  * Daily rainfall from Open-Meteo's historical archive, at the parish rather
    than at a gauge. The nearest Environment Agency rain gauges are 5.5 km and
    5.9 km away, and the EA's live API only retains about a month of readings,
    so it cannot answer a question about last year at all.

The dry-day test is the Environment Agency's own, quoted verbatim in their
August 2024 post: "A dry day spill is when a storm overflow is used on a 'dry
day' - which is defined as no rainfall above 0.25mm on that day and the
preceding 24 hours."

A dry-day spill is not proof of anything. The EA treat one as a potential
breach until investigated, and allow that large catchments can legitimately
drain down long after the rain stopped. The page says "potential breach", never
"illegal".
"""

import csv
import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xlsx  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, ".cache")

DETAIL = ("https://environment.data.gov.uk/api/file/download"
          "?fileDataSetId=c95ecc47-fa70-4a24-b8cc-098232987526")
FILES = {
    2024: "Severn Trent 2024 Detailed EDM Data.xlsx",
    2025: "Severn Trent 2025 Detailed EDM Data.csv",
}

# Centre of the parish. Open-Meteo is gridded, so this is the cell the rainfall
# comes from; the parish is about 5 km across, well inside one cell.
LAT, LON = 53.0246, -1.3300
THRESHOLD_MM = 0.25

NAMES = {
    "SVT01315": "Cromford Road",
    "SVT00684": "Cromford Road No 3",
    "SVT01317": "Station Road",
    "SVT01316": "Milnhay Road",
    "SVT01338": "Lee Lane",
    "SVT01570": "Milnhay works (overflow)",
    "SVT01571": "Milnhay works (storm tank)",
}


def fetch(url, dest, args=()):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest
    print(f"  fetching {os.path.basename(dest)} ...", flush=True)
    subprocess.run(["curl", "-sL", "--max-time", "900", "-o", dest, "--get", url,
                    *args], check=True)
    return dest


def rainfall(start, end):
    """Daily precipitation, mm, keyed by ISO date."""
    dest = os.path.join(CACHE, f"rain_{start}_{end}.json")
    if not os.path.exists(dest):
        url = ("https://archive-api.open-meteo.com/v1/archive"
               f"?latitude={LAT}&longitude={LON}&start_date={start}&end_date={end}"
               "&daily=precipitation_sum&timezone=UTC")
        fetch(url, dest)
    d = json.load(open(dest))["daily"]
    return {day: v for day, v in zip(d["time"], d["precipitation_sum"]) if v is not None}


def events(year):
    """Yield (uid, start datetime, stop datetime) for our outfalls."""
    name = FILES[year]
    dest = os.path.join(CACHE, name)
    fetch(DETAIL, dest, ["--data-urlencode", f"fileName={name}"])

    def parse(a, b):
        return (datetime.datetime.fromisoformat(a.replace("Z", "+00:00")),
                datetime.datetime.fromisoformat(b.replace("Z", "+00:00")))

    if dest.endswith(".csv"):
        with open(dest, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if r["Unique ID"] in NAMES and r["Discharge Start (GMT)"] and \
                        r["Discharge Stop (GMT)"]:
                    yield (r["Unique ID"],
                           *parse(r["Discharge Start (GMT)"], r["Discharge Stop (GMT)"]))
    else:
        seen_header = False
        for r in xlsx.rows(dest):
            if not seen_header:
                seen_header = (r.get("A") == "Unique ID")
                continue
            if r.get("A") in NAMES and r.get("C") and r.get("D"):
                yield (r["A"], *parse(r["C"], r["D"]))


def main():
    os.makedirs(CACHE, exist_ok=True)
    years = sorted(FILES)
    # One day of margin either side: a spill on 1 January is tested against
    # 31 December, which is in the previous year's series.
    rain = rainfall(f"{years[0] - 1}-12-30", f"{years[-1]}-12-31")

    def dry(day):
        prev = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
        if day not in rain or prev not in rain:
            return None
        return rain[day] <= THRESHOLD_MM and rain[prev] <= THRESHOLD_MM

    out = {"threshold_mm": THRESHOLD_MM, "years": {}, "dry_spills": [],
           "rainfall_source": "Open-Meteo historical archive, daily total at "
                              f"{LAT},{LON}"}
    untested = 0
    for year in years:
        per = {uid: {"events": 0, "hours": 0.0, "dry": 0, "dry_hours": 0.0}
               for uid in NAMES}
        for uid, start, stop in events(year):
            hours = (stop - start).total_seconds() / 3600
            day = start.date().isoformat()
            p = per[uid]
            p["events"] += 1
            p["hours"] += hours
            d = dry(day)
            if d is None:
                untested += 1
            elif d:
                p["dry"] += 1
                p["dry_hours"] += hours
                prev = (start.date() - datetime.timedelta(days=1)).isoformat()
                out["dry_spills"].append({
                    "id": uid, "name": NAMES[uid], "start": start.isoformat(),
                    "hours": round(hours, 2), "rain_day": rain[day],
                    "rain_prev": rain[prev], "year": year,
                })
        for p in per.values():
            p["hours"] = round(p["hours"], 2)
            p["dry_hours"] = round(p["dry_hours"], 2)
        out["years"][str(year)] = per

    dest = os.path.join(HERE, "data", "spills.json")
    json.dump(out, open(dest, "w"), indent=1)
    print(f"\nwrote {dest}")
    if untested:
        print(f"  {untested} discharges had no rainfall data and were not tested")

    for year in years:
        per = out["years"][str(year)]
        ev = sum(p["events"] for p in per.values())
        hr = sum(p["hours"] for p in per.values())
        dr = sum(p["dry"] for p in per.values())
        print(f"\n{year}: {ev} discharges, {hr:.1f} hours, {dr} began on a dry day")
        for uid, name in NAMES.items():
            p = per[uid]
            if p["events"]:
                print("   %-28s %4d discharges %7.1f h  dry: %d"
                      % (name, p["events"], p["hours"], p["dry"]))
    if out["dry_spills"]:
        print("\nDry-day discharges (EA test: <=%.2f mm that day and the day before):"
              % THRESHOLD_MM)
        for d in out["dry_spills"]:
            print("   %s  %-28s %5.2f h   rain %.2f / %.2f mm"
                  % (d["start"][:16], d["name"], d["hours"], d["rain_day"], d["rain_prev"]))


if __name__ == "__main__":
    main()
