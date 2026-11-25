// Sends JavaScript errors of this page to the server log (core.activity.client_error_view),
// so a problem a user reports can be found even when nothing failed on the server.
(function () {
    "use strict";
    var script = document.currentScript;
    var url = script && script.getAttribute("data-url");
    if (!url || !navigator.sendBeacon) {
        return;
    }
    var sent = 0;

    function send(message, source, line) {
        if (sent >= 5) {
            return;
        }
        sent += 1;
        var body = JSON.stringify({
            message: String(message || "").slice(0, 300),
            source: String(source || "").replace(location.origin, "").slice(0, 200),
            line: line || "",
            page: location.pathname + location.search
        });
        navigator.sendBeacon(url, new Blob([body], {type: "application/json"}));
    }

    window.addEventListener("error", function (event) {
        if (event.message) { // resource load errors have no message
            send(event.message, event.filename, event.lineno);
        }
    });
    window.addEventListener("unhandledrejection", function (event) {
        var reason = event.reason;
        send("Unhandled promise rejection: " + (reason && reason.message ? reason.message : reason), "", "");
    });
})();
