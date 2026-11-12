// Forms: show/hide password and a busy state on submit.
(function () {
    "use strict";

    function initPasswordToggles() {
        var buttons = document.querySelectorAll("[data-password-toggle]");
        Array.prototype.forEach.call(buttons, function (button) {
            var input = document.getElementById(button.getAttribute("aria-controls"));
            if (!input) {
                return;
            }
            button.addEventListener("click", function () {
                var show = input.type === "password";
                input.type = show ? "text" : "password";
                button.textContent = show
                    ? button.getAttribute("data-hide-label") || "Hide"
                    : button.getAttribute("data-show-label") || "Show";
                button.setAttribute("aria-pressed", show ? "true" : "false");
            });
        });
    }

    function initBusyForms() {
        var forms = document.querySelectorAll("[data-busy-form]");
        Array.prototype.forEach.call(forms, function (form) {
            form.addEventListener("submit", function () {
                var button = form.querySelector("[data-busy-label]");
                if (!button || button.getAttribute("aria-busy") === "true") {
                    return;
                }
                // Passwords go back to hidden so the browser does not store them as plain text.
                Array.prototype.forEach.call(form.querySelectorAll("[data-password-toggle]"), function (toggle) {
                    var input = document.getElementById(toggle.getAttribute("aria-controls"));
                    if (input) {
                        input.type = "password";
                    }
                });
                button.setAttribute("data-idle-label", button.textContent);
                button.setAttribute("aria-busy", "true");
                button.textContent = button.getAttribute("data-busy-label");
            });
        });

        // Back/forward cache restores the page as it was, so undo the busy state.
        window.addEventListener("pageshow", function (event) {
            if (!event.persisted) {
                return;
            }
            Array.prototype.forEach.call(document.querySelectorAll("[data-busy-label][aria-busy='true']"), function (button) {
                button.removeAttribute("aria-busy");
                button.textContent = button.getAttribute("data-idle-label");
            });
        });
    }

    // Field form: after "How the location is given" only the fields of the chosen
    // method are shown. A field that already had a value or an error stays visible,
    // so saved data is never hidden. Hidden fields are disabled and not sent.
    function initLocationFields() {
        var selects = document.querySelectorAll("select[data-location-method]");
        Array.prototype.forEach.call(selects, function (select) {
            var form = select.form;
            if (!form) {
                return;
            }
            var inputs = form.querySelectorAll("[data-location-for]");

            function update() {
                Array.prototype.forEach.call(inputs, function (input) {
                    var wrapper = input.closest(".field");
                    if (!wrapper) {
                        return;
                    }
                    var methods = input.getAttribute("data-location-for").split(" ");
                    var show = methods.indexOf(select.value) !== -1
                        || input.defaultValue.trim() !== ""
                        || wrapper.classList.contains("has-error");
                    wrapper.hidden = !show;
                    input.disabled = !show;
                });
            }

            select.addEventListener("change", update);
            update();
        });
    }

    // Field form: hints for locality, street and house number from this site's
    // /geo/ endpoints (national address register). Choosing a locality and street
    // fills the hidden codes the server uses to look up the address or parcel.
    function initGeoHints() {
        var form = document.querySelector("form[data-geo-localities]");
        if (!form) {
            return;
        }
        var locality = form.querySelector("[data-geo='locality']");
        var street = form.querySelector("[data-geo='street']");
        var number = form.querySelector("[data-geo='number']");
        var address = form.elements.address;
        var hidden = {
            sym: form.elements.locality_sym,
            name: form.elements.locality_name,
            commune: form.elements.locality_commune,
            streetSym: form.elements.street_sym
        };
        if (!locality || !hidden.sym) {
            return;
        }

        function attachList(input) {
            var list = document.createElement("datalist");
            list.id = "geo-list-" + input.name;
            input.setAttribute("list", list.id);
            input.parentNode.appendChild(list);
            return list;
        }

        function fill(list, items) {
            list.textContent = "";
            items.forEach(function (item) {
                var option = document.createElement("option");
                option.value = item.label;
                list.appendChild(option);
            });
        }

        function request(url, params, callback) {
            var query = Object.keys(params).map(function (key) {
                return encodeURIComponent(key) + "=" + encodeURIComponent(params[key]);
            }).join("&");
            fetch(url + "?" + query, {credentials: "same-origin", headers: {"Accept": "application/json"}})
                .then(function (response) { return response.ok ? response.json() : {results: []}; })
                .then(function (data) { callback(data.results || []); })
                .catch(function () { callback([]); });
        }

        function debounce(fn) {
            var timer;
            return function () {
                clearTimeout(timer);
                timer = setTimeout(fn, 250);
            };
        }

        var lists = {locality: attachList(locality)};
        var found = {locality: [], street: []};
        if (street) {
            lists.street = attachList(street);
        }
        if (number) {
            lists.number = attachList(number);
        }

        function updateAddressPreview() {
            if (!address || !number || !number.value.trim() || !hidden.name.value) {
                return;
            }
            var first = street && street.value.trim()
                ? street.value.trim() + " " + number.value.trim()
                : hidden.name.value + " " + number.value.trim();
            address.value = first + ", " + hidden.name.value;
        }

        function loadNumbers() {
            if (!number) {
                return;
            }
            var params = {sym: hidden.sym.value};
            if (hidden.streetSym && hidden.streetSym.value) {
                params.sym_ul = hidden.streetSym.value;
            }
            request(form.getAttribute("data-geo-numbers"), params, function (numbers) {
                fill(lists.number, numbers.map(function (n) { return {label: n}; }));
            });
        }

        function chooseLocality() {
            var match = found.locality.filter(function (item) { return item.label === locality.value; })[0];
            var changed = (match ? match.sym : "") !== hidden.sym.value;
            hidden.sym.value = match ? match.sym : "";
            hidden.name.value = match ? match.name : "";
            hidden.commune.value = match ? match.commune : "";
            if (changed) {
                if (street) { street.value = ""; }
                if (hidden.streetSym) { hidden.streetSym.value = ""; }
                if (number) { number.value = ""; }
                if (match) { loadNumbers(); }
            }
        }

        locality.addEventListener("input", debounce(function () {
            chooseLocality();
            if (hidden.sym.value || locality.value.trim().length < 2) {
                return;
            }
            request(form.getAttribute("data-geo-localities"), {q: locality.value.trim()}, function (items) {
                found.locality = items;
                fill(lists.locality, items);
                chooseLocality();
            });
        }));
        locality.addEventListener("change", chooseLocality);

        if (street) {
            var chooseStreet = function () {
                var match = found.street.filter(function (item) { return item.label === street.value; })[0];
                var sym = match ? match.sym_ul : "";
                if (hidden.streetSym && sym !== hidden.streetSym.value) {
                    hidden.streetSym.value = sym;
                    if (number) { number.value = ""; }
                    loadNumbers();
                }
            };
            street.addEventListener("input", debounce(function () {
                chooseStreet();
                if (!hidden.sym.value) {
                    return;
                }
                request(form.getAttribute("data-geo-streets"), {sym: hidden.sym.value, q: street.value.trim()}, function (items) {
                    found.street = items;
                    fill(lists.street, items);
                    chooseStreet();
                });
            }));
            street.addEventListener("change", chooseStreet);
        }
        if (number) {
            number.addEventListener("change", updateAddressPreview);
        }
    }

    function init() {
        initPasswordToggles();
        initBusyForms();
        initLocationFields();
        initGeoHints();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
