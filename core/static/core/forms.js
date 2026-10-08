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
                button.textContent = show ? "Ukryj" : "Pokaż";
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

    function init() {
        initPasswordToggles();
        initBusyForms();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
