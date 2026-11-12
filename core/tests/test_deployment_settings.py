"""Settings used by the hosting setup described in docs/hosting.md."""

import sys
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

from .test_database_config import MYSQL_ENV, load_settings


class TiDBAndSSLSettingsTests(SimpleTestCase):
    def test_db_engine_tidb_selects_tidb_dialect(self):
        loaded = load_settings({**MYSQL_ENV, "DB_ENGINE": "tidb"})

        self.assertEqual(loaded["DATABASES"]["default"]["ENGINE"], "django_tidb")

    def test_no_ssl_options_without_ca(self):
        options = load_settings(MYSQL_ENV)["DATABASES"]["default"]["OPTIONS"]

        self.assertNotIn("ssl", options)
        self.assertNotIn("ssl_mode", options)

    def test_ssl_ca_turns_on_verified_tls(self):
        loaded = load_settings({**MYSQL_ENV, "DB_SSL_CA": "/etc/ssl/certs/ca-certificates.crt"})
        options = loaded["DATABASES"]["default"]["OPTIONS"]

        self.assertEqual(options["ssl"], {"ca": "/etc/ssl/certs/ca-certificates.crt"})
        self.assertEqual(options["ssl_mode"], "VERIFY_IDENTITY")


class RenderHostSettingsTests(SimpleTestCase):
    def test_render_hostname_is_allowed_and_trusted(self):
        loaded = load_settings({**MYSQL_ENV, "RENDER_EXTERNAL_HOSTNAME": "farmer-app.onrender.com"})

        self.assertIn("farmer-app.onrender.com", loaded["ALLOWED_HOSTS"])
        self.assertIn("https://farmer-app.onrender.com", loaded["CSRF_TRUSTED_ORIGINS"])

    def test_render_hostname_is_not_duplicated(self):
        loaded = load_settings({
            **MYSQL_ENV,
            "RENDER_EXTERNAL_HOSTNAME": "farmer-app.onrender.com",
            "DJANGO_ALLOWED_HOSTS": "farmer-app.onrender.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://farmer-app.onrender.com",
        })

        self.assertEqual(loaded["ALLOWED_HOSTS"].count("farmer-app.onrender.com"), 1)
        self.assertEqual(
            loaded["CSRF_TRUSTED_ORIGINS"].count("https://farmer-app.onrender.com"), 1
        )

    def test_without_render_only_configured_hosts(self):
        loaded = load_settings(MYSQL_ENV)

        self.assertEqual(loaded["ALLOWED_HOSTS"], ["localhost", "127.0.0.1", "[::1]"])
        self.assertEqual(loaded["CSRF_TRUSTED_ORIGINS"], [])


class ProxyHeaderSettingsTests(SimpleTestCase):
    def test_proxy_header_is_off_by_default(self):
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", load_settings(MYSQL_ENV))

    def test_proxy_header_is_trusted_only_when_enabled(self):
        loaded = load_settings({**MYSQL_ENV, "DJANGO_TRUST_X_FORWARDED_PROTO": "true"})

        self.assertEqual(loaded["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))


class StaticFilesSettingsTests(SimpleTestCase):
    def test_whitenoise_serves_static_files(self):
        self.assertIn("whitenoise.middleware.WhiteNoiseMiddleware", settings.MIDDLEWARE)
        index = settings.MIDDLEWARE.index
        self.assertEqual(
            index("whitenoise.middleware.WhiteNoiseMiddleware"),
            index("django.middleware.csp.ContentSecurityPolicyMiddleware") + 1,
        )

    def test_production_uses_hashed_compressed_static_files(self):
        # Outside `manage.py test` (e.g. under gunicorn) the WhiteNoise storage is used.
        with mock.patch.object(sys, "argv", ["gunicorn"]):
            loaded = load_settings(MYSQL_ENV)

        self.assertEqual(
            loaded["STORAGES"]["staticfiles"]["BACKEND"],
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )
        self.assertTrue(str(loaded["STATIC_ROOT"]).endswith("staticfiles"))
