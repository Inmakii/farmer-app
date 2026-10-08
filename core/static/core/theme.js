// Handles the light/dark theme toggle in the main navigation.
(function () {
    "use strict";

    var STORAGE_KEY = "farmer-theme";
    // Translated texts come from data-* attributes on the button; these are fallbacks.
    var DEFAULT_LABELS = {
        light: "Turn on dark mode",
        dark: "Turn on light mode"
    };
    var DEFAULT_ANNOUNCEMENTS = {
        light: "Light mode is on.",
        dark: "Dark mode is on."
    };
    var root = document.documentElement;

    function isValidTheme(value) {
        return value === "light" || value === "dark";
    }

    function readStoredTheme() {
        try {
            var value = window.localStorage.getItem(STORAGE_KEY);
            return isValidTheme(value) ? value : null;
        } catch (error) {
            return null;
        }
    }

    function storeTheme(theme) {
        try {
            window.localStorage.setItem(STORAGE_KEY, theme);
        } catch (error) {
            // The choice still applies to the current page.
        }
    }

    function currentTheme() {
        return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
    }

    function applyTheme(theme, button) {
        root.setAttribute("data-theme", theme);
        root.style.colorScheme = theme;
        if (button) {
            var label = button.getAttribute("data-label-" + theme) || DEFAULT_LABELS[theme];
            button.setAttribute("aria-label", label);
            button.setAttribute("title", label);
        }
    }

    function init() {
        var button = document.getElementById("theme-toggle");
        var status = document.getElementById("theme-status");
        if (!button) {
            return;
        }

        applyTheme(currentTheme(), button);

        button.addEventListener("click", function () {
            var nextTheme = currentTheme() === "dark" ? "light" : "dark";
            applyTheme(nextTheme, button);
            storeTheme(nextTheme);
            if (status) {
                status.textContent = button.getAttribute("data-announce-" + nextTheme)
                    || DEFAULT_ANNOUNCEMENTS[nextTheme];
            }
        });

        if (window.matchMedia) {
            var query = window.matchMedia("(prefers-color-scheme: dark)");
            var onSystemChange = function (event) {
                if (!readStoredTheme()) {
                    applyTheme(event.matches ? "dark" : "light", button);
                }
            };
            if (query.addEventListener) {
                query.addEventListener("change", onSystemChange);
            } else if (query.addListener) {
                query.addListener(onSystemChange);
            }
        }

        window.addEventListener("storage", function (event) {
            if (event.key === STORAGE_KEY && isValidTheme(event.newValue)) {
                applyTheme(event.newValue, button);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
