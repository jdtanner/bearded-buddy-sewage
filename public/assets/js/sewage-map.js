/* Sewage map for sewage.beardedbuddy.com.
   A sibling of the walks site's walk-map.js rather than a fork of it: the base
   layers, the dashed parish boundary, the divIcon dots and the scroll-wheel
   behaviour are the same house style, but nothing here is about a route.

   Exposes one global, BBSewage.init(opts). */
(function () {
  "use strict";

  function bases() {
    // Street first: it is the default, and the layer control lists these in key
    // order. The walks site leads with Outdoor because contours matter on a
    // walk; here the job is finding a street corner and a river, so plain OSM
    // reads better and goes two zoom levels deeper.
    // These attribution strings are a licence condition. Do not remove them.
    return {
      Street: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution:
          'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }),
      Outdoor: L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
        maxZoom: 17,
        attribution:
          'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
          'contributors, <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
      }),
      Satellite: L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { maxZoom: 19, attribution: "Imagery &copy; Esri" }
      ),
    };
  }

  /* A dot sized by how much this outfall spilled and coloured by what it
     spills into, with a white ring so it reads on any base layer. */
  function dot(colour, size, live) {
    return L.divIcon({
      className: "bb-pin" + (live ? " is-live" : ""),
      html:
        (live ? '<i class="bb-ring"></i>' : "") +
        '<span style="display:block;width:' + size + "px;height:" + size + "px;" +
        "border-radius:50%;background:" + colour + ";border:3px solid #fff;" +
        'box-shadow:0 0 0 1px rgba(0,0,0,.35)"></span>',
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }

  function radius(hours, max) {
    // Area in proportion to hours, so a dot twice the width is four times the
    // sewage, not twice. Floor of 11px so the quiet ones stay clickable.
    var frac = max > 0 ? Math.sqrt(hours / max) : 0;
    return Math.round(11 + frac * 21);
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function hours(h) {
    // Non-breaking, so a narrow popup cannot strand the unit on its own line.
    if (h == null) return "not reported";
    if (h >= 48) return (h / 24).toFixed(1) + "\u00a0days";
    return h.toFixed(1) + "\u00a0hours";
  }

  function popup(o, years, live) {
    // A horizontal strip: six narrow year columns. Stacking them vertically
    // made the popup taller than the map, and Leaflet then panned the marker
    // clean off the screen to fit it.
    var head = years.map(function (y) { return "<th>" + y + "</th>"; }).join("");
    var cells = years.map(function (y) {
      var d = o.years[y];
      return "<td>" + (d && d.hours != null
        ? Math.round(d.hours) + "\u00a0<i>h</i>"
        : '<span class="nr">n/r</span>') + "</td>";
    }).join("");

    var status = "";
    if (live && live[o.id]) {
      var s = live[o.id];
      status =
        '<span class="pop-live' + (s.status === "discharging" ? " on" : "") + '">' +
        (s.status === "discharging" ? "Discharging now"
          : s.status === "offline" ? "Monitor offline" : "Not discharging") +
        "</span>";
    }

    return (
      '<div class="pop">' +
      "<h4>" + esc(o.name) + "</h4>" +
      '<p class="pop-sub">' + esc(o.kind) + " &rarr; " + esc(o.water) + " " + status + "</p>" +
      '<p class="pop-big"><b>' + hours(o.totalHours) + "</b> since 2020, " +
      o.totalSpills + " spills</p>" +
      '<table class="pop-tab"><thead><tr>' + head + "</tr></thead>" +
      "<tbody><tr>" + cells + "</tr></tbody></table>" +
      '<p class="pop-fine">Permit ' + esc(o.permit || "&ndash;") +
      " &middot; " + esc(o.id) + "</p>" +
      "</div>"
    );
  }

  function init(opts) {
    var mapEl = document.getElementById(opts.map);
    if (!mapEl || typeof L === "undefined") return;

    Promise.all([
      fetch(opts.data).then(function (r) { return r.json(); }),
      fetch(opts.boundary).then(function (r) { return r.json(); }),
      fetch(opts.live).then(function (r) { return r.json(); }).catch(function () { return null; }),
    ])
      .then(function (res) {
        draw(mapEl, res[0], res[1], res[2], opts);
      })
      .catch(function () {
        mapEl.innerHTML =
          '<p style="padding:1.5rem;color:#6b7385">The map could not be loaded. ' +
          "The figures below do not depend on it.</p>";
      });
  }

  function draw(mapEl, data, boundary, liveData, opts) {
    var b = bases();
    var map = L.map(mapEl, { layers: [b.Street], scrollWheelZoom: false });
    L.control.scale({ imperial: true, metric: true }).addTo(map);

    var ring = L.polyline(boundary, {
      color: "#283653", weight: 2, opacity: 0.85,
      dashArray: "7 6", interactive: false,
    }).addTo(map);

    // Every permitted discharge point on the Environment Agency's register, as a
    // layer you can turn on. Most coincide with an outfall above; the point of
    // showing them is the ones that do not, which discharge here with a permit
    // and no monitor and therefore no published hours.
    var consents = L.layerGroup();
    var sites = (data.consents && data.consents.sites) || [];
    sites.forEach(function (c) {
      L.circleMarker([c.lat, c.lon], {
        radius: 7,
        color: c.monitored ? "#283653" : "#B4802A",
        weight: 2,
        fillColor: c.monitored ? "#283653" : "#B4802A",
        fillOpacity: c.monitored ? 0.15 : 0.55,
        dashArray: c.monitored ? null : "3 3",
      })
        .bindPopup(
          '<div class="pop"><h4>' + esc(c.site) + "</h4>" +
          '<p class="pop-sub">' + esc(c.effluent || "") + "</p>" +
          '<p class="pop-big">Permitted to discharge into ' + esc(c.receiving || "") +
          "</p>" +
          '<p class="pop-note' + (c.monitored ? "" : " warn") + '">' +
          (c.monitored
            ? "Has an event duration monitor. Its hours are in the figures above."
            : "<b>No event duration monitor.</b> Nothing on this page counts it, " +
              "because no hours are published for it anywhere.") +
          "</p>" +
          '<p class="pop-fine">Permit ' + esc(c.permit) + "</p></div>",
          { maxWidth: 320 }
        )
        .addTo(consents);
    });

    // Built after the outfall markers below, so the control can list both.
    var overlays = null;

    var live = liveData && liveData.live ? liveData.live : {};
    var max = Math.max.apply(null, data.outfalls.map(function (o) { return o.totalHours; }));
    var markers = [];

    // Milnhay works has two separately permitted assets - the inlet overflow
    // and the storm tank - at one set of coordinates. Nudging them apart would
    // put a dot where there is no outfall, so they share a marker and the popup
    // lists both. The table below still counts them separately, because the
    // Environment Agency permits them separately.
    var CLUSTER_M = 90;
    var groups = [];
    data.outfalls.forEach(function (o) {
      if (o.lat == null || o.lon == null) return;
      var near = groups.find(function (g) {
        var dy = (o.lat - g.lat) * 111320;
        var dx = (o.lon - g.lon) * 111320 * Math.cos(o.lat * Math.PI / 180);
        return Math.sqrt(dx * dx + dy * dy) < CLUSTER_M;
      });
      if (near) near.items.push(o);
      else groups.push({ lat: o.lat, lon: o.lon, items: [o] });
    });

    var index = {};
    var anyLive = false;
    var outfalls = L.layerGroup().addTo(map);
    groups.forEach(function (g) {
      var total = g.items.reduce(function (a, o) { return a + o.totalHours; }, 0);
      var brook = g.items.every(function (o) { return /bailey/i.test(o.water || ""); });
      var on = g.items.some(function (o) {
        return live[o.id] && live[o.id].status === "discharging";
      });
      if (on) anyLive = true;
      var m = L.marker([g.lat, g.lon], {
        icon: dot(brook ? "#8E4A78" : "#c62828", radius(total, max), on),
        title: g.items.map(function (o) { return o.name; }).join(" / ")
          + (on ? " (discharging now)" : ""),
        riseOnHover: true,
      })
        .addTo(outfalls)
        .bindPopup(
          g.items.map(function (o) { return popup(o, data.years, live); }).join(
            '<hr style="border:0;border-top:1px solid #e2e5ec;margin:.7rem 0">'
          ),
          {
          maxWidth: 420, minWidth: 300, autoPanPadding: [20, 20],
          // Milnhay stacks three assets into one popup. Without a cap it grows
          // taller than the map and Leaflet pans the marker off-screen to fit.
          maxHeight: 330,
        }
        );
      markers.push(m);
      g.items.forEach(function (o) { index[o.id] = m; });
    });

    // The two layers sit on top of each other at several sites, so both are
    // switchable: turn the outfalls off to see which permitted points have no
    // monitor behind them.
    overlays = { "Sewage outfalls (monitored)": outfalls };
    if (sites.length) overlays["Every permitted discharge"] = consents;
    overlays["Parish boundary"] = ring;
    L.control.layers(b, overlays, { position: "topright" }).addTo(map);

    if (markers.length) {
      map.fitBounds(L.featureGroup(markers).getBounds().pad(0.35));
    } else {
      map.fitBounds(ring.getBounds());
    }
    var home = map.getBounds();

    // Scroll-wheel zoom off until the map is clicked, so the page still
    // scrolls normally on a phone.
    map.on("click", function () { map.scrollWheelZoom.enable(); });
    map.on("mouseout", function () { map.scrollWheelZoom.disable(); });

    var reset = document.querySelector("[data-map-reset]");
    if (reset) {
      reset.addEventListener("click", function (e) {
        e.preventDefault();
        map.fitBounds(home);
      });
    }

    // Let the page open a specific outfall from its row in the table.
    document.querySelectorAll("[data-outfall]").forEach(function (el) {
      el.addEventListener("click", function (e) {
        e.preventDefault();
        var m = index[el.getAttribute("data-outfall")];
        if (m) {
          mapEl.scrollIntoView({ behavior: "smooth", block: "center" });
          m.openPopup();
        }
      });
    });

    var keyLive = document.getElementById("key-live");
    if (keyLive && anyLive) keyLive.hidden = false;

    if (opts.onready) opts.onready(data, liveData);
  }

  window.BBSewage = { init: init };
})();
