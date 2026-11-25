"""Request log: a code for every request, one log line per request and the
activity trail of signed-in users (core.models.UserActivity).

Every request gets a short code (request.request_id, the X-Request-ID response
header). Log lines written while the request runs carry that code and the
user, so in the Render logs one search for "req=<code>" or "user=<number>"
shows everything about it, e.g.

    2026-11-24 20:15:01 INFO [req=3f9a1c2b7d user=42:jan] farmer.requests:
    POST /fields/add/ (core:field_create) 200 in 134 ms; form errors: house_number

Form values are never logged, only the names of fields with errors.
"""

import contextvars
import logging
import time
import uuid

from django.conf import settings

logger = logging.getLogger("farmer.requests")

_request_id = contextvars.ContextVar("request_id", default="-")
_user = contextvars.ContextVar("log_user", default="-")

# Not logged at all (static files are served earlier by WhiteNoise).
SKIP_PREFIXES = ("/static/", "/favicon.ico", "/robots.txt")
# Logged in the server log, but not stored as user activity (typing hints).
NO_STORE_PREFIXES = ("/geo/", "/log/client/", "/admin/jsi18n/")


class RequestContextFilter(logging.Filter):
    """Adds request_id and user to every log record (see LOGGING in settings)."""

    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = _request_id.get()
        if not hasattr(record, "user"):
            record.user = _user.get()
        return True


def user_label(user):
    if user is not None and getattr(user, "is_authenticated", False) and user.pk:
        return f"{user.pk}:{user.get_username()}"
    return "-"


def new_request_id():
    return uuid.uuid4().hex[:10]


def client_ip(request):
    # Behind Render's proxy the visitor's address is the first X-Forwarded-For entry.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded and getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def store_activity(**values):
    """Saves one activity row; a failure is logged and never breaks the request."""
    from .models import UserActivity

    try:
        UserActivity.objects.create(**values)
    except Exception:  # noqa: BLE001 - logging must not break the page
        logger.exception("Could not store user activity")


class RequestLogMiddleware:
    """Place right after WhiteNoise, so it covers all other middleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(SKIP_PREFIXES):
            return self.get_response(request)

        request.request_id = new_request_id()
        id_token = _request_id.set(request.request_id)
        user_token = _user.set("-")
        started = time.monotonic()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request.request_id
            self.log(request, response, started)
            return response
        finally:
            _request_id.reset(id_token)
            _user.reset(user_token)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # The user is known here (after AuthenticationMiddleware), so log lines
        # written by the view carry it too.
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            request._log_user_before = user  # still known after a logout
        _user.set(user_label(user))

    def process_exception(self, request, exception):
        request._log_error = f"{type(exception).__name__}: {exception}"[:300]

    def process_template_response(self, request, response):
        form = (response.context_data or {}).get("form") if hasattr(response, "context_data") else None
        errors = getattr(form, "errors", None) if form is not None else None
        if errors:
            request._log_form_errors = ", ".join(errors.keys())[:300]
        return response

    def log(self, request, response, started):
        duration_ms = int((time.monotonic() - started) * 1000)
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            user = getattr(request, "_log_user_before", None)  # e.g. the logout request
        if user is not None and not user.pk:
            user = None  # the account was deleted by this request
        _user.set(user_label(user))
        match = getattr(request, "resolver_match", None)
        view_name = (match.view_name if match else "")[:100]
        form_errors = getattr(request, "_log_form_errors", "")
        error = getattr(request, "_log_error", "")
        username = user.get_username() if user else ""
        if not user and view_name == "core:login" and request.method == "POST":
            username = request.POST.get("username", "").strip()[:150]

        message = "%s %s%s %s in %s ms"
        args = [
            request.method, request.get_full_path()[:500],
            f" ({view_name})" if view_name else "", response.status_code, duration_ms,
        ]
        if username and not user:
            message += "; login attempt: %s"
            args.append(username)
        if form_errors:
            message += "; form errors: %s"
            args.append(form_errors)
        if error:
            message += "; error: %s"
            args.append(error)
        message += "; ip %s"
        args.append(client_ip(request))
        level = logging.ERROR if response.status_code >= 500 else (
            logging.WARNING if response.status_code >= 400 and response.status_code != 404 else logging.INFO
        )
        logger.log(level, message, *args, extra={
            "request_id": request.request_id, "user": user_label(user),
        })

        if request.method in ("HEAD", "OPTIONS") or request.path.startswith(NO_STORE_PREFIXES):
            return
        if user is None and not username:
            return  # anonymous visitors are only in the server log
        store_activity(
            user=user, username=username, request_id=request.request_id,
            method=request.method[:8], path=request.get_full_path()[:500],
            view_name=view_name, status=response.status_code, duration_ms=duration_ms,
            form_errors=form_errors, error=error,
        )


# Browser errors -------------------------------------------------------------

CLIENT_ERRORS_PER_MINUTE = 20
CLIENT_ERROR_MAX_BYTES = 4096


def client_error_view(request):
    """Receives JavaScript errors sent by core/static/core/client-log.js
    (navigator.sendBeacon, so there is no CSRF token; the view only writes a
    log line and is limited per user or address)."""
    import json

    from django.core.cache import cache
    from django.http import HttpResponse, HttpResponseNotAllowed

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    user = request.user if request.user.is_authenticated else None
    key = "client-errors:" + (str(user.pk) if user else client_ip(request))
    cache.add(key, 0, 60)
    if cache.incr(key) > CLIENT_ERRORS_PER_MINUTE or len(request.body) > CLIENT_ERROR_MAX_BYTES:
        return HttpResponse(status=204)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=204)
    if not isinstance(data, dict):
        return HttpResponse(status=204)

    def text(name, limit):
        return " ".join(str(data.get(name, "")).split())[:limit]

    page = text("page", 500)
    if not page.startswith("/"):
        page = ""
    message = text("message", 200)
    where = text("source", 150)
    if data.get("line"):
        where += f":{text('line', 10)}"
    logger.warning("Browser error on %s: %s at %s", page or "?", message, where or "?")
    if user is not None:
        store_activity(
            user=user, username=user.get_username(), request_id=request.request_id,
            method="JS", path=page, view_name="", status=0,
            error=f"{message} ({where})"[:300],
        )
    return HttpResponse(status=204)
