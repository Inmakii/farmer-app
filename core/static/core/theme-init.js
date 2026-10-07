// Applies the colour theme before the stylesheet is loaded to avoid a flash
// of the wrong theme. A saved choice takes precedence over the system setting.
(function () {
    "use strict";

    var root = document.documentElement;
    var theme = null;

    try {
        var stored = window.localStorage.getItem("farmer-theme");
        if (stored === "light" || stored === "dark") {
            theme = stored;
        }
    } catch (error) {
        // localStorage may be unavailable (private mode, blocked storage).
    }

    if (!theme) {
        var prefersDark = window.matchMedia
            && window.matchMedia("(prefers-color-scheme: dark)").matches;
        theme = prefersDark ? "dark" : "light";
    }

    root.setAttribute("data-theme", theme);
    root.style.colorScheme = theme;
})();
