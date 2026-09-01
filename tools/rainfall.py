"""Daily rainfall from Environment Agency rain gauges around the parish.

Not Open-Meteo. The first version of this used Open-Meteo's gridded archive,
which was a mistake worth recording: it is a model, its cell is far wider than
the parish, it ran about 9% wetter than the gauges over 2024-25, and at the
0.25 mm threshold the Environment Agency's dry-day test uses, that difference
decides the answer. Two Open-Meteo models disagreed by a factor of 3.6 on one
of the dates that mattered.

These are real tipping-bucket gauges, from the EA's hydrology API, which keeps
decades of daily totals. (The EA's *other* API, flood-monitoring, keeps only
about a month and cannot answer a question about last year at all.)

No single gauge speaks for the parish either: the nearest is 5.7 km away, and
the two nearest disagree about whether a given day was dry about 8% of the time.
So we ask several and report how many agreed. A discharge is only called a
dry-day discharge when a clear majority of gauges say both days were dry.
"""

import json
import os
import time
import urllib.request

READINGS = "https://environment.data.gov.uk/hydrology/data/readings.json"

# Gauges within about 15 km, nearest first, with their distance from the parish
# centre. Found via:
#   /hydrology/id/stations?observedProperty=rainfall&lat=53.0246&long=-1.33&dist=20
GAUGES = [
    ("Watnall",           "c1ab3bd4-e22a-4ad3-8255-d4ea642ab735", 5.7),
    ("Denby Pottery",     "0e887352-6b58-4884-a07e-51ac32e85428", 5.8),
    ("Newstead Abbey",    "76824692-1513-46ec-b3de-da8c75fa189a", 11.0),
    ("Sutton-in-Ashfield", "cc9824a3-f516-49e7-8cea-56d72fb0c9dd", 13.2),
    ("Ogston",            "63e4ac73-d70e-435e-8eb9-4f2bbf8c3ece", 14.0),
    ("Draycott",          "3df464fe-cd1a-4adb-bd6d-9abcc1d1be77", 14.2),
]

THRESHOLD_MM = 0.25          # the EA's dry-day threshold
AGREEMENT = 0.75             # fraction of gauges that must agree to call it dry


def _get(url, tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as fh:
                return json.load(fh)
        except Exception as exc:
            if i == tries - 1:
                print(f"    gave up: {type(exc).__name__}")
                return None
            time.sleep(min(2 ** i, 20))
    return None


def daily(station, start, end, cache_dir):
    """{'YYYY-MM-DD': mm} of daily totals for one gauge."""
    path = os.path.join(cache_dir, f"gauge_{station}_{start}_{end}.json")
    if os.path.exists(path):
        return json.load(open(path))
    url = (f"{READINGS}?measure={station}-rainfall-t-86400-mm-qualified"
           f"&min-date={start}&max-date={end}&_limit=20000")
    d = _get(url)
    out = {}
    if d:
        for r in d.get("items", []):
            if r.get("value") is not None:
                out[r["date"]] = r["value"]
        json.dump(out, open(path, "w"))
    return out


def series(start, end, cache_dir):
    """Load every gauge. Returns {name: {date: mm}}."""
    os.makedirs(cache_dir, exist_ok=True)
    out = {}
    for name, station, km in GAUGES:
        d = daily(station, start, end, cache_dir)
        if d:
            out[name] = d
            print(f"  {name} ({km} km): {len(d)} days, {sum(d.values()):.0f} mm")
        else:
            print(f"  {name} ({km} km): FAILED, skipped")
    return out


def dry_vote(rain, day, prev_day):
    """How many gauges call this a dry day, and how many could answer.

    The EA test: no rainfall above 0.25 mm on the day or the preceding 24 hours.
    """
    yes = total = 0
    for name, d in rain.items():
        a, b = d.get(day), d.get(prev_day)
        if a is None or b is None:
            continue
        total += 1
        if a <= THRESHOLD_MM and b <= THRESHOLD_MM:
            yes += 1
    return yes, total


def is_dry(rain, day, prev_day):
    """True only when a clear majority of gauges agree both days were dry."""
    yes, total = dry_vote(rain, day, prev_day)
    if total == 0:
        return None
    return yes / total >= AGREEMENT
