# Leaflet 1.9.4

Copied from https://unpkg.com/leaflet@1.9.4/dist/ (BSD-2-Clause, see LICENSE) and
served from this site, because the Content Security Policy allows scripts only
from 'self'. Used by core/static/core/field-map.js.

Change made: the `//# sourceMappingURL=leaflet.js.map` line was removed from
leaflet.js, because the map file is not included and ManifestStaticFilesStorage
fails in `collectstatic` on a reference to a missing file.
