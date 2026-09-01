/**
 * sewage.beardedbuddy.com
 *
 * Serves the page from ./public, and keeps its own record of every discharge.
 *
 * Severn Trent's live feed reports only the *latest* event per outfall. It
 * cannot be asked what happened in March, so anyone wanting a running total for
 * the current year has to watch the feed and write down what it says. This
 * Worker does that on a five-minute cron and keeps the result in KV, so the
 * page depends on nobody else's archive.
 *
 * The authority for a finished year is still the Environment Agency's annual
 * return, which is built into public/data/parish.json. What is collected here
 * covers the gap between a year ending and its return being published, roughly
 * fifteen months later, and is always labelled provisional.
 *
 * Nothing the page renders depends on an upstream fetch succeeding: the cron
 * writes to KV, the page reads KV, and a failed poll leaves the last good value
 * in place.
 */

const STATUS_KEY = "parish:status";
const eventsKey = (year) => `events:${year}`;

// The seven monitored assets in the parish, by Environment Agency id.
// SVT01570, the inlet overflow at Milnhay works, is deliberately absent: it was
// decommissioned in January 2025 and no longer appears in the feed at all.
const OUTFALLS = {
  SVT01571: "Milnhay works (storm tank)",
  SVT00684: "Cromford Road No 3",
  SVT01317: "Station Road",
  SVT01316: "Milnhay Road",
  SVT01338: "Lee Lane",
  SVT01315: "Cromford Road",
};

const LIVE =
  "https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/" +
  "Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0/query";

const RAIN =
  "https://api.open-meteo.com/v1/forecast?latitude=53.0246&longitude=-1.33" +
  "&daily=precipitation_sum&past_days=16&forecast_days=1&timezone=UTC";

const THRESHOLD_MM = 0.25;

// Refresh the stored timestamp at least this often even when nothing changed,
// so the page can say when it was last checked without writing to KV on all
// 288 cron runs a day.
const HEARTBEAT_MS = 30 * 60 * 1000;

async function getJSON(url, ms = 15000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    const r = await fetch(url, {
      signal: ctrl.signal,
      headers: { "User-Agent": "sewage.beardedbuddy.com" },
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

async function poll() {
  const ids = Object.keys(OUTFALLS).map((i) => `'${i}'`).join(",");
  const qs = new URLSearchParams({
    where: `Id IN (${ids})`,
    outFields: "Id,Status,StatusStart,LatestEventStart,LatestEventEnd,LastUpdated",
    returnGeometry: "false",
    f: "json",
  });
  const d = await getJSON(`${LIVE}?${qs}`);
  const out = {};
  for (const f of d.features || []) {
    const a = f.attributes;
    out[a.Id] = {
      status: a.Status === 1 ? "discharging" : a.Status === 0 ? "not discharging" : "offline",
      since: a.StatusStart || null,
      start: a.LatestEventStart || null,
      end: a.LatestEventEnd || null,
    };
  }
  return out;
}

/**
 * Fold a poll into the stored event list.
 *
 * Events are keyed on their END time, not their start. The company revises the
 * reported start of an event while it is still running, so the same discharge
 * can be seen with several different starts; keyed on the end, those collapse
 * back into one and the earliest start seen wins. Checked against the
 * Environment Agency's own detailed return for December 2025, this comes to
 * within about 5% of the official hours.
 *
 * The key is the end time rounded down to the MINUTE. The feed reports seconds,
 * and it revises them: the same discharge has been seen ending at :23 and then
 * :41 a poll later, which at full precision becomes two events. Rounding also
 * lets a seeded event, which only has minute precision, match the same event
 * when it is later seen live. The value keeps the exact times.
 */
const minute = (ms) => Math.floor(ms / 60000);

function fold(store, live) {
  let changed = false;
  for (const [id, s] of Object.entries(live)) {
    if (!s.start || !s.end || s.end <= s.start) continue;
    const key = `${id}|${minute(s.end)}`;
    const existing = store[key];
    if (existing === undefined) {
      store[key] = [s.start, s.end];
      changed = true;
    } else if (s.start < existing[0]) {
      // A revised start earlier than what we recorded: the discharge began
      // before we first saw it. Keep the earliest, and the latest end.
      store[key] = [s.start, Math.max(existing[1], s.end)];
      changed = true;
    } else if (s.end > existing[1]) {
      store[key] = [existing[0], s.end];
      changed = true;
    }
  }
  return changed;
}

/** Totals for a year from the stored events. */
function summarise(store, year) {
  const per = {};
  let events = 0;
  let ms = 0;
  let latest = null;
  for (const [key, val] of Object.entries(store)) {
    const id = key.split("|")[0];
    const [s, e] = Array.isArray(val) ? val : [Number(val), Number(key.split("|")[1]) * 60000];
    if (!Number.isFinite(s) || !Number.isFinite(e)) continue;
    if (new Date(s).getUTCFullYear() !== year) continue;
    const p = (per[id] = per[id] || { name: OUTFALLS[id] || id, events: 0, hours: 0, last: null });
    p.events += 1;
    p.hours += (e - s) / 3600000;
    if (p.last === null || s > p.last) p.last = s;
    events += 1;
    ms += e - s;
    if (latest === null || s > latest) latest = s;
  }
  for (const p of Object.values(per)) p.hours = Math.round(p.hours * 10) / 10;
  return {
    year,
    events,
    hours: Math.round((ms / 3600000) * 10) / 10,
    outfalls: per,
    latestDischarge: latest ? new Date(latest).toISOString() : null,
  };
}

async function recentRain() {
  const d = await getJSON(RAIN);
  const out = {};
  const { time, precipitation_sum: mm } = d.daily;
  for (let i = 0; i < time.length; i++) if (mm[i] !== null) out[time[i]] = mm[i];
  return out;
}

function prevDay(iso) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

/** The Environment Agency's dry-day test, applied to what we can see live. */
function flagDry(live, rain) {
  const out = [];
  for (const [id, s] of Object.entries(live)) {
    if (!s.start) continue;
    const day = new Date(s.start).toISOString().slice(0, 10);
    const prev = prevDay(day);
    if (!(day in rain) || !(prev in rain)) continue;
    if (rain[day] <= THRESHOLD_MM && rain[prev] <= THRESHOLD_MM) {
      out.push({ id, day, rain: rain[day], rainPrev: rain[prev] });
    }
  }
  return out;
}

async function refresh(env) {
  const year = new Date().getUTCFullYear();
  const prev = await env.DATA.get(STATUS_KEY, "json");

  const [liveR, rainR] = await Promise.allSettled([poll(), recentRain()]);
  const live = liveR.status === "fulfilled" ? liveR.value : null;
  const rain = rainR.status === "fulfilled" ? rainR.value : prev?.rain ?? {};

  const errors = [];
  if (liveR.status === "rejected") errors.push(`live: ${liveR.reason}`);
  if (rainR.status === "rejected") errors.push(`rain: ${rainR.reason}`);

  // Nothing new to record; leave the good data alone.
  if (!live) {
    return prev ? { ...prev, errors } : { updated: null, live: {}, rain: {}, errors };
  }

  // Fold the poll into this year's event record. Only write when it changed:
  // the cron runs every five minutes and most polls see nothing new.
  const key = eventsKey(year);
  const store = (await env.DATA.get(key, "json")) || {};
  if (fold(store, live)) {
    await env.DATA.put(key, JSON.stringify(store));
  }

  const payload = {
    updated: new Date().toISOString(),
    live,
    rain,
    dryFlags: flagDry(live, rain),
    anyDischarging: Object.values(live).some((s) => s.status === "discharging"),
    current: summarise(store, year),
    errors: errors.length ? errors : undefined,
  };

  // Same reasoning for the status blob: write on change, otherwise only often
  // enough to keep "last checked" honest.
  const stale = !prev?.updated ||
    Date.now() - Date.parse(prev.updated) > HEARTBEAT_MS;
  const moved = JSON.stringify(prev?.live) !== JSON.stringify(live) ||
    prev?.current?.events !== payload.current.events;
  if (stale || moved) await env.DATA.put(STATUS_KEY, JSON.stringify(payload));

  return payload;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/api/parish") {
      const data = await env.DATA.get(STATUS_KEY, "json");
      if (data) return json(data);
      // Nothing stored yet, which only happens before the first cron run.
      const fresh = await refresh(env).catch(() => null);
      return json(fresh ?? { updated: null, live: {}, rain: {}, dryFlags: [] });
    }

    // Everything we have recorded, so the numbers can be checked and so the
    // record can be exported if this ever needs rebuilding elsewhere.
    if (url.pathname === "/api/events") {
      const year = Number(url.searchParams.get("year")) ||
        new Date().getUTCFullYear();
      const store = (await env.DATA.get(eventsKey(year), "json")) || {};
      const events = Object.entries(store)
        .map(([k, val]) => {
          const id = k.split("|")[0];
          const [s, e] = Array.isArray(val)
            ? val
            : [Number(val), Number(k.split("|")[1]) * 60000];
          return {
            id,
            name: OUTFALLS[id] || id,
            start: new Date(s).toISOString(),
            end: new Date(e).toISOString(),
            hours: Math.round(((e - s) / 3600000) * 100) / 100,
          };
        })
        .filter((e) => new Date(e.start).getUTCFullYear() === year)
        .sort((a, b) => a.start.localeCompare(b.start));
      return json({ year, count: events.length, events });
    }

    if (url.pathname === "/api/refresh" && request.method === "POST") {
      ctx.waitUntil(refresh(env));
      return json({ queued: true });
    }

    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(refresh(env));
  },
};

function json(body) {
  return new Response(JSON.stringify(body), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
}
