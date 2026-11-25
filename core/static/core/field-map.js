// Field map (Leaflet, vendored in core/vendor/leaflet).
//  - [data-field-map="pick"] in the field form: search for an address or locality,
//    "my location", click the map or drag the marker; latitude and longitude
//    inputs are filled in. Shown only for the "point on a map" method.
//  - [data-field-map="view"] on the field page: the saved point.
// Tiles: OpenStreetMap and the GUGiK orthophoto (both allowed in the CSP img-src).
(function () {
    "use strict";

    var POLAND = [52.07, 19.48];
    var METHODS_WITH_MAP = ["MAP"];

    function layers(root) {
        // OSM blocks tile requests without a Referer (403 "Access blocked"). The site's
        // Referrer-Policy is same-origin, so the tiles send just the site's origin.
        var map = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            referrerPolicy: "strict-origin-when-cross-origin",
            maxZoom: 19,
            attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a>"
        });
        // GUGiK orthophoto as cached WMTS tiles; its EPSG:3857 grid is the usual z/x/y one.
        var photo = L.tileLayer("https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMTS/StandardResolution" +
            "?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTOFOTOMAPA&STYLE=default" +
            "&FORMAT=image/jpeg&TILEMATRIXSET=EPSG:3857&TILEMATRIX=EPSG:3857:{z}&TILEROW={y}&TILECOL={x}", {
            maxZoom: 19,
            attribution: "Ortofotomapa &copy; <a href=\"https://www.geoportal.gov.pl/\">GUGiK</a>"
        });
        var named = {};
        named[root.getAttribute("data-label-map") || "Map"] = map;
        named[root.getAttribute("data-label-photo") || "Aerial photo"] = photo;
        return {map: map, photo: photo, named: named};
    }

    function markerIcon(root) {
        return L.icon({
            iconUrl: root.getAttribute("data-icon"),
            iconRetinaUrl: root.getAttribute("data-icon-2x"),
            shadowUrl: root.getAttribute("data-icon-shadow"),
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            shadowSize: [41, 41]
        });
    }

    function parseCoord(value, limit) {
        var number = parseFloat(String(value || "").replace(",", "."));
        return isFinite(number) && Math.abs(number) <= limit ? number : null;
    }

    function createMap(root, center, zoom, options) {
        var canvas = root.querySelector("[data-map-canvas]");
        var tiles = layers(root);
        var map = L.map(canvas, options || {}).setView(center, zoom);
        tiles.map.addTo(map);
        L.control.layers(tiles.named, null, {collapsed: false}).addTo(map);
        return {map: map, tiles: tiles};
    }

    function showPhoto(created) {
        if (!created.map.hasLayer(created.tiles.photo)) {
            created.map.removeLayer(created.tiles.map);
            created.tiles.photo.addTo(created.map);
        }
    }

    function initView(root) {
        var lat = parseCoord(root.getAttribute("data-lat"), 90);
        var lng = parseCoord(root.getAttribute("data-lng"), 180);
        if (lat === null || lng === null) {
            return;
        }
        var created = createMap(root, [lat, lng], 16, {scrollWheelZoom: false});
        showPhoto(created);
        L.marker([lat, lng], {icon: markerIcon(root), keyboard: false}).addTo(created.map);
    }

    function initPicker(root) {
        var form = root.closest("form");
        if (!form || !form.elements.latitude || !form.elements.longitude) {
            return;
        }
        var latInput = form.elements.latitude;
        var lngInput = form.elements.longitude;
        var method = form.querySelector("select[data-location-method]");
        var status = root.querySelector("[data-map-status]");
        var search = root.querySelector("[data-map-search]");
        var created = null;
        var marker = null;

        function say(key, state) {
            if (status) {
                status.textContent = root.getAttribute(key) || "";
                status.setAttribute("data-state", state || "");
            }
        }

        function current() {
            var lat = parseCoord(latInput.value, 90);
            var lng = parseCoord(lngInput.value, 180);
            return lat === null || lng === null ? null : L.latLng(lat, lng);
        }

        function writeInputs(latlng) {
            latlng = latlng.wrap();
            latInput.value = latlng.lat.toFixed(6);
            lngInput.value = latlng.lng.toFixed(6);
            [latInput, lngInput].forEach(function (input) {
                input.dispatchEvent(new Event("input", {bubbles: true}));
                input.dispatchEvent(new Event("change", {bubbles: true}));
            });
        }

        function placeMarker(latlng) {
            if (marker) {
                marker.setLatLng(latlng);
                return;
            }
            marker = L.marker(latlng, {icon: markerIcon(root), draggable: true, autoPan: true})
                .addTo(created.map);
            marker.on("dragend", function () {
                writeInputs(marker.getLatLng());
                say("data-msg-picked");
            });
        }

        function pick(latlng) {
            placeMarker(latlng);
            writeInputs(latlng);
            say("data-msg-picked");
        }

        function ensureMap() {
            if (created) {
                created.map.invalidateSize();
                return;
            }
            var point = current();
            created = createMap(root, point || POLAND, point ? 16 : 6);
            if (point) {
                showPhoto(created);
                placeMarker(point);
            }
            created.map.on("click", function (event) {
                pick(event.latlng);
            });
        }

        function update() {
            var show = METHODS_WITH_MAP.indexOf(method ? method.value : "") !== -1;
            root.hidden = !show;
            if (show) {
                ensureMap();
            }
        }

        // Coordinates typed by hand move the marker.
        [latInput, lngInput].forEach(function (input) {
            input.addEventListener("change", function () {
                var point = current();
                if (created && point && (!marker || !marker.getLatLng().equals(point))) {
                    placeMarker(point);
                    created.map.panTo(point);
                }
            });
        });

        function runSearch() {
            var query = search.value.trim();
            if (query.length < 3) {
                search.focus();
                return;
            }
            say("data-msg-searching");
            fetch(root.getAttribute("data-search-url") + "?q=" + encodeURIComponent(query), {
                credentials: "same-origin",
                headers: {"Accept": "application/json"}
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return {ok: response.ok, data: data};
                    });
                })
                .then(function (answer) {
                    var found = (answer.data.results || [])[0];
                    if (!answer.ok || answer.data.available === false) {
                        say("data-msg-unavailable", "error");
                    } else if (!found) {
                        say("data-msg-not-found", "error");
                    } else {
                        showPhoto(created);
                        created.map.setView([parseFloat(found.latitude), parseFloat(found.longitude)], found.zoom || 15);
                        say("data-msg-found");
                    }
                })
                .catch(function () {
                    say("data-msg-unavailable", "error");
                });
        }

        if (search) {
            search.addEventListener("keydown", function (event) {
                if (event.key === "Enter") {
                    event.preventDefault(); // Enter here searches; it must not save the form.
                    runSearch();
                }
            });
            root.querySelector("[data-map-search-button]").addEventListener("click", runSearch);
        }

        var locate = root.querySelector("[data-map-locate]");
        if (locate) {
            if (!("geolocation" in navigator)) {
                locate.hidden = true;
            }
            locate.addEventListener("click", function () {
                say("data-msg-locating");
                navigator.geolocation.getCurrentPosition(function (position) {
                    var latlng = L.latLng(position.coords.latitude, position.coords.longitude);
                    showPhoto(created);
                    created.map.setView(latlng, 17);
                    pick(latlng);
                }, function () {
                    say("data-msg-no-location", "error");
                }, {enableHighAccuracy: true, timeout: 15000, maximumAge: 60000});
            });
        }

        if (method) {
            method.addEventListener("change", update);
        }
        update();
    }

    function init() {
        if (typeof L === "undefined") {
            return;
        }
        Array.prototype.forEach.call(document.querySelectorAll("[data-field-map]"), function (root) {
            if (root.getAttribute("data-field-map") === "pick") {
                initPicker(root);
            } else {
                initView(root);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
