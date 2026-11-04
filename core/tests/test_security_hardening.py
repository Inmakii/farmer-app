"""Tests for the application security hardening (settings, headers, cookies and CSP)."""

from datetime import date
from decimal import Decimal
from html.parser import HTMLParser

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.csp import build_policy

from ..models import Crop, Cultivation, ErrorReport, Field, FieldWork, Harvest, Spraying
from .test_database_config import MYSQL_ENV, load_settings

LOCAL_ENV = {**MYSQL_ENV, "DJANGO_DEBUG": "True"}
PRODUCTION_ENV = {**MYSQL_ENV, "DJANGO_DEBUG": "False"}
# Header tests pin the CSP mode explicitly so they do not depend on DJANGO_DEBUG in the local .env.
PRODUCTION_CSP = load_settings(PRODUCTION_ENV)["SECURE_CSP"]
ENFORCED_CSP = override_settings(SECURE_CSP=PRODUCTION_CSP, SECURE_CSP_REPORT_ONLY={})
REPORT_ONLY_CSP = override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=PRODUCTION_CSP)
JSON_RENDERER = "rest_framework.renderers.JSONRenderer"
BROWSABLE_RENDERER = "rest_framework.renderers.BrowsableAPIRenderer"
GOOGLE_FONTS_CSS = "https://fonts.googleapis.com"
GOOGLE_FONTS_FILES = "https://fonts.gstatic.com"


def parse_csp(header):
    """Return the CSP header as a {directive: [sources]} dictionary."""
    policy = {}
    for part in header.split(";"):
        tokens = part.split()
        if tokens:
            policy[tokens[0]] = tokens[1:]
    return policy


class SecuritySettingsParsingTests(SimpleTestCase):
    """config/settings.py is executed with a controlled environment (no .env)."""

    def test_local_defaults_keep_http_development_working(self):
        loaded = load_settings(LOCAL_ENV)

        self.assertTrue(loaded["DEBUG"])
        self.assertFalse(loaded["SECURE_SSL_REDIRECT"])
        self.assertFalse(loaded["SESSION_COOKIE_SECURE"])
        self.assertFalse(loaded["CSRF_COOKIE_SECURE"])
        self.assertEqual(loaded["SECURE_HSTS_SECONDS"], 0)
        self.assertFalse(loaded["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertFalse(loaded["SECURE_HSTS_PRELOAD"])
        self.assertEqual(loaded["CSRF_TRUSTED_ORIGINS"], [])
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", loaded)

    def test_production_flags_are_read_from_the_environment(self):
        loaded = load_settings(
            {
                **MYSQL_ENV,
                "DJANGO_DEBUG": "False",
                "DJANGO_SECURE_SSL_REDIRECT": "true",
                "DJANGO_SESSION_COOKIE_SECURE": "1",
                "DJANGO_CSRF_COOKIE_SECURE": "yes",
                "DJANGO_SECURE_HSTS_SECONDS": "3600",
            }
        )

        self.assertFalse(loaded["DEBUG"])
        self.assertTrue(loaded["SECURE_SSL_REDIRECT"])
        self.assertTrue(loaded["SESSION_COOKIE_SECURE"])
        self.assertTrue(loaded["CSRF_COOKIE_SECURE"])
        self.assertEqual(loaded["SECURE_HSTS_SECONDS"], 3600)
        self.assertFalse(loaded["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertFalse(loaded["SECURE_HSTS_PRELOAD"])

    def test_full_hsts_preload_configuration_is_accepted(self):
        loaded = load_settings(
            {
                **MYSQL_ENV,
                "DJANGO_SECURE_HSTS_SECONDS": "31536000",
                "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS": "on",
                "DJANGO_SECURE_HSTS_PRELOAD": "on",
            }
        )

        self.assertEqual(loaded["SECURE_HSTS_SECONDS"], 31536000)
        self.assertTrue(loaded["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertTrue(loaded["SECURE_HSTS_PRELOAD"])

    def test_invalid_boolean_values_are_rejected(self):
        variables = (
            "DJANGO_DEBUG",
            "DJANGO_SECURE_SSL_REDIRECT",
            "DJANGO_SESSION_COOKIE_SECURE",
            "DJANGO_CSRF_COOKIE_SECURE",
            "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
            "DJANGO_SECURE_HSTS_PRELOAD",
        )
        for name in variables:
            for value in ("maybe", "Tru", "2", "enabled"):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesMessage(ImproperlyConfigured, name):
                        load_settings({**MYSQL_ENV, "DJANGO_SECURE_HSTS_SECONDS": "3600", name: value})

    def test_invalid_hsts_seconds_are_rejected(self):
        for value in ("-1", "abc", "1.5", "1e3", "3600s", "+60", "36 00"):
            with self.subTest(value=value):
                with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECURE_HSTS_SECONDS"):
                    load_settings({**MYSQL_ENV, "DJANGO_SECURE_HSTS_SECONDS": value})

    def test_non_ascii_digits_are_rejected_without_value_error(self):
        # "²" passes str.isdigit() but int() fails on it; full-width and Arabic-Indic digits pass both.
        for value in ("²", "３６００", "٣٦٠٠"):
            with self.subTest(value=value):
                with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECURE_HSTS_SECONDS"):
                    load_settings({**MYSQL_ENV, "DJANGO_SECURE_HSTS_SECONDS": value})

    def test_extremely_long_number_is_rejected_without_value_error(self):
        # More digits than int() accepts by default (4300) must still give a configuration error.
        for value in ("9" * 5000, "1" * 11):
            with self.subTest(length=len(value)):
                with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECURE_HSTS_SECONDS"):
                    load_settings({**MYSQL_ENV, "DJANGO_SECURE_HSTS_SECONDS": value})

    def test_valid_hsts_seconds_are_accepted(self):
        for value, expected in (("0", 0), ("31536000", 31536000), (" 300 ", 300)):
            with self.subTest(value=value):
                loaded = load_settings({**MYSQL_ENV, "DJANGO_SECURE_HSTS_SECONDS": value})
                self.assertEqual(loaded["SECURE_HSTS_SECONDS"], expected)

    def test_ssl_redirect_makes_cookies_secure_by_default(self):
        loaded = load_settings({**PRODUCTION_ENV, "DJANGO_SECURE_SSL_REDIRECT": "True"})

        self.assertTrue(loaded["SECURE_SSL_REDIRECT"])
        self.assertTrue(loaded["SESSION_COOKIE_SECURE"])
        self.assertTrue(loaded["CSRF_COOKIE_SECURE"])

    def test_ssl_redirect_with_insecure_cookies_is_rejected(self):
        for name in ("DJANGO_SESSION_COOKIE_SECURE", "DJANGO_CSRF_COOKIE_SECURE"):
            with self.subTest(name=name):
                with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECURE_SSL_REDIRECT"):
                    load_settings({**PRODUCTION_ENV, "DJANGO_SECURE_SSL_REDIRECT": "True", name: "False"})

    def test_secure_cookies_without_ssl_redirect_are_allowed(self):
        loaded = load_settings(
            {
                **PRODUCTION_ENV,
                "DJANGO_SESSION_COOKIE_SECURE": "True",
                "DJANGO_CSRF_COOKIE_SECURE": "True",
            }
        )

        self.assertFalse(loaded["SECURE_SSL_REDIRECT"])
        self.assertTrue(loaded["SESSION_COOKIE_SECURE"])
        self.assertTrue(loaded["CSRF_COOKIE_SECURE"])

    def test_production_enforces_csp_and_serves_json_only(self):
        loaded = load_settings(PRODUCTION_ENV)

        self.assertEqual(loaded["SECURE_CSP"], loaded["_CSP_POLICY"])
        self.assertEqual(loaded["SECURE_CSP_REPORT_ONLY"], {})
        self.assertEqual(loaded["REST_FRAMEWORK"]["DEFAULT_RENDERER_CLASSES"], (JSON_RENDERER,))

    def test_development_uses_report_only_csp_and_browsable_api(self):
        loaded = load_settings(LOCAL_ENV)

        self.assertEqual(loaded["SECURE_CSP"], {})
        self.assertEqual(loaded["SECURE_CSP_REPORT_ONLY"], loaded["_CSP_POLICY"])
        self.assertEqual(
            loaded["REST_FRAMEWORK"]["DEFAULT_RENDERER_CLASSES"], (JSON_RENDERER, BROWSABLE_RENDERER)
        )

    def test_unset_debug_means_production_csp(self):
        loaded = load_settings(MYSQL_ENV)

        self.assertFalse(loaded["DEBUG"])
        self.assertEqual(loaded["SECURE_CSP"], loaded["_CSP_POLICY"])
        self.assertEqual(loaded["SECURE_CSP_REPORT_ONLY"], {})

    def test_hsts_options_require_a_positive_max_age(self):
        for name in ("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "DJANGO_SECURE_HSTS_PRELOAD"):
            with self.subTest(name=name):
                with self.assertRaises(ImproperlyConfigured):
                    load_settings({**MYSQL_ENV, name: "True"})

    def test_hsts_preload_requires_subdomains_and_one_year(self):
        invalid = (
            {"DJANGO_SECURE_HSTS_SECONDS": "31536000", "DJANGO_SECURE_HSTS_PRELOAD": "True"},
            {
                "DJANGO_SECURE_HSTS_SECONDS": "3600",
                "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS": "True",
                "DJANGO_SECURE_HSTS_PRELOAD": "True",
            },
        )
        for env in invalid:
            with self.subTest(env=env):
                with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECURE_HSTS_PRELOAD"):
                    load_settings({**MYSQL_ENV, **env})

    def test_csrf_trusted_origins_are_parsed(self):
        loaded = load_settings(
            {
                **MYSQL_ENV,
                "DJANGO_CSRF_TRUSTED_ORIGINS": (
                    " https://farm.example.com, https://*.example.org/ ,,http://localhost:8000"
                ),
            }
        )

        self.assertEqual(
            loaded["CSRF_TRUSTED_ORIGINS"],
            ["https://farm.example.com", "https://*.example.org", "http://localhost:8000"],
        )

    def test_invalid_csrf_trusted_origins_are_rejected(self):
        for value in (
            "farm.example.com",
            "https://",
            "https://*",
            "*",
            "ftp://farm.example.com",
            "https://farm.example.com/path",
            "https://farm.example.com?next=1",
            "https://farm.example.com#top",
            "https://user@farm.example.com",
            "https://farm.example.com:port",
            "https://farm.example.com, example.org",
        ):
            with self.subTest(value=value):
                with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_CSRF_TRUSTED_ORIGINS"):
                    load_settings({**MYSQL_ENV, "DJANGO_CSRF_TRUSTED_ORIGINS": value})


class MiddlewareConfigurationTests(SimpleTestCase):
    def test_security_middleware_order(self):
        middleware = settings.MIDDLEWARE
        position = {name: middleware.index(name) for name in middleware}

        self.assertEqual(middleware[0], "django.middleware.security.SecurityMiddleware")
        self.assertEqual(middleware[1], "django.middleware.csp.ContentSecurityPolicyMiddleware")
        self.assertLess(
            position["django.contrib.sessions.middleware.SessionMiddleware"],
            position["django.middleware.csrf.CsrfViewMiddleware"],
        )
        self.assertLess(
            position["django.middleware.csrf.CsrfViewMiddleware"],
            position["django.contrib.auth.middleware.AuthenticationMiddleware"],
        )
        self.assertIn("django.middleware.clickjacking.XFrameOptionsMiddleware", middleware)

    def test_cookie_and_header_settings(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "same-origin")
        self.assertEqual(settings.SECURE_CROSS_ORIGIN_OPENER_POLICY, "same-origin")


@ENFORCED_CSP
class SecurityHeadersTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("core:home"))

    def test_page_is_served(self):
        self.assertEqual(self.response.status_code, 200)

    def test_basic_security_headers(self):
        self.assertEqual(self.response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(self.response.headers["Referrer-Policy"], "same-origin")
        self.assertEqual(self.response.headers["Cross-Origin-Opener-Policy"], "same-origin")

    def test_csp_header_restricts_sources(self):
        self.assertNotIn("Content-Security-Policy-Report-Only", self.response.headers)
        policy = parse_csp(self.response.headers["Content-Security-Policy"])

        self.assertEqual(policy["default-src"], ["'self'"])
        self.assertEqual(policy["script-src"], ["'self'"])
        self.assertEqual(policy["style-src"], ["'self'", GOOGLE_FONTS_CSS])
        self.assertEqual(policy["font-src"], ["'self'", GOOGLE_FONTS_FILES])
        self.assertEqual(policy["img-src"], ["'self'", "data:"])
        self.assertEqual(policy["object-src"], ["'none'"])
        self.assertEqual(policy["base-uri"], ["'self'"])
        self.assertEqual(policy["form-action"], ["'self'"])
        self.assertEqual(policy["frame-ancestors"], ["'none'"])

    def test_csp_has_no_broad_or_unsafe_sources(self):
        policy = parse_csp(self.response.headers["Content-Security-Policy"])
        for directive, sources in policy.items():
            for source in sources:
                with self.subTest(directive=directive, source=source):
                    self.assertNotIn("*", source)
                    self.assertNotIn(source, ("'unsafe-eval'", "'unsafe-inline'", "'unsafe-hashes'"))
                    self.assertNotIn(source, ("http:", "https:", "blob:", "filesystem:"))
                    if source == "data:":
                        self.assertEqual(directive, "img-src")

    def test_csp_is_also_sent_on_admin_pages(self):
        response = self.client.get(reverse("admin:login"))

        self.assertIn("Content-Security-Policy", response.headers)

    def test_csrf_failure_page_is_covered_by_enforced_csp(self):
        response = Client(enforce_csrf_checks=True).post(reverse("core:login"), {})

        self.assertEqual(response.status_code, 403)
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertNotIn("Content-Security-Policy-Report-Only", response.headers)


@REPORT_ONLY_CSP
class DevelopmentCspTests(TestCase):
    """With DEBUG=True the same policy is only reported, so Django's own pages keep their styles."""

    def test_pages_get_report_only_header_with_the_same_policy(self):
        response = self.client.get(reverse("core:home"))

        self.assertNotIn("Content-Security-Policy", response.headers)
        self.assertEqual(
            parse_csp(response.headers["Content-Security-Policy-Report-Only"]),
            parse_csp(build_policy(PRODUCTION_CSP)),
        )

    def test_csrf_failure_page_is_not_blocked(self):
        response = Client(enforce_csrf_checks=True).post(reverse("core:login"), {})

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Content-Security-Policy", response.headers)
        self.assertIn("Content-Security-Policy-Report-Only", response.headers)

    def test_hsts_is_not_sent_by_default(self):
        response = self.client.get(reverse("core:home"), secure=True)

        self.assertNotIn("Strict-Transport-Security", response.headers)

    @override_settings(SECURE_HSTS_SECONDS=3600)
    def test_hsts_header_uses_configured_max_age_only(self):
        # SecurityMiddleware reads its settings when it is created, so a new client is needed.
        response = Client().get(reverse("core:home"), secure=True)

        self.assertEqual(response.headers["Strict-Transport-Security"], "max-age=3600")


class HttpsRedirectTests(TestCase):
    def test_local_configuration_does_not_redirect_to_https(self):
        loaded = load_settings(LOCAL_ENV)

        with override_settings(SECURE_SSL_REDIRECT=loaded["SECURE_SSL_REDIRECT"]):
            response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_production_configuration_redirects_http_to_https(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["Location"], "https://testserver/")

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_https_request_is_not_redirected(self):
        response = self.client.get(reverse("core:home"), secure=True)

        self.assertEqual(response.status_code, 200)


class CookieSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "StrongPass!2026"
        self.user = get_user_model().objects.create_user(
            username="cookie_owner", password=self.password
        )

    def tearDown(self):
        cache.clear()

    def login(self, **extra):
        self.client.get(reverse("core:login"), **extra)
        return self.client.post(
            reverse("core:login"),
            {"username": self.user.username, "password": self.password},
            **extra,
        )

    @override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_production_settings_mark_cookies_secure(self):
        response = self.login(secure=True)

        self.assertRedirects(response, reverse("core:home"), fetch_redirect_response=False)
        session_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]
        csrf_cookie = self.client.cookies[settings.CSRF_COOKIE_NAME]
        self.assertTrue(session_cookie["secure"])
        self.assertTrue(session_cookie["httponly"])
        self.assertEqual(session_cookie["samesite"], "Lax")
        self.assertTrue(csrf_cookie["secure"])
        self.assertEqual(csrf_cookie["samesite"], "Lax")

    @override_settings(SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
    def test_local_settings_keep_cookies_usable_over_http(self):
        response = self.login()

        self.assertRedirects(response, reverse("core:home"), fetch_redirect_response=False)
        self.assertFalse(self.client.cookies[settings.SESSION_COOKIE_NAME]["secure"])
        self.assertTrue(self.client.cookies[settings.SESSION_COOKIE_NAME]["httponly"])
        self.assertFalse(self.client.cookies[settings.CSRF_COOKIE_NAME]["secure"])


class ExistingProtectionTests(TestCase):
    """The hardening must not weaken the CSRF, authentication and ownership checks."""

    def setUp(self):
        cache.clear()
        self.password = "StrongPass!2026"
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="guarded_user", password=self.password)
        self.other_user = user_model.objects.create_user(username="other_user", password=self.password)
        self.other_field = Field.objects.create(
            owner=self.other_user,
            name="Cudze pole",
            area_ha=Decimal("1.00"),
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Toruń",
        )

    def tearDown(self):
        cache.clear()

    def test_post_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        self.assertEqual(client.post(reverse("core:logout")).status_code, 403)
        self.assertEqual(
            client.post(reverse("core:field_delete", kwargs={"pk": self.other_field.pk})).status_code,
            403,
        )
        self.assertTrue(Field.objects.filter(pk=self.other_field.pk).exists())

    def test_logout_rejects_get(self):
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(reverse("core:logout")).status_code, 405)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("core:field_list"))

        self.assertRedirects(
            response, f"{reverse('core:login')}?next={reverse('core:field_list')}"
        )

    def test_other_users_data_returns_404(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:field_detail", kwargs={"pk": self.other_field.pk}))

        self.assertEqual(response.status_code, 404)

    @override_settings(ALLOWED_HOSTS=["app.internal"], CSRF_TRUSTED_ORIGINS=["https://farm.example.com"])
    def test_https_post_checks_origin_against_trusted_origins(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST="app.internal")
        client.get(reverse("core:login"), secure=True)
        data = {
            "username": self.user.username,
            "password": self.password,
            "csrfmiddlewaretoken": client.cookies[settings.CSRF_COOKIE_NAME].value,
        }

        untrusted = client.post(
            reverse("core:login"), data, secure=True, HTTP_ORIGIN="https://evil.example.com"
        )
        trusted = client.post(
            reverse("core:login"), data, secure=True, HTTP_ORIGIN="https://farm.example.com"
        )

        self.assertEqual(untrusted.status_code, 403)
        self.assertEqual(trusted.status_code, 302)


class InlineCodeCollector(HTMLParser):
    """Collect markup that the CSP would block or that loads disallowed sources."""

    @staticmethod
    def is_same_origin(url):
        """A root-relative URL such as /static/... or /admin/jsi18n/ is allowed by 'self'."""
        return url.startswith("/") and not url.startswith("//")

    def __init__(self):
        super().__init__()
        self.problems = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for name, value in attrs:
            if name == "style":
                self.problems.append(f"style attribute on <{tag}>")
            if name.startswith("on"):
                self.problems.append(f"inline event handler {name} on <{tag}>")
            if name in ("href", "src", "action") and (value or "").strip().lower().startswith("javascript:"):
                self.problems.append(f"javascript: URL in <{tag} {name}>")
        if tag == "style":
            self.problems.append("inline <style>")
        elif tag == "script":
            src = attributes.get("src")
            if not src:
                # json_script data blocks are not executed, so the CSP does not apply to them.
                if attributes.get("type") != "application/json":
                    self.problems.append("inline <script>")
            elif not self.is_same_origin(src):
                self.problems.append(f"script from disallowed source {src}")
        elif tag == "link" and "stylesheet" in (attributes.get("rel") or "").split():
            href = attributes.get("href", "")
            if not (self.is_same_origin(href) or href.startswith(GOOGLE_FONTS_CSS + "/")):
                self.problems.append(f"stylesheet from disallowed source {href}")
        elif tag == "img":
            src = attributes.get("src", "")
            if not (self.is_same_origin(src) or src.startswith("data:")):
                self.problems.append(f"image from disallowed source {src}")
        elif tag in ("iframe", "object", "embed"):
            self.problems.append(f"<{tag}> element")
        elif tag == "form":
            action = attributes.get("action") or ""
            if action.startswith(("http:", "https:", "//")):
                self.problems.append(f"form posting to another origin {action}")


@ENFORCED_CSP
class CspCompatibilityTests(TestCase):
    """Rendered pages must work under the CSP: no inline code and only allowed sources."""

    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="csp_owner", password="StrongPass!2026")
        self.field = Field.objects.create(
            owner=self.user,
            name="Pole testowe",
            area_ha=Decimal("4.00"),
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.GPS,
            latitude=Decimal("53.100000"),
            longitude=Decimal("18.000000"),
        )
        crop = Crop.objects.create(name="Owies")
        self.cultivation = Cultivation.objects.create(
            field=self.field,
            crop=crop,
            season_year=2026,
            status=Cultivation.Status.ACTIVE,
            sowing_date=date(2026, 4, 1),
        )
        self.work = FieldWork.objects.create(
            cultivation=self.cultivation, work_type=FieldWork.WorkType.SOWING, work_date=date(2026, 4, 1)
        )
        self.spraying = Spraying.objects.create(
            cultivation=self.cultivation,
            spraying_date=date(2026, 5, 1),
            product_name="Środek",
            quantity=Decimal("1.00"),
            unit=Spraying.Unit.L,
        )
        self.harvest = Harvest.objects.create(
            cultivation=self.cultivation,
            harvest_date=date(2026, 8, 1),
            quantity=Decimal("2.00"),
            unit=Harvest.Unit.T,
        )
        self.report = ErrorReport.objects.create(
            user=self.user,
            category=ErrorReport.Category.OTHER,
            description="Opis zgłoszenia testowego.",
            status=ErrorReport.Status.NEW,
        )

    def tearDown(self):
        cache.clear()

    def assert_page_is_csp_compatible(self, url):
        response = self.client.get(url)
        with self.subTest(url=url):
            self.assertEqual(response.status_code, 200)
            self.assertIn("Content-Security-Policy", response.headers)
            collector = InlineCodeCollector()
            collector.feed(response.content.decode("utf-8"))
            self.assertEqual(collector.problems, [])

    def test_anonymous_pages(self):
        for name in ("core:home", "core:login", "core:register"):
            self.assert_page_is_csp_compatible(reverse(name))

    def test_signed_in_pages(self):
        self.client.force_login(self.user)
        plain = (
            "home", "profile", "profile_edit", "password_change",
            "field_list", "field_create", "crop_list", "crop_create",
            "cultivation_list", "cultivation_create",
            "fieldwork_list", "fieldwork_create",
            "spraying_list", "spraying_create",
            "harvest_list", "harvest_create",
            "report_dashboard", "error_report_list", "error_report_create",
        )
        for name in plain:
            self.assert_page_is_csp_compatible(reverse(f"core:{name}"))
        with_pk = {
            "field": self.field.pk,
            "cultivation": self.cultivation.pk,
            "fieldwork": self.work.pk,
            "spraying": self.spraying.pk,
            "harvest": self.harvest.pk,
        }
        for prefix, pk in with_pk.items():
            for action in ("detail", "update", "delete"):
                self.assert_page_is_csp_compatible(reverse(f"core:{prefix}_{action}", kwargs={"pk": pk}))
        self.assert_page_is_csp_compatible(reverse("core:field_report", kwargs={"pk": self.field.pk}))
        self.assert_page_is_csp_compatible(
            reverse("core:cultivation_report", kwargs={"pk": self.cultivation.pk})
        )
        self.assert_page_is_csp_compatible(
            reverse("core:error_report_detail", kwargs={"pk": self.report.pk})
        )

    def test_admin_pages(self):
        admin = get_user_model().objects.create_superuser(username="csp_admin", password="StrongPass!2026")
        self.assert_page_is_csp_compatible(reverse("admin:login"))
        self.client.force_login(admin)
        for url in (
            reverse("admin:index"),
            reverse("admin:core_field_changelist"),
            reverse("admin:core_field_add"),
            reverse("admin:core_field_change", args=[self.field.pk]),
            reverse("admin:core_cultivation_changelist"),
            reverse("admin:auth_user_changelist"),
        ):
            self.assert_page_is_csp_compatible(url)

    def test_language_switcher_and_theme_scripts_stay_on_allowed_sources(self):
        response = self.client.get(reverse("core:home"))
        content = response.content.decode("utf-8")

        self.assertIn(f'action="{reverse("set_language")}"', content)
        for script in ("core/theme-init.js", "core/theme.js", "core/forms.js"):
            self.assertIn(f'src="{settings.STATIC_URL}{script}"', content)
        self.assertIn(f'href="{settings.STATIC_URL}core/styles.css"', content)
        self.assertIn(f'href="{GOOGLE_FONTS_CSS}/css2?', content)

    def test_language_switch_still_works(self):
        response = self.client.post(
            reverse("set_language"), {"language": "en", "next": reverse("core:home")}
        )

        self.assertRedirects(response, reverse("core:home"), fetch_redirect_response=False)
        self.assertEqual(self.client.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")
