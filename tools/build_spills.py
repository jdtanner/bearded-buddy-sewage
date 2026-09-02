#!/usr/bin/env python3
"""Build data/spills.json: individual discharges, and which began on a dry day.

Two sources, both run once a year rather than daily, because both are annual
publications that do not change once out:

  * Severn Trent's detailed EDM return (start and stop of every discharge),
    from the EA's "Event Duration Monitoring - Storm Overflow - Start/Stop
    Detailed Data" dataset on data.gov.uk. Published from 2024 onwards only.
    Before 2024 there is no public per-discharge data for these outfalls, so
    no dry-day test is possible for those years and the page must say so.

  * Daily rainfall from Environment Agency rain gauges - see rainfall.py, which
    explains why real gauges rather than a gridded model, and why several of
    them rather than the nearest one.

The dry-day test is the Environment Agency's own, quoted verbatim in their
August 2024 post: "A dry day spill is when a storm overflow is used on a 'dry
day' - which is defined as no rainfall above 0.25mm on that day and the
preceding 24 hours."

A dry-day spill is not proof of anything. The EA treat one as a potential
breach until investigated, and allow that large catchments can legitimately
drain down long after the rain stopped. The page says "potential breach", never
"illegal".

Every flagged discharge records how many gauges agreed, so a marginal call is
visible as a marginal call rather than hidden inside a single number.
"""

import csv
import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rainfall  # noqa: E402
import xlsx  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, ".cache")

DETAIL = ("https://environment.data.gov.uk/api/file/download"
          "?fileDataSetId=c95ecc47-fa70-4a24-b8cc-098232987526")
FILES = {
    2024: "Severn Trent 2024 Detailed EDM Data.xlsx",
    2025: "Severn Trent 2025 Detailed EDM Data.csv",
}

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


def sweep(rain, all_events, thresholds=(0.0, 0.1, 0.2, 0.25, 0.3, 0.4, 0.5,
                                       0.75, 1.0, 1.5, 2.0, 3.0)):
    """How the count moves as the threshold moves.

    The obvious objection to any threshold is that it was chosen to give a
    convenient answer. This shows what every other choice would have given, so
    the reader can see the count is flat across a wide band around the
    Environment Agency's 0.25 mm rather than balanced on it.
    """
    out = []
    for th in thresholds:
        hits = [(uid, day, hours) for uid, day, hours in all_events
                if is_dry_at(rain, day, th)]
        out.append({
            "threshold": th,
            "spills": len(hits),
            "hours": round(sum(h for _, _, h in hits), 2),
        })
    return out


def is_dry_at(rain, day, threshold):
    """The EA test at an arbitrary threshold, same agreement rule."""
    prev = (datetime.date.fromisoformat(day)
            - datetime.timedelta(days=1)).isoformat()
    yes = total = 0
    for g in rain.values():
        a, b = g.get(day), g.get(prev)
        if a is None or b is None:
            continue
        total += 1
        if a <= threshold and b <= threshold:
            yes += 1
    return bool(total) and yes / total >= rainfall.AGREEMENT


def near_misses(rain, all_events, lo=0.25, hi=1.0):
    """Discharges that would count at `hi` but do not at `lo`.

    Worth publishing because every one of them so far fails on the day BEFORE
    the discharge rather than the day of it, which is a real thing about the
    test rather than a quirk of the data.
    """
    out = []
    for uid, day, hours in all_events:
        if is_dry_at(rain, day, lo) or not is_dry_at(rain, day, hi):
            continue
        prev = (datetime.date.fromisoformat(day)
                - datetime.timedelta(days=1)).isoformat()
        gauges = {n: [g.get(day), g.get(prev)] for n, g in rain.items()}
        day_vals = [v[0] for v in gauges.values() if v[0] is not None]
        prev_vals = [v[1] for v in gauges.values() if v[1] is not None]
        out.append({
            "id": uid, "name": NAMES[uid], "day": day, "hours": round(hours, 2),
            "maxOnDay": max(day_vals) if day_vals else None,
            "maxDayBefore": max(prev_vals) if prev_vals else None,
            "failsOn": "the day before" if (day_vals and max(day_vals) <= lo)
                       else "both days",
            "gauges": gauges,
        })
    out.sort(key=lambda r: -r["hours"])
    return out


def annual_rain(rain):
    """Mean annual rainfall across the gauges, for the wet-year comparison.

    Only counts a gauge for a year when it reported on more than 330 days, so a
    gauge that was down for a season cannot drag a year's mean down and make a
    wet year look dry.
    """
    out = {}
    for year in range(2020, 2026):
        y = str(year)
        totals = [sum(v for k, v in d.items() if k.startswith(y))
                  for d in rain.values()
                  if sum(1 for k in d if k.startswith(y)) > 330]
        if totals:
            out[y] = round(sum(totals) / len(totals))
    return out


def main():
    os.makedirs(CACHE, exist_ok=True)
    years = sorted(FILES)
    # One day of margin: a discharge on 1 January is tested against 31 December,
    # which is in the previous year.
    print("Rain gauges:")
    # Reaches back to 2020 so the page can set rainfall against discharge for
    # every year of the annual return, not just the two with per-discharge data.
    rain = rainfall.series("2019-12-28", f"{years[-1]}-12-31", CACHE)
    if not rain:
        raise SystemExit("no rainfall data; refusing to publish an untested result")

    def prev_of(day):
        return (datetime.date.fromisoformat(day)
                - datetime.timedelta(days=1)).isoformat()

    out = {
        "threshold_mm": rainfall.THRESHOLD_MM,
        "agreement": rainfall.AGREEMENT,
        "gauges": [{"name": n, "km": km} for n, _, km in rainfall.GAUGES
                   if n in rain],
        "years": {},
        "dry_spills": [],
        "rainfall_source": "Environment Agency rain gauges, daily totals",
        "annual_rain": annual_rain(rain),
        # Every daily reading behind the dry-day test, across all gauges. The
        # page quotes it, so it has to come from the data rather than a comment.
        "readings": sum(len(v) for v in rain.values()),
    }
    untested = 0
    all_events = []
    for year in years:
        per = {uid: {"events": 0, "hours": 0.0, "dry": 0, "dry_hours": 0.0}
               for uid in NAMES}
        for uid, start, stop in events(year):
            hours = (stop - start).total_seconds() / 3600
            day = start.date().isoformat()
            prev = prev_of(day)
            p = per[uid]
            p["events"] += 1
            p["hours"] += hours
            all_events.append((uid, day, hours))

            verdict = rainfall.is_dry(rain, day, prev)
            if verdict is None:
                untested += 1
                continue
            if not verdict:
                continue
            yes, total = rainfall.dry_vote(rain, day, prev)
            p["dry"] += 1
            p["dry_hours"] += hours
            out["dry_spills"].append({
                "id": uid, "name": NAMES[uid], "start": start.isoformat(),
                "hours": round(hours, 2), "year": year,
                "gauges_dry": yes, "gauges_total": total,
                "rain": {n: [rain[n].get(day), rain[n].get(prev)] for n in rain},
            })
        for p in per.values():
            p["hours"] = round(p["hours"], 2)
            p["dry_hours"] = round(p["dry_hours"], 2)
        out["years"][str(year)] = per

    out["sweep"] = sweep(rain, all_events)
    out["near_misses"] = near_misses(rain, all_events)

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

    print("\nThreshold sweep - how the count moves if the threshold moves:")
    for r in out["sweep"]:
        mark = "  <- the EA's test" if r["threshold"] == rainfall.THRESHOLD_MM else ""
        print("   <= %4.2f mm  %3d spills %7.1f h%s"
              % (r["threshold"], r["spills"], r["hours"], mark))
    if out["near_misses"]:
        print("\nNear misses (would count at 1.0 mm, do not at %.2f):"
              % rainfall.THRESHOLD_MM)
        for r in out["near_misses"]:
            print("   %s  %-28s %5.2f h   fails on %s"
                  % (r["day"], r["name"], r["hours"], r["failsOn"]))

    print("\nDry-day discharges (EA test: <=%.2f mm that day and the day before,"
          "\nagreed by at least %.0f%% of gauges):"
          % (rainfall.THRESHOLD_MM, 100 * rainfall.AGREEMENT))
    for d in out["dry_spills"]:
        print("   %s  %-28s %5.2f h   %d of %d gauges dry"
              % (d["start"][:16], d["name"], d["hours"],
                 d["gauges_dry"], d["gauges_total"]))


if __name__ == "__main__":
    main()
