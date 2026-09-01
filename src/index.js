/**
 * sewage.beardedbuddy.com
 *
 * Serves the page from ./public, and one JSON endpoint at /api/parish.
 *
 * The page never calls an upstream API itself. A cron job asks Severn Trent
 * and Open-Meteo for the current picture and writes the answer to KV; the
 * page reads that. Both upstreams have been seen to fail — the Environment
 * Agency's rainfall API returned 503 on two requests out of three while this
 * was being built — and a campaign page that shows an error because someone
 * else's server is down is worse than one showing yesterday's numbers.
 *
 * So: a failed refresh leaves the previous value in KV untouched, and the
 * payload carries the time it was gathered so the page can say how old it is.
 */

const KEY = "parish:aldercar";

// The seven monitored assets inside the parish boundary, by the Environment
// Agency's unique id. SVT01570 is not in Severn Trent's live feed - only the
// storm tank at Milnhay reports live - so it will simply have no status.
const OUTFALLS = [
  "SVT01315", "SVT00684", "SVT01317", "SVT01316",
  "SVT01338", "SVT01570", "SVT01571",
];

const LIVE =
  "https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/" +
  "Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0/query";

const RAIN =
  "https://api.open-meteo.com/v1/forecast?latitude=53.0246&longitude=-1.33" +
  "&daily=precipitation_sum&past_days=16&forecast_days=1&timezone=UTC";

// The Environment Agency's dry-day test: no more than this much rain on the
// day of the spill or the day before.
const THRESHOLD_MM = 0.25;

async function withTimeout(url, ms = 15000) {
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

async function liveStatus() {
  const ids = OUTFALLS.map((i) => `'${i}'`).join(",");
  const qs = new URLSearchParams({
    where: `Id IN (${ids})`,
    outFields: "Id,Status,StatusStart,LatestEventStart,LatestEventEnd,LastUpdated",
    returnGeometry: "false",
    f: "json",
  });
  const d = await withTimeout(`${LIVE}?${qs}`);
  const out = {};
  for (const f of d.features || []) {
    const a = f.attributes;
    out[a.Id] = {
      // Severn Trent use 1 for discharging, 0 for not, -1 for offline.
      status: a.Status === 1 ? "discharging" : a.Status === 0 ? "not discharging" : "offline",
      since: a.StatusStart || null,
      lastStart: a.LatestEventStart || null,
      lastEnd: a.LatestEventEnd || null,
    };
  }
  return out;
}

async function recentRain() {
  const d = await withTimeout(RAIN);
  const out = {};
  const { time, precipitation_sum: mm } = d.daily;
  for (let i = 0; i < time.length; i++) {
    if (mm[i] !== null) out[time[i]] = mm[i];
  }
  return out;
}

function prevDay(iso) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

/** The EA test, applied to whatever live events we can see. */
function flagDry(live, rain) {
  const flagged = [];
  for (const [id, s] of Object.entries(live)) {
    if (!s.lastStart) continue;
    const day = new Date(s.lastStart).toISOString().slice(0, 10);
    const prev = prevDay(day);
    if (!(day in rain) || !(prev in rain)) continue;
    if (rain[day] <= THRESHOLD_MM && rain[prev] <= THRESHOLD_MM) {
      flagged.push({ id, day, rain: rain[day], rainPrev: rain[prev] });
    }
  }
  return flagged;
}

async function refresh(env) {
  const prev = await env.DATA.get(KEY, "json");

  // Settle both independently: one upstream failing should not cost us the
  // other's fresh data.
  const [liveR, rainR] = await Promise.allSettled([liveStatus(), recentRain()]);

  const live = liveR.status === "fulfilled" ? liveR.value : prev?.live ?? {};
  const rain = rainR.status === "fulfilled" ? rainR.value : prev?.rain ?? {};

  const errors = [];
  if (liveR.status === "rejected") errors.push(`live: ${liveR.reason}`);
  if (rainR.status === "rejected") errors.push(`rain: ${rainR.reason}`);

  // If both failed there is nothing new to say; keep what we had rather than
  // overwriting a good payload with an empty one.
  if (liveR.status === "rejected" && rainR.status === "rejected" && prev) {
    return { ...prev, staleSince: prev.updated, errors };
  }

  const payload = {
    updated: new Date().toISOString(),
    live,
    rain,
    dryFlags: flagDry(live, rain),
    anyDischarging: Object.values(live).some((s) => s.status === "discharging"),
    errors: errors.length ? errors : undefined,
  };
  await env.DATA.put(KEY, JSON.stringify(payload));
  return payload;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/api/parish") {
      const data = await env.DATA.get(KEY, "json");
      if (!data) {
        // First request before the cron has ever run. Fill it in now rather
        // than serving nothing, but do not let the visitor wait on it.
        const fresh = await refresh(env).catch(() => null);
        return json(fresh ?? { updated: null, live: {}, rain: {}, dryFlags: [] });
      }
      return json(data);
    }

    // Manual refresh, handy from a terminal while working on it.
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
      // Short edge cache: the cron runs daily, but a burst of shares should
      // not each hit KV.
      "cache-control": "public, max-age=300",
    },
  });
}
