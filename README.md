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
| Historic rainfall | Open-Meteo archive, at the parish | once a year |
| Live status, recent rainfall | Severn Trent ArcGIS feed, Open-Meteo forecast | daily cron |

To rebuild the historic figures after the EA publishes a new year:

```
npm run data          # build_history.py, then build_spills.py, then bundle.py
```

Add the new year to `YEARS` in `tools/build_history.py` and to `FILES` in
`tools/build_spills.py` first. Downloads are cached in `.cache/`, which is
gitignored; pass `--download` to refetch.

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

**The Environment Agency's own rainfall API cannot answer this question.** It
keeps roughly a month of readings, and the nearest gauges are 5.5 km and 5.9 km
away. Historic rainfall comes from Open-Meteo instead, at the parish. During
development the EA API returned 503 on two requests out of three, which is why
nothing the page renders depends on a live fetch.

## The dry-day test

`tools/build_spills.py` applies the Environment Agency's published definition:
no rainfall above 0.25 mm on the day of the discharge or the day before.

Across 2024 and 2025 — the only two years with per-discharge data — exactly one
of 693 discharges met it: Milnhay works storm tank, 8 November 2024, 25 minutes.

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

## Before it goes public

- Fill in the imprint in the footer of `public/index.html` — `[NAME]` and
  `[ADDRESS]`. Campaign material for a candidate needs a promoter's name and
  address.
- Replace the three `.ph` photograph slots in the "Where it ends up" section
  with real `<img>` tags.
- Add `public/assets/img/og-card.png` at 1200×630 — the meta tags already point
  at it.
- Check the complaint links still resolve, particularly the MP.
- Bump `?v=` on the CSS and JS in `index.html` whenever you edit them.
