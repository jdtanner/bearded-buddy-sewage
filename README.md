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

## What it costs

Nothing, and on the Free plan it cannot: going over a limit there returns 429s,
it does not generate a bill. Paid usage would only start on the $5/month Workers
plan, and this site would use a rounding error of what that includes.

The binding constraint is KV **writes**, capped at 1,000 a day on Free. Measured
against the 219 discharges actually recorded in 2026:

| | writes/day | of the limit |
|---|---|---|
| Heartbeat, every day regardless | 48 | 5% |
| Typical day (about 1 discharge) | 51 | 5% |
| Busiest day of 2026 so far (17) | 99 | 10% |
| An absurd day (60 discharges) | 228 | 23% |
| Ceiling if every single poll changed something | 576 | 58% |

Everything else is far away from its limit: 288 cron invocations and 576 KV
reads a day, against 100,000 of each. A year of stored events is 11 KB against
1 GB, so a decade is still a rounding error.

**Page traffic is free.** Static assets served through the assets binding are
free and unlimited on every plan. Only `/api/parish` invokes the Worker, and it
is edge-cached for five minutes, so even a page that gets shared widely adds very
little. It would take roughly 100,000 uncached visits in a day to reach the
Workers request limit.

Two things that would change the picture:

- **More parishes.** The daily KV limits are almost certainly per account rather
  than per namespace — the docs do not say outright — so budget on the account
  total. At about 100 writes a day each, eight or so parishes would still fit;
  beyond that, either lengthen the cron or move to the $5 plan.
- **A churning field in the feed.** The stored status deliberately holds only
  `status`, `since`, `start` and `end`. `LastUpdated` is fetched but not stored,
  because it changes on every poll and storing it would turn every one of the 288
  daily runs into a write. Do not add it.

## The wider catchment

The page states that 66 monitored Severn Trent storm overflows discharge into the
Erewash, Bailey Brook and their tributaries, six of them in the parish, and that
31 of the rest are upstream. Counted from the live feed by receiving watercourse:

    where=UPPER(ReceivingWaterCourse) LIKE '%EREWASH%'
       OR UPPER(ReceivingWaterCourse) LIKE '%BAILEY BROOK%'

Upstream is geometric, not hydrological: north of the parish on the Erewash,
which runs roughly north-south here, and west of Lee Lane on Bailey Brook, which
joins the Erewash at Langley Mill. Good enough for the claim being made, and the
page says so. It counts monitored storm overflows only, so it is a floor - not
unmonitored assets, not other companies, not agricultural or highway runoff.

Worth re-running if the argument ever leans harder on it, since the receiving
water names in the feed are free text: RIVER EREWASH, TRIB OF RIVER EREWASH,
TRIBUTARY OF THE RIVER EREWASH and River Erewash all appear as separate spellings.

## Discharges that are not storm overflows

`tools/build_consents.py` reads the EA's public register, Consented Discharges to
Controlled Waters with Conditions, and clips it to the parish. Nine permitted
discharge points across seven permits, and two of them appear nowhere else on
this site:

- **Milnhay works final/treated effluent**, permit T/61/45098/R. Continuous,
  properly permitted, not a spill, and no hours are counted for it anywhere
  because it is not meant to stop. The storm-tank hours sit on top of it.
- **Cornwood Meadows industrial site pumping station**, permit T/61/09188/O,
  discharging sewage to the Erewash inside the parish. It appears in **no** EDM
  annual return for 2021-2025. Unmonitored, so no figure exists for it.

The rest are the CSOs already covered, plus one private septic tank discharging
to ground through a soakaway. **The permit holder is a private individual and is
not named on the site or in the published data** - bundle.py deliberately passes
through only counts and effluent types.

Two things checked before believing any of it. A "Cornwood Pumping Station" does
appear in the return, with spill hours - it is South West Water's, in Devon, on
the River Yealm, and nothing to do with ours. And Lee Lane's permitted discharge
point falls a few metres outside the boundary while its monitor is inside; it is
counted as ours throughout, and the page says so.

This is the only script needing the virtualenv. The register ships as a Microsoft
Access database and grid references need a real projection:

    python3 -m venv .venv && .venv/bin/pip install access-parser pyproj
    .venv/bin/python tools/build_consents.py

The National Grid converter is checked against Milnhay works, whose grid
reference SK4572046380 must come back as 53.01278, -1.32000. An earlier version
had the northing 800 km out and put the parish in Shetland.

## The state of the river

`tools/build_wfd.py` reads the Environment Agency's Catchment Data Explorer for
water body **GB104028052511**, "Erewash from Nethergreen Brook to Gilt Brook" -
the reach beside the village, which takes Milnhay works.

Status: **Moderate** 2013-15, **Poor** from 2016 and every assessment since. In
2022 four elements are below good: phosphate and macrophytes Poor, invertebrates
and dissolved oxygen Moderate.

The valuable half is RNAG - Reasons for Not Achieving Good. The Agency records
each pressure with a certainty of Confirmed, Probable or Suspected. Of the twenty
reasons listed, **two are Confirmed and both are sewage**: "Sewage discharge
(intermittent)", which is their term for a storm overflow, and "Sewage discharge
(continuous)". Farming and urban run-off appear only as Probable.

The page tables the Confirmed ones only. Probable and Suspected are in the JSON
and one click away on the Agency's own site, but the argument should rest on what
the regulator has actually concluded.

Two traps. The classification CSV has a BOM stuck to its first column name, so
read it with a fallback. And the two status series do not cover the same years -
"Overall Waterbody" stops at 2019, and from 2022 the headline is the ecological
status, which is what the Agency's own page leads with. Take the overall figure
where it exists and fall back to ecological, or the site will claim the newest
assessment is 2019.

## What the water actually measures

`tools/build_river.py` pulls the Environment Agency's own sample results for two
points, from the Water Quality Archive:

- **MD-45691150**, Bailey Brook at Milnhay Road, in the parish, a few hundred
  metres below the Lee Lane outfall.
- **MD-45217250**, the Erewash at Shipley Gate, the first point below the parish.

Bailey Brook's ammonia averaged **0.098 mg/l** every year from 2015 to 2021. It
was **0.65 in 2022** (peak 3.50) and **0.81 in 2025** (peak 2.60) - seven and
eight times its own baseline. Dissolved oxygen at the same point hit its record
low in 2025. Ammonia up while oxygen falls is what sewage does to a watercourse.

Stated carefully on the page: these are monthly spot samples, a peak is one
morning, and no particular discharge is blamed for any particular reading.

**MD-45217950, the Erewash immediately upstream of Milnhay works, has recorded
nothing since 2015.** That is the point that would let anyone compare the river
above and below the works. Its absence is Part C of the enquiry letter.

API notes in NOTES-water-quality.md. The one that costs time: `limit` caps at 250
and truncates silently, so query one determinand at a time or you will get four
years of pH and conclude there is no ammonia data.

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

### What 0.25 mm actually is

Worth knowing because it sounds arbitrary and turns out not to be. Every one of
the 13,164 daily readings behind this page is an exact multiple of **0.2 mm** —
these are tipping buckets, and below 1.2 mm the only values that exist are 0.0,
0.2, 0.4, 0.6, 0.8, 1.0.

So the Agency's threshold sits in the gap between one tip and two: a dry day is a
day the gauge tipped once or not at all. That is also why the sweep below is flat
across a band — there are no readings inside the gap for a moved threshold to
land on.

In physical terms 0.25 mm is a quarter of a litre over a square metre, for a
whole day: a tenth of an ordinary wet day here (median 2.6 mm), and one part in
three thousand of the 816 mm this parish gets in a year.

### Is 0.25 mm a convenient threshold?

`build_spills.py` sweeps it, and the page publishes the sweep, because it is the
obvious objection. The count is **flat at 2 from 0.20 mm through to 0.50 mm** —
it sits on a plateau either side of the EA's figure rather than balanced on it —
and only starts climbing at 1.0 mm (7 discharges, 14.6 h), which is not a dry day
by any reading.

The five discharges between those two lines are published as near misses, because
of *how* they fail. On four of the five the day of the discharge was itself dry
by the EA's measure; what rules them out is a trace on the day before. The
biggest is 19 February 2024, when the gauges recorded at most 0.2 mm and Milnhay
works discharged three times for 11.3 hours in total.

Excluding them is right — the preceding 24 hours are in the test because
catchments drain down — but it is the sort of thing that should be shown rather
than quietly dropped.

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

- The repo is public at github.com/jdtanner/bearded-buddy-sewage, and the page
  links to it. **Nothing personal may be committed to it.** `build_consents.py`
  redacts private permit holders as it reads them, because the EA register gives
  a person's name and the grid reference of their home for every private septic
  tank. An earlier version wrote those to `data/consents.json`; that file and the
  git history were both scrubbed before the first push.
- **If the candidacy ever goes back on**, the imprint has to go back with it.
  UK digital campaign material for a candidate legally requires a promoter's name
  and address (Elections Act 2022). Both the candidacy line and the imprint were
  removed together, deliberately: as it stands this is a public-interest page
  about published data, not election material, and it needs no imprint. Put back
  one without the other and that stops being true.
- The page used to claim "the code that produces these figures is open". It is
  not: this repo has no remote. The claim is removed. Put it back if and when the
  repo is public, and it is worth doing, because it is the strongest answer to
  anyone who says the numbers are made up.
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
