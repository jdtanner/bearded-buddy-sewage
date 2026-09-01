# bearded-buddy-sewage

Sewage discharges from the seven Severn Trent storm overflows inside the parish
of Aldercar and Langley Mill, at **sewage.beardedbuddy.com**.

A Cloudflare Worker that serves a static page from `public/` and one JSON
endpoint. No framework, no build step for the page itself. Plain HTML, one
stylesheet copied from the walks site so the two read as one hand, and Leaflet
vendored locally.

## Publishing

```
npx wrangler kv namespace create DATA        # first time only, paste the id into wrangler.jsonc
npx wrangler deploy
```

A git push deploys **nothing**. Only `wrangler deploy` does, and it ships
`public/` with it.

`sewage.beardedbuddy.com` is a Worker custom domain on a zone registered with
Cloudflare Registrar, so `wrangler deploy` creates the DNS record and
provisions the certificate. Do not add a manual DNS record, and do not add the
domain in the dashboard — that is what the walks site needs because it is Pages,
and this is not.

Local: `npx wrangler dev`. For the page on its own without the API,
`python3 -m http.server 8811` from `public/` works, and the live-status figure
degrades to a dash.

## Where the numbers come from

Nothing is calculated in the browser. `public/data/parish.json` is built on this
machine and committed; the Worker only adds live status on top.

| | source | how often |
|---|---|---|
| Spill hours and counts, 2020–2025 | EA [EDM Storm Overflow Annual Return](https://www.data.gov.uk/dataset/19f6064d-7356-466f-844e-d20ea10ae9fd/event-duration-monitoring-storm-overflows-annual-returns) | once a year, late March |
| Every individual discharge, 2024– | EA [EDM Start/Stop Detailed Data](https://www.data.gov.uk/dataset/event-duration-monitoring-storm-overflow-start-stop-detailed-data) | once a year |
| Historic rainfall | EA hydrology API, six rain gauges | once a year |
| The year in progress | the Worker's own record of the live feed | every 5 minutes |
| Live status, recent rainfall | Severn Trent ArcGIS feed, Open-Meteo forecast | every 5 minutes |

The daily cron still uses Open-Meteo for the *recent* rainfall behind the live
indicator, because it is fast and the live figure is indicative. Nothing
published as a finding depends on it.

To rebuild the historic figures after the EA publishes a new year:

```
npm run data          # build_history.py, then build_spills.py, then bundle.py
```

Add the new year to `YEARS` in `tools/build_history.py` and to `FILES` in
`tools/build_spills.py` first. Downloads are cached in `.cache/`, which is
gitignored; pass `--download` to refetch.

## The year in progress, and why this site keeps its own record

The EA return for a year lands around the following March, so for fifteen months
the newest official figure is out of date. The Worker fills that gap itself.

Severn Trent's live feed reports only the **latest** event per outfall. It cannot
be asked what happened in March, so the only way to have a running total is to
watch it and write down what it says. The cron does that every five minutes and
keeps the result in KV under `events:<year>`. Nothing about the current year
depends on anyone else's archive.

Five minutes is not about being live. Anything that starts and finishes between
two polls is lost for good, and plenty of these discharges last twenty minutes.

**Keys.** An event is stored as `"<id>|<end minute>" -> [start ms, end ms]`. Keyed
on the end rather than the start because the company revises the reported start
while a discharge is running, so one discharge otherwise becomes several. Rounded
to the minute because it revises the seconds too — the same discharge has been
seen ending at :23 and then :41 one poll later.

**Writes are conditional.** The cron runs 288 times a day; it writes only when
something changed, plus a heartbeat every 30 minutes so "last checked" stays
honest. A quiet day costs about 50 writes.

`GET /api/events?year=2026` dumps everything recorded, so the numbers can be
checked and the record exported if it ever needs rebuilding elsewhere.

### The one-time seed

The Worker cannot remember a year that began before it was deployed. Severn Trent
publish a per-year EDM feature service but only after the year ends (`STW_Edm_2025`
exists, `STW_Edm_2026` does not), and the EA return is a year further off still.
For the already-elapsed months of the current year there is exactly one public
record: Top of the Poops, who poll the same feed and keep the history.

`tools/seed_events.py` reads that **once** and writes it into KV in the Worker's
own format. That is the entire extent of the dependency and it ends there. Delete
the script once the EA has published the return for that year.

Two traps it has to handle, both of which silently double-count:

- **Top of the Poops displays British local time**, the feed and the EA returns
  are UTC. In summer that is an hour out, which does not change a duration but
  does change which day a discharge falls on and stops a seeded event matching
  the same event seen live.
- **That page shows minutes; the feed reports seconds.** Hence the minute-rounded
  key.

Checked after seeding: 219 events and 606 hours from the seed, still 219 and 606
after repeated live polls, with no near-duplicate pairs an hour apart.

**Do not seed a year the EA has already published.** Top of the Poops only began
polling these outfalls on 15 November 2025, so the same method over 2025 returns
231 hours against an official 700. Over December 2025, the first month both cover
in full, it gives 136.5 against an official 130.3 — about 5% over.

## Things that will bite you

**The annual return changes shape every year.** Only 2024 and 2025 have a
`Unique ID` column, so outfalls are matched on EA permit reference instead.
Milnhay works has two separately permitted assets sharing one permit, split by
asset type. Column letters move, so `build_history.py` maps columns by reading
the header text, never by position.

**The duration column changes units.** Up to 2023 it is headed `(hrs)` and holds
hours. From 2024 it is headed `(hh:mm:ss)` and holds an Excel day fraction that
needs multiplying by 24. Getting this wrong understates everything 24-fold and
looks entirely plausible. The header text decides.

**"Counted spills" is not the number of discharges.** The EA groups discharges
within 12 hours into one spill, then one more per 24 hours. Cromford Road No 3
recorded 106 discharges in 2025 and reports 63 spills. We publish the EA's
number because it is the one in the official return; the page says so.

**Not reported is not zero.** Where an outfall filed no figure, the table shows
`n/r`. A missing monitor is not a clean river, and rendering it as 0 would flatter
the company.

**Use the gauges, not a weather model.** The first version of this used
Open-Meteo's gridded archive for historic rainfall. That was wrong, and worth
recording: it ran about 9% wetter than the gauges over 2024-25, and at the
0.25 mm threshold the dry-day test uses, that difference decides the answer. It
reported one dry-day discharge where the gauges report two. Two Open-Meteo
models disagreed by a factor of 3.6 on one of the dates that mattered.

Historic rainfall now comes from the EA **hydrology** API, which keeps decades of
daily gauge totals. Do not confuse it with the EA **flood-monitoring** API, which
keeps about a month and cannot answer a question about last year. Flood-monitoring
also returned 503 on two requests out of three during development, which is why
nothing the page renders depends on a live fetch.

**One gauge is not enough.** The nearest is 5.7 km away, and the two nearest
disagree about whether a given day was dry roughly one day in twelve. Over
2024-25 the wettest of the six gauges recorded 1,878 mm and the driest 1,429 mm.
`rainfall.py` polls six and requires 75% agreement; every flagged discharge
records how many gauges agreed, so a marginal call stays visible as one.

## The dry-day test

`tools/build_spills.py` applies the Environment Agency's published definition:
no rainfall above 0.25 mm on the day of the discharge or the day before.

Across 2024 and 2025 — the only two years with per-discharge data — two of 693
discharges met it, totalling one hour:

- Milnhay works storm tank, 8 November 2024, 25 minutes. All six gauges dry.
- Cromford Road No 3, 2 July 2025, 35 minutes. Five of six; the sixth had 0.2 mm.

Two more candidates were tested and rejected: 19 February 2024 (three discharges
at Milnhay totalling 11.3 hours) was dry at only one gauge of six, and 27 August
2025 at only two of six. Both are excluded. The 19 February one matters most,
because it is by far the longest, and a single-gauge method would have published
it.

The EA treats a dry-day spill as a **potential** permit breach until it has been
investigated, and allows that a large catchment can still be draining down long
after rain stops. The page says "dry-day spill" and "potential permit breach",
never "illegal". Keep it that way. Overstating one 25-minute event would hand
Severn Trent an easy way to discredit the 7,464 hours that are not in dispute.

## Cross-checks worth keeping

Hours derived from the individual discharge records match the annual return
exactly for both 2024 (1,118.8 h) and 2025 (699.7 h), from two separately
published files. If a change breaks that agreement, something is wrong.

`tools/build_history.py` should always find 7 outfalls for 2021 onwards and 5
for 2020. Fewer means the matching has broken, and it will fail quietly by
showing a lower total rather than by throwing.

The two gaps in the table are real and explained, not missing data:

- **2020** has five outfalls because both Milnhay monitors were installed in
  2021 ("Data start - calendar year" in the return).
- **2025** has six because the Milnhay works inlet overflow was decommissioned
  that January — the return says "no longer operational as an overflow, permit
  revoked or to be revoked" and "no longer spilling to environment". That is a
  genuine improvement and the page says so.

Also in that row, and worth keeping in the argument: Severn Trent give the cause
of the storm tank's spill frequency as "hydraulic capacity", with UWWTR and Storm
Overflow Discharge Reduction Plan investigations ongoing.

## Before it goes public

- Fill in the imprint in the footer of `public/index.html` — `[NAME]` and
  `[ADDRESS]`. Campaign material for a candidate needs a promoter's name and
  address.
- Replace the three `.ph` photograph slots in the "Where it ends up" section
  with real `<img>` tags.
- Add `public/assets/img/og-card.png` at 1200×630 — the meta tags already point
  at it.
- Check the complaint links still resolve, particularly the MP.
- The page deliberately does **not** claim sewage reaches the canal. The pump
  house at Langley Mill Basin back-pumps water from the Erewash *Canal* below
  Langley Bridge Lock into the basin above it; the basin is fed from the
  Nottingham Canal feeder off Moorgreen reservoir, not from the river. River and
  canal run side by side here and are very easy to conflate. Do not add that
  claim back without a source.
- Bump `?v=` on the CSS and JS in `index.html` whenever you edit them.
