import os
import runpy
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import SimpleTestCase, TestCase

SETTINGS_FILE = settings.BASE_DIR / "config" / "settings.py"
MYSQL_ENV = {
    "DJANGO_SECRET_KEY": "test-secret-key",
    "DB_NAME": "farmer_db",
    "DB_USER": "farmer_app_user",
    "DB_PASSWORD": "test-password",
}


def load_settings(env):
    """Execute config/settings.py with the given environment, ignoring .env."""
    with mock.patch.dict(os.environ, env, clear=True), mock.patch("dotenv.load_dotenv"):
        return runpy.run_path(str(SETTINGS_FILE))


class ActiveDatabaseTests(TestCase):
    def test_active_backend_is_mysql(self):
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.mysql")
        self.assertEqual(connection.vendor, "mysql")
        self.assertEqual(connection.settings_dict["OPTIONS"]["charset"], "utf8mb4")

    def test_tests_run_on_temporary_test_database(self):
        # The test runner replaces NAME with the test database name; the
        # regular database name is still available in the environment.
        regular_name = os.environ["DB_NAME"]
        test_name = "test_" + regular_name

        self.assertEqual(connection.settings_dict["NAME"], test_name)
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            self.assertEqual(cursor.fetchone()[0], test_name)


class DatabaseSettingsTests(SimpleTestCase):
    def test_mysql_is_used_without_db_engine(self):
        loaded = load_settings(MYSQL_ENV)
        database = loaded["DATABASES"]["default"]

        self.assertEqual(database["ENGINE"], "django.db.backends.mysql")
        self.assertEqual(database["NAME"], "farmer_db")
        self.assertEqual(database["HOST"], "localhost")
        self.assertEqual(database["PORT"], "3306")
        self.assertEqual(database["OPTIONS"]["charset"], "utf8mb4")

    def test_db_engine_cannot_switch_to_sqlite(self):
        loaded = load_settings({**MYSQL_ENV, "DB_ENGINE": "sqlite"})

        self.assertEqual(loaded["DATABASES"]["default"]["ENGINE"], "django.db.backends.mysql")

    def test_missing_required_variable_raises_improperly_configured(self):
        for name in ("DB_NAME", "DB_USER", "DB_PASSWORD"):
            with self.subTest(variable=name):
                env = {key: value for key, value in MYSQL_ENV.items() if key != name}
                with self.assertRaisesMessage(ImproperlyConfigured, name):
                    load_settings(env)
