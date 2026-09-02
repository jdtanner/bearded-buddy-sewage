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

  // A value and its unit are one token. With an ordinary space a narrow table
  // cell will happily leave the "h" stranded on its own line.
  var NB = "\u00a0";
  function unit(value, u) { return value + NB + u; }

  function setFacts(d, live) {
    var f = el("facts");
    if (!f) return;
    var t = d.totals;
    var cells = [
      [fmt(Math.round(t.hours)), NB + "h", "of discharge, " + t.from + "&ndash;" + t.to],
      [fmt(Math.round(t.days)), NB + "days", "the same figure, in days"],
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
      if (!ms) return "not since this site started watching";
      var m = Math.round((now - ms) / 60000);
      if (m < 60) return m + NB + "minutes ago";
      var h = Math.round(m / 60);
      if (h < 48) return h + NB + "hours ago";
      return Math.round(h / 24) + NB + "days ago";
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
        "<td>" + (cur ? cur.events : "&ndash;") + "</td>" +
        "<td>" + (cur ? unit(Math.round(cur.hours), "h") : "&ndash;") + "</td></tr>";
    }).join("");

    // Two columns rather than "50 / 266 h", which nobody could be expected to
    // read as fifty discharges totalling 266 hours.
    var yr = (live.current && live.current.year) || new Date().getUTCFullYear();
    t.innerHTML =
      "<thead><tr><th>Outfall</th><th>Now</th><th>Last discharged</th>" +
      "<th>Discharges in " + yr + "</th><th>Hours in " + yr + "</th>" +
      "</tr></thead><tbody>" + rows + "</tbody>";

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
          unit(r.threshold.toFixed(2), "mm") +
          (here ? " <b>&larr; the Environment Agency&rsquo;s test</b>" : "") +
          "</td><td>" + r.spills + "</td><td>" + unit(r.hours.toFixed(1), "h") + "</td></tr>";
      }).join("") + "</tbody>";
  }

  function setNear(d) {
    var t = el("near-table");
    if (!t || !d.dry.nearMisses || !d.dry.nearMisses.length) return;

    // Three of these are the same outfall on the same day, which reads as a
    // repeated row unless they are told apart. Sort oldest first and letter the
    // ones that share a date and a site.
    var rows = d.dry.nearMisses.slice().sort(function (a, b) {
      return a.day === b.day ? b.hours - a.hours : a.day.localeCompare(b.day);
    });
    var seen = {};
    rows.forEach(function (r) {
      var k = r.day + "|" + r.name;
      seen[k] = (seen[k] || 0) + 1;
      r._n = seen[k];
    });
    var totals = seen;

    t.innerHTML =
      "<thead><tr><th>Date</th><th>Outfall</th><th>Length</th>" +
      "<th>Rain that day</th><th>Day before</th></tr></thead><tbody>" +
      rows.map(function (r) {
        var d2 = new Date(r.day).toLocaleDateString("en-GB",
          { day: "numeric", month: "short", year: "numeric" });
        var multi = totals[r.day + "|" + r.name] > 1;
        var label = r.name + (multi
          ? ' <span class="disch">discharge ' +
            String.fromCharCode(64 + r._n) + "</span>"
          : "");
        return "<tr><td>" + d2 + "</td><td>" + label + "</td><td>" +
          (r.hours >= 1 ? unit(r.hours.toFixed(1), "h")
                        : unit(Math.round(r.hours * 60), "min")) + "</td><td>" +
          unit(r.maxOnDay.toFixed(1), "mm") + "</td><td>" +
          unit(r.maxDayBefore.toFixed(1), "mm") + "</td></tr>";
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
        '<span class="v">' + unit(fmt(Math.round(o.totalHours)), "h") + "</span>" +
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
          ? unit(r.hours.toFixed(0), "h")
          : '<span class="nr" title="No figure filed for this year">n/r</span>') + "</td>";
      }).join("");
      return "<tr><td>" + o.name + "</td><td>" + o.water + "</td>" + cells +
        "<td><b>" + unit(fmt(Math.round(o.totalHours)), "h") + "</b></td></tr>";
    }).join("");
    var foot = "<tr><td><b>All seven</b></td><td></td>" +
      d.years.map(function (y) {
        return "<td><b>" + unit(fmt(Math.round(d.perYear[y].hours)), "h") + "</b></td>";
      }).join("") +
      "<td><b>" + unit(fmt(Math.round(d.totals.hours)), "h") + "</b></td></tr>";
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
    set("cur-hours", fmt(Math.round(c.hours)) + NB + "hours");
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
        "Checked against the official return for December 2025, the first " +
        "month both sources cover completely, the live feed gave 136.5 hours " +
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

  /* The Environment Agency's own reasons for the river's condition. Only the
     Confirmed ones are tabled: Probable and Suspected are in the data and in the
     source, but the argument rests on what the Agency has actually concluded. */
  function setWfd(d) {
    var w = d.wfd;
    if (!w) return;
    // Capitalised, because the paragraph around it names the other grades the
    // same way: Moderate, Poor.
    var st = el("wfd-status");
    if (st) st.textContent = w.latestStatus || "Poor";

    var t = el("wfd-table");
    if (!t) return;
    var confirmed = (w.reasons || []).filter(function (r) {
      return (r.activityCertainty || "").toLowerCase() === "confirmed";
    });
    if (!confirmed.length) { t.closest(".tw").hidden = true; return; }
    t.innerHTML =
      "<thead><tr><th>What the Agency says is causing it</th><th>Sector</th>" +
      "<th>Affecting</th><th>Certainty</th></tr></thead><tbody>" +
      confirmed.map(function (r) {
        return "<tr><td>" + r.activity + "</td><td>" + r.sector +
          "</td><td>" + r.element + "</td><td><b>" + r.activityCertainty +
          "</b></td></tr>";
      }).join("") + "</tbody>";
  }

  /* Bailey Brook's own record, so the reader compares the brook with itself
     rather than with a standard nobody can picture. */
  function setRiver(d) {
    var r = d.river, t = el("river-table");
    if (!r || !t) return;
    var bb = r.points["MD-45691150"];
    if (!bb || !bb.series || !bb.series.ammonia) { t.closest(".tw").hidden = true; return; }
    var am = bb.series.ammonia, ox = bb.series.oxygen || {};
    var years = Object.keys(am).filter(function (y) { return y >= "2021"; }).sort();
    var base = r.baileyBaseline;

    t.innerHTML =
      "<thead><tr><th>Year</th><th>Ammonia, average</th><th>Highest single sample</th>" +
      "<th>Dissolved oxygen</th></tr></thead><tbody>" +
      years.map(function (y) {
        var a = am[y], hot = base && a.mean > base * 3;
        return "<tr" + (hot ? ' class="hot"' : "") + "><td>" + y + "</td>" +
          "<td>" + unit(a.mean.toFixed(2), "mg/l") +
          (hot ? " <b>&times;" + Math.round(a.mean / base) + "</b>" : "") + "</td>" +
          "<td>" + unit(a.max.toFixed(2), "mg/l") + "</td>" +
          "<td>" + (ox[y] ? unit(ox[y].mean.toFixed(1), "mg/l") : "&ndash;") + "</td></tr>";
      }).join("") +
      "<tr><td><b>2015&ndash;21</b></td><td><b>" + base.toFixed(2) +
      NB + "mg/l</b></td><td colspan=\"2\">the brook's own baseline</td></tr>" +
      "</tbody>";
  }

  /* The public address of this page, for putting in letters. Taken from the
     canonical link rather than location.href, so that a letter written from a
     preview on localhost still points at the real site. */
  function pageUrl() {
    var c = document.querySelector('link[rel="canonical"]');
    return (c && c.href) || location.origin + "/";
  }

  function setMailto(d) {
    var a = el("mp-mail");
    if (!a) return;
    var t = d.totals, c = d.current, w = d.wfd, cat = d.catchment;
    var pct = c && d.perYear[t.to]
      ? Math.round((c.hours / d.perYear[t.to].hours) * 100) : null;

    var body = [
      "Dear Ms Farnsworth,",
      "",
      "I am a constituent living in Aldercar and Langley Mill.",
      "",
      "Between " + t.from + " and " + t.to + ", the seven Severn Trent storm overflows",
      "inside this parish discharged sewage into the River Erewash and Bailey Brook",
      "for " + fmt(Math.round(t.hours)) + " hours, across " + fmt(t.spills) + " separate spills. That is the",
      "equivalent of " + Math.round(t.days) + " days. These are Severn Trent's own figures, filed",
      "with the Environment Agency.",
      "",
    ];

    if (c && pct) {
      body.push(
        "It is not improving. From Severn Trent's live feed, this parish has already",
        "had " + fmt(Math.round(c.hours)) + " hours of discharge in " + c.year + ", " + pct + "% of the whole of " + t.to + ",",
        "with a third of the year and the wettest months still to come.",
        "");
    }

    body.push(
      "Almost none of it broke any rule, and that is the point. Every one of the " +
        (d.dry.tested || 693),
      "individual discharges recorded in " + (d.dry.yearsTested || []).join(" and ") + " has been tested",
      "against the Environment Agency's own dry-day test. Two happened in dry weather.",
      "The rest were permitted. The permits are the problem.",
      "");

    if (w && w.latestStatus) {
      body.push(
        "The Environment Agency has already reached the same conclusion. It classifies",
        "this stretch of the Erewash (water body " + w.waterbody + ") as " + w.latestStatus + ", down",
        "from Moderate in 2015. Of the twenty reasons it records for the river failing to",
        "achieve good status, farming and urban run-off are marked Probable. Two are",
        "marked Confirmed, and both are sewage discharge from the water industry, one",
        "continuous and one intermittent. Intermittent means storm overflows.",
        "");
    }

    body.push(
      "Severn Trent will tell you, correctly, that they have spent money here. Between",
      "2022 and 2024 they spent around 35.8 million pounds rebuilding Newthorpe works",
      "and closing Milnhay as a treatment works, and they enlarged the storm tanks at",
      "Milnhay from 2 megalitres to 7. That scheme was built to meet the Water Framework",
      "Directive and the tighter phosphate limits that came into force in December 2024.",
      "",
      "Two things follow from that, and they are the reason I am writing.",
      "",
      "First, this river was classified Poor in 2016 and has been Poor at every",
      "assessment since. The works discharged into it throughout. What changed was not",
      "the state of the river, which was on the record the whole time. What changed was",
      "the law.",
      "",
      "Second, it has not been enough. The enlarged storm tank at Milnhay discharged for",
      "305 hours in 2025, the first full year after the work was completed, and by 1",
      "September 2026 it had already discharged for 266 hours with the wettest months",
      "still ahead. Severn Trent's own return gives the cause as \"hydraulic capacity\":",
      "the site cannot take what is being put into it, and housing continues to be built",
      "on the same network.",
      "");

    if (cat && cat.upstream) {
      body.push(
        "This is not only a local problem. Of the " + cat.total + " monitored storm overflows in",
        "this river's catchment, " + cat.upstream + " are upstream of us, so what they release comes",
        "through this parish before it goes anywhere else.",
        "");
    }

    body.push(
      "I would like to know:",
      "",
      "1. What you will do to secure further investment in this network, given that a",
      "   35.8 million pound scheme completed in 2024 has not stopped the storm tank at",
      "   Milnhay, which remains the largest single source of sewage in this parish.",
      "2. Whether you will press the Environment Agency to review the permit",
      "   conditions for these outfalls, given that the Agency itself records",
      "   intermittent sewage discharge as a confirmed cause of this river's",
      "   condition.",
      "3. What assessment is made of sewer capacity before new housing is approved",
      "   here, and who makes it.",
      "4. Whether you will ask the Agency why the flow monitoring at Milnhay works",
      "   reported no usable data for 336 days of 2025.",
      "",
      "Every figure above comes from published Government data. The full working,",
      "with every source linked and the method described, is set out at:",
      "",
      "    " + pageUrl(),
      "",
      "Yours sincerely,",
      "",
      "[your name]",
      "[your address, so she can see you are a constituent]");

    a.href = "mailto:?subject=" +
      encodeURIComponent("Sewage discharges into the River Erewash at Langley Mill") +
      "&body=" + encodeURIComponent(body.join("\n"));
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
    setWfd(d);
    setRiver(d);
    setMailto(d);
    setCornwood();
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
