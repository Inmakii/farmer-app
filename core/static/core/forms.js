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

    function init() {
        initPasswordToggles();
        initBusyForms();
        initLocationFields();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
