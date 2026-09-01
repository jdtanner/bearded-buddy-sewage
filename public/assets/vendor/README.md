# Vendored third-party assets

Pinned and served from this origin rather than a CDN, matching the pattern used by
`bearded-buddy-money` (`public/vendor/chart.umd.min.js`).

## leaflet-1.9.4/ : Leaflet 1.9.4

- Source: https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/
- Licence: BSD-2-Clause
- Files: `leaflet.js`, `leaflet.css`, `images/` (marker and layer-control sprites)

`leaflet.css` refers to `images/` relatively, so keep that folder alongside it.

To update: replace all files from the same dist path at the new version and bump the
version here. Check the map still fits bounds and all three base layers tile.
