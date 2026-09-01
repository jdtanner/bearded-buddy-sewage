/* Renders the parts of the page that come from the data, so that the numbers
   in the prose and the numbers in the tables can never drift apart: everything
   here reads data/parish.json, which tools/bundle.py writes.

   The headline figures are also hard-coded in index.html so the page says
   something true before JavaScript runs, and if the numbers change this script
   overwrites them. */
(function () {
  "use strict";

  var DATA = "/data/parish.json";
  var LIVE = "/api/parish";

  function el(id) { return document.getElementById(id); }
  function fmt(n) { return n.toLocaleString("en-GB"); }

  function setFacts(d, live) {
    var f = el("facts");
    if (!f) return;
    var t = d.totals;
    var cells = [
      [fmt(Math.round(t.hours)), " h", "of discharge, " + t.from + "&ndash;" + t.to],
      [fmt(Math.round(t.days)), " days", "the same figure, in days"],
      [fmt(t.spills), "", "separate spills"],
      [String(d.outfalls.length), "", "outfalls in the parish"],
    ];
    var html = cells.map(function (c) {
      return '<div class="fact"><div class="n">' + c[0] +
        (c[1] ? "<small>" + c[1] + "</small>" : "") +
        '</div><div class="l">' + c[2] + "</div></div>";
    });

    var n = live && live.live
      ? Object.values(live.live).filter(function (s) { return s.status === "discharging"; }).length
      : null;
    html.push(
      '<div class="fact"><div class="n' + (n ? " hot" : "") + '">' +
      (n === null ? "&ndash;" : n) + '</div><div class="l">discharging right now</div></div>'
    );
    f.innerHTML = html.join("");

    var u = el("updated");
    if (u && live && live.updated) {
      var when = new Date(live.updated);
      u.innerHTML = "Live status from Severn Trent, checked " +
        when.toLocaleDateString("en-GB", { day: "numeric", month: "long" }) +
        " at " + when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) +
        ". Historic figures from the Environment Agency annual returns.";
    } else if (u) {
      u.textContent = "Historic figures from the Environment Agency annual returns.";
    }
  }

  /* The live panel. This is the only part of the page that is about right now
     rather than about the record, so it says plainly when each outfall last
     discharged rather than hiding a single count in a stat tile. */
  function setLive(d, live) {
    var t = el("live-table"), note = el("live-note"), dot = el("live-dot");
    if (!t) return;

    if (!live || !live.live || !Object.keys(live.live).length) {
      var box = t.closest(".livebox");
      if (box) box.hidden = true;
      return;
    }

    var order = d.outfalls
      .filter(function (o) { return live.live[o.id]; })
      .sort(function (a, b) { return b.totalHours - a.totalHours; });

    var now = Date.now();
    function ago(ms) {
      if (!ms) return "not since we started watching";
      var m = Math.round((now - ms) / 60000);
      if (m < 60) return m + " minutes ago";
      var h = Math.round(m / 60);
      if (h < 48) return h + " hours ago";
      return Math.round(h / 24) + " days ago";
    }

    var on = 0;
    var rows = order.map(function (o) {
      var s = live.live[o.id];
      var cur = (live.current && live.current.outfalls && live.current.outfalls[o.id]) || null;
      if (s.status === "discharging") on++;
      var badge = s.status === "discharging"
        ? '<span class="pop-live on">Discharging</span>'
        : s.status === "offline"
        ? '<span class="pop-live off">Monitor offline</span>'
        : '<span class="pop-live">Quiet</span>';
      return "<tr><td>" + o.name + "</td><td>" + badge + "</td>" +
        "<td>" + ago(s.lastStart || s.start) + "</td>" +
        "<td>" + (cur ? cur.events + " / " + Math.round(cur.hours) + " h" : "&ndash;") +
        "</td></tr>";
    }).join("");

    t.innerHTML =
      "<thead><tr><th>Outfall</th><th>Now</th><th>Last discharged</th>" +
      "<th>This year</th></tr></thead><tbody>" + rows + "</tbody>";

    if (dot) {
      dot.className = "livedot" + (on ? " on" : "");
      dot.title = on ? on + " discharging" : "none discharging";
    }
    if (note) {
      var when = live.updated ? new Date(live.updated) : null;
      note.innerHTML =
        (on
          ? "<b>" + on + " of these is discharging into the river as you read this.</b> "
          : "None of them is discharging at this moment. ") +
        "This site checks Severn Trent's feed every five minutes and keeps its own " +
        "record, because the feed only ever reports the most recent discharge and " +
        "forgets the rest." +
        (when ? " Last checked " + when.toLocaleTimeString("en-GB",
          { hour: "2-digit", minute: "2-digit" }) + " on " +
          when.toLocaleDateString("en-GB", { day: "numeric", month: "long" }) + "." : "");
    }
  }

  function setSweep(d) {
    var t = el("sweep-table");
    if (!t || !d.dry.sweep) return;
    t.innerHTML =
      "<thead><tr><th>If the threshold were</th><th>Discharges</th><th>Hours</th></tr></thead>" +
      "<tbody>" + d.dry.sweep.map(function (r) {
        var here = r.threshold === d.dry.threshold_mm;
        return "<tr" + (here ? ' class="here"' : "") + "><td>" +
          r.threshold.toFixed(2) + " mm" +
          (here ? " <b>&larr; the Environment Agency&rsquo;s test</b>" : "") +
          "</td><td>" + r.spills + "</td><td>" + r.hours.toFixed(1) + " h</td></tr>";
      }).join("") + "</tbody>";
  }

  function setNear(d) {
    var t = el("near-table");
    if (!t || !d.dry.nearMisses || !d.dry.nearMisses.length) return;
    t.innerHTML =
      "<thead><tr><th>Date</th><th>Outfall</th><th>Length</th>" +
      "<th>Rain that day</th><th>Day before</th></tr></thead><tbody>" +
      d.dry.nearMisses.map(function (r) {
        var d2 = new Date(r.day).toLocaleDateString("en-GB",
          { day: "numeric", month: "short", year: "numeric" });
        return "<tr><td>" + d2 + "</td><td>" + r.name + "</td><td>" +
          (r.hours >= 1 ? r.hours.toFixed(1) + " h"
                        : Math.round(r.hours * 60) + " min") + "</td><td>" +
          r.maxOnDay.toFixed(1) + " mm</td><td>" +
          r.maxDayBefore.toFixed(1) + " mm</td></tr>";
      }).join("") + "</tbody>";
  }

  function setBars(d) {
    var wrap = el("bars");
    if (!wrap) return;
    var max = Math.max.apply(null, d.outfalls.map(function (o) { return o.totalHours; }));
    wrap.innerHTML = d.outfalls.map(function (o) {
      var pct = max > 0 ? (o.totalHours / max) * 100 : 0;
      return '<div class="bar road">' +
        '<span><a href="#" data-outfall="' + o.id + '">' + o.name + "</a></span>" +
        '<span class="track"><i style="width:' + pct.toFixed(1) + '%"></i></span>' +
        '<span class="v">' + fmt(Math.round(o.totalHours)) + " h</span>" +
        "</div>";
    }).join("");
  }

  function setTable(d) {
    var t = el("table");
    if (!t) return;
    var head = "<thead><tr><th>Outfall</th><th>Goes into</th>" +
      d.years.map(function (y) { return "<th>" + y + "</th>"; }).join("") +
      "<th>Total</th></tr></thead>";
    var body = d.outfalls.map(function (o) {
      var cells = d.years.map(function (y) {
        var r = o.years[y];
        return "<td>" + (r && r.hours != null
          ? r.hours.toFixed(0) + " h"
          : '<span class="nr" title="No figure filed for this year">n/r</span>') + "</td>";
      }).join("");
      return "<tr><td>" + o.name + "</td><td>" + o.water + "</td>" + cells +
        "<td><b>" + fmt(Math.round(o.totalHours)) + " h</b></td></tr>";
    }).join("");
    var foot = "<tr><td><b>All seven</b></td><td></td>" +
      d.years.map(function (y) {
        return "<td><b>" + fmt(Math.round(d.perYear[y].hours)) + " h</b></td>";
      }).join("") +
      "<td><b>" + fmt(Math.round(d.totals.hours)) + " h</b></td></tr>";
    t.innerHTML = head + "<tbody>" + body + foot + "</tbody>";
  }

  /* Hand-built SVG, in the same spirit as the walks site's height profile:
     no chart library for one bar chart. */
  function setTrend(d) {
    var host = document.querySelector("[data-trend-svg]");
    if (!host) return;
    var W = 900, H = 260, padL = 54, padR = 14, padT = 16, padB = 42;
    var years = d.years;
    var vals = years.map(function (y) { return d.perYear[y].hours; });
    var max = Math.ceil(Math.max.apply(null, vals) / 500) * 500 || 500;
    var iw = W - padL - padR, ih = H - padT - padB;
    var bw = (iw / years.length) * 0.62;

    var parts = [];
    for (var g = 0; g <= max; g += 500) {
      var y = padT + ih - (g / max) * ih;
      parts.push('<line x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (W - padR) +
        '" y2="' + y.toFixed(1) + '" stroke="#e2e5ec" stroke-width="1"/>');
      parts.push('<text x="' + (padL - 8) + '" y="' + (y + 4).toFixed(1) +
        '" text-anchor="end" font-size="12" fill="#6b7385">' + g + "</text>");
    }
    years.forEach(function (yr, i) {
      var v = d.perYear[yr];
      var cx = padL + (iw / years.length) * (i + 0.5);
      var h = (v.hours / max) * ih;
      var top = padT + ih - h;
      var partial = v.reporting < v.of;
      parts.push('<rect x="' + (cx - bw / 2).toFixed(1) + '" y="' + top.toFixed(1) +
        '" width="' + bw.toFixed(1) + '" height="' + Math.max(h, 1).toFixed(1) +
        '" fill="' + (partial ? "#e39a9a" : "#c62828") + '" rx="2"/>');
      parts.push('<text x="' + cx.toFixed(1) + '" y="' + (top - 7).toFixed(1) +
        '" text-anchor="middle" font-size="12" font-weight="700" fill="#283653">' +
        Math.round(v.hours) + "</text>");
      parts.push('<text x="' + cx.toFixed(1) + '" y="' + (H - 14) +
        '" text-anchor="middle" font-size="13" fill="#1c2333">' + yr + "</text>");
    });
    parts.push('<line x1="' + padL + '" y1="' + (padT + ih) + '" x2="' + (W - padR) +
      '" y2="' + (padT + ih) + '" stroke="#6b7385" stroke-width="1"/>');
    parts.push('<text x="' + padL + '" y="' + (padT - 2) +
      '" font-size="12" fill="#6b7385">hours of discharge</text>');

    host.innerHTML = '<svg viewBox="0 0 ' + W + " " + H +
      '" role="img" aria-label="Hours of sewage discharge per year, ' +
      years[0] + " to " + years[years.length - 1] +
      '" style="width:100%;height:auto;display:block">' + parts.join("") + "</svg>";

    var note = el("trend-note");
    var partials = years.filter(function (y) { return d.perYear[y].reporting < d.perYear[y].of; });
    if (note) {
      // Deliberately does not say "so the real total is higher". It is for 2020,
      // where monitors were not yet installed, but not for 2025, where an
      // outfall was decommissioned. Both are explained just below.
      note.innerHTML = partials.length
        ? "Paler bars (" + partials.join(", ") + ") are years when fewer than all " +
          d.outfalls.length + " outfalls filed a figure, for the reasons below."
        : "";
    }
  }

  /* The year in progress. Provisional live-feed figures, deliberately separate
     from the headline totals, which are the official returns only. */
  function setCurrent(d, live) {
    // Prefer the Worker's own record over the file built on the last data run:
    // it is this site's own count, and it is up to the last five minutes.
    // The committed file is the fallback for when the API is unreachable.
    var c = (live && live.current && live.current.events) ? live.current : d.current;
    if (!c) return;
    if (!c.asOf) c.asOf = (live && live.updated) ? live.updated.slice(0, 10) : null;
    var full = d.perYear[d.totals.to];
    var set = function (id, text) { var e = el(id); if (e) e.textContent = text; };
    set("cur-hours", fmt(Math.round(c.hours)) + " hours");
    set("cur-events", fmt(c.events));
    set("cur-pct", Math.round((c.hours / full.hours) * 100) + "%");

    var note = el("cur-note");
    if (note) {
      var asOf = c.asOf
        ? new Date(c.asOf).toLocaleDateString("en-GB",
            { day: "numeric", month: "long", year: "numeric" })
        : "today";
      note.innerHTML =
        "Provisional, to " + asOf + ". These come from Severn Trent's live feed " +
        "rather than the audited annual return, so treat them as indicative. " +
        "Checked against the official return for December 2025 \u2014 the first " +
        "month both sources cover completely \u2014 the live feed gave 136.5 hours " +
        "against an official 130.3, about 5% over. They are shown separately from " +
        "the six-year totals above, which use published returns only.";
    }

    var m = c.outfalls && c.outfalls.SVT01571;
    if (m && m.last) {
      var last = new Date(m.last);
      set("milnhay-last", "on " + last.toLocaleDateString("en-GB",
        { day: "numeric", month: "long", year: "numeric" }));
    }
  }

  function setMailto(d) {
    var a = el("mp-mail");
    if (!a) return;
    var t = d.totals;
    var body = [
      "Dear Ms Farnsworth,",
      "",
      "I am a constituent living in Aldercar and Langley Mill.",
      "",
      "Between " + t.from + " and " + t.to + ", the seven Severn Trent storm overflows inside our",
      "parish discharged sewage into the River Erewash and Bailey Brook for " +
        fmt(Math.round(t.hours)) + " hours",
      "across " + fmt(t.spills) + " separate spills. That is the equivalent of " +
        Math.round(t.days) + " days.",
      "",
      "These figures come from Severn Trent's own returns to the Environment Agency.",
      "Almost all of this discharging was permitted. That is my concern: the permits",
      "themselves allow it.",
      "",
      "I would like to know:",
      "",
      "1. What you are doing to secure investment in the Milnhay treatment works, which",
      "   accounts for most of the discharge in this parish.",
      "2. Whether you will press the Environment Agency to review the permit conditions",
      "   for these outfalls.",
      "3. What assessment is made of sewer capacity before new housing is approved here.",
      "",
      "I would be grateful for a reply.",
      "",
      "Yours sincerely,",
      "",
      "[your name and address]",
    ].join("\n");
    a.href = "mailto:?subject=" +
      encodeURIComponent("Sewage discharges into the Erewash at Langley Mill") +
      "&body=" + encodeURIComponent(body);
  }

  function render(d, live) {
    setFacts(d, live);
    setLive(d, live);
    setSweep(d);
    setNear(d);
    setBars(d);
    setTable(d);
    setTrend(d);
    setCurrent(d, live);
    setMailto(d);
  }

  fetch(DATA)
    .then(function (r) { return r.json(); })
    .then(function (d) {
      fetch(LIVE)
        .then(function (r) { return r.json(); })
        .catch(function () { return null; })
        .then(function (live) { render(d, live); });

      BBSewage.init({
        map: "map",
        data: DATA,
        boundary: "/data/boundary.json",
        live: LIVE,
      });
    })
    .catch(function () {
      // The prose and the hard-coded headline figures still stand.
    });
})();
