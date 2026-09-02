# Other discharge records — what exists, and one thing worth chasing

Notes from surveying what else is published beyond the storm-overflow figures the
site currently uses. Nothing here is on the page yet.

## 1. EA Water Quality Archive — the big one

API base `https://environment.data.gov.uk/water-quality`, spec at
`/openapi.json`. Two traps: the path is `/sampling-point`, **not**
`/id/sampling-point` (that 404s), and it refuses `Accept: application/json` —
you must ask for `application/ld+json` or `application/geo+json`. `limit` caps
at 250. Results come back under `member`, not `features` or `items`.

```
curl -H "Accept: application/ld+json" \
 "https://environment.data.gov.uk/water-quality/sampling-point?latitude=53.0246&longitude=-1.33&radius=6&limit=250"
```

**78 sampling points within 6 km.** The ones that matter:

| Point | What it is |
|---|---|
| MD-45217950 | River Erewash **upstream of Milnhay STW** |
| MD-45217250 | River Erewash at Shipley Gate (**downstream**) |
| MD-45217701 | Milnhay STW final effluent (non-tertiary) |
| MD-45217704 | Milnhay STW **settled storm sewage** |
| MD-45217707 | Milnhay STW UWWTD intake self-monitoring |
| MD-45691150 | Bailey Brook at Milnhay Road |
| MD-82531410 | **Erewash Canal**, Anchor Lane, Langley Mill |
| MD-45220980 / MD-45220500 | Erewash at Pyebridge / Jacksdale (upstream) |

Upstream and downstream of the works are both sampled, so a before-and-after
comparison across the parish is possible. Shipley Gate has 250 observations from
2023-01 to 2024-05 — pH, ammoniacal nitrogen, nitrate, conductivity, temperature.
The upstream point returned nothing after 2023, so check its date range before
building anything on the pair.

## 2. The find worth chasing: flow compliance at Milnhay

`MD-45217704` does not carry chemistry. It carries the **permit condition** — a
storm overflow may only spill once the works is passing forward its required flow
to treatment. Severn Trent report against it, and the EA publish it.

```
curl -H "Accept: application/ld+json" \
 "https://environment.data.gov.uk/water-quality/sampling-point/MD-45217704/observation?dateFrom=2020-01-01&limit=250"
```

| | 2023 | 2024 | **2025** |
|---|---|---|---|
| FPF readings ≥92% of limit when overflowing | 100% | 100% | **75%** |
| Consecutive days without good FPF data | 0 | 11 | **336** |
| Consecutive days without good overflow data | 0 | 8 | **350** |
| Days without both good FPF and overflow data | 0 | 10 | **341** |
| Duration of overflow operation (annual) | 1,054.7 h | 812.3 h | 43.1 h |
| Number of overflow operations | 3,115 | 2,623 | 19 |

Read that carefully before using it. In 2025 the flow monitoring at Milnhay
reported **no good data for 336 consecutive days** — most of the year — and when
it did work, compliance fell from 100% to 75%. The low 43.1 hours and 19
operations on this point are almost certainly an artefact of the instrument being
down, not of a quiet year: the EDM return for the same site and year says 305.5
hours across 38 spills.

This is closer to "was this discharge permitted" than the rainfall-based dry-day
test on the site, because it measures the actual condition in the permit rather
than a proxy for it. It is also the more serious finding, so it needs checking
properly before publication:

- Confirm the exact meaning of each determinand rather than inferring from the
  label. `/codelist/determinand` in the same API.
- Establish why two instruments at one works disagree so far on hours.
- Ask Severn Trent and the EA directly. This belongs with the Cornwood enquiry in
  `~/Documents/cornwood-enquiry.md` — same letter, same recipients.

## 3. Other categories in the consents register, already downloaded

From the 78 nearby sampling points, by type: 23 freshwater river, 7 non-water-
company treated sewage (private plants), 6 trade site drainage, 6 mineral
workings (opencast), 6 sediments, 6 water-company final effluent, 5 crude sewage
to further treatment, 4 STW storm overflow, 3 canals.

So besides Severn Trent there are private sewage plants, trade discharges and
former opencast sites draining into the same water. None of it is on the page.

## 4. Not yet looked at

- EA pollution incident records (category 1–3) for this stretch.
- WFD classification for waterbody GB104028052511 — the Erewash's ecological and
  chemical status, and the stated reasons for not achieving good. Catchment Data
  Explorer returned a 500 when tried; retry.
- Enforcement action register.
