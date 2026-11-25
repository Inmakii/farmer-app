"""Request codes, request log lines, the user activity trail and browser errors."""

import json
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import ErrorReport, UserActivity

PASSWORD = "StrongPass!2026"


class RequestLogTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="jan", password=PASSWORD)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

    def test_response_has_request_code(self):
        response = self.client.get(reverse("core:login"))

        self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{10}$")

    def test_log_line_has_code_user_and_page(self):
        self.client.force_login(self.user)
        with self.assertLogs("farmer.requests", "INFO") as logs:
            response = self.client.get(reverse("core:field_list"))

        line = logs.output[0]
        self.assertIn("GET /fields/ (core:field_list) 200", line)
        record = logs.records[0]
        self.assertEqual(record.request_id, response["X-Request-ID"])
        self.assertEqual(record.user, f"{self.user.pk}:jan")

    def test_signed_in_requests_are_stored(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:field_list"))

        activity = UserActivity.objects.get()
        self.assertEqual(activity.user, self.user)
        self.assertEqual(activity.request_id, response["X-Request-ID"])
        self.assertEqual(activity.view_name, "core:field_list")
        self.assertEqual(activity.status, 200)

    def test_anonymous_pages_are_not_stored(self):
        self.client.get(reverse("core:login"))

        self.assertFalse(UserActivity.objects.exists())

    def test_form_errors_are_named_but_values_are_not_stored(self):
        self.client.force_login(self.user)
        self.client.post(reverse("core:field_create"), {"name": "Tajne pole", "area_ha": "-1"})

        activity = UserActivity.objects.get(method="POST")
        self.assertIn("area_ha", activity.form_errors)
        self.assertNotIn("Tajne", activity.path + activity.form_errors + activity.error)

    def test_failed_login_keeps_typed_login_not_password(self):
        with self.assertLogs("farmer.requests", "INFO") as logs:
            self.client.post(reverse("core:login"), {"username": "jan", "password": "zle-haslo"})

        activity = UserActivity.objects.get()
        self.assertIsNone(activity.user)
        self.assertEqual(activity.username, "jan")
        self.assertIn("login attempt: jan", logs.output[0])
        self.assertNotIn("zle-haslo", "".join(logs.output))

    def test_successful_login_is_stored_for_user(self):
        self.client.post(reverse("core:login"), {"username": "jan", "password": PASSWORD})

        self.assertEqual(UserActivity.objects.get().user, self.user)

    def test_logout_is_stored_for_user_who_logged_out(self):
        self.client.force_login(self.user)
        self.client.post(reverse("core:logout"))

        self.assertEqual(UserActivity.objects.get(view_name="core:logout").user, self.user)

    def test_geo_hints_are_not_stored(self):
        self.client.force_login(self.user)
        self.client.get(reverse("core:geo_localities"), {"q": "Ni"})

        self.assertFalse(UserActivity.objects.exists())

    def test_storage_failure_does_not_break_page(self):
        self.client.force_login(self.user)
        with mock.patch.object(UserActivity.objects, "create", side_effect=RuntimeError("db down")), \
                self.assertLogs("farmer.requests", "ERROR"):
            response = self.client.get(reverse("core:field_list"))

        self.assertEqual(response.status_code, 200)

    def test_profile_shows_account_number(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:profile"))

        self.assertContains(response, f"#{self.user.pk}")


class ServerErrorTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="jan", password=PASSWORD)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.client.force_login(self.user)
        self.client.raise_request_exception = False

    def test_error_page_shows_code_and_activity_keeps_exception(self):
        with mock.patch("core.views.FieldListView.get", side_effect=ValueError("boom")):
            response = self.client.get(reverse("core:field_list"))

        self.assertEqual(response.status_code, 500)
        code = response["X-Request-ID"]
        self.assertContains(response, code, status_code=500)
        self.assertContains(response, f"code={code}", status_code=500)
        activity = UserActivity.objects.get(request_id=code)
        self.assertEqual(activity.status, 500)
        self.assertEqual(activity.error, "ValueError: boom")

    def test_report_keeps_error_code(self):
        url = reverse("core:error_report_create") + "?from=/fields/&code=0123456789"
        self.client.post(url, {"category": "TECHNICAL", "description": "Strona się wysypała."})

        self.assertEqual(ErrorReport.objects.get().error_code, "0123456789")

    def test_report_ignores_bad_error_code(self):
        url = reverse("core:error_report_create") + "?code=<script>"
        self.client.post(url, {"category": "TECHNICAL", "description": "Strona się wysypała."})

        self.assertEqual(ErrorReport.objects.get().error_code, "")


class AdminActivityTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.admin = users.objects.create_superuser(username="admin", password=PASSWORD)
        self.user = users.objects.create_user(username="jan", password=PASSWORD)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

    def test_report_page_shows_activity_before_report(self):
        user_client = self.client_class()
        user_client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        user_client.force_login(self.user)
        user_client.get(reverse("core:field_list"))
        user_client.post(reverse("core:field_create"), {"name": "", "area_ha": ""})
        user_client.post(reverse("core:error_report_create"), {
            "category": "TECHNICAL", "description": "Nie mogę zapisać pola.",
        })
        report = ErrorReport.objects.get()

        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:core_errorreport_change", args=[report.pk]))

        self.assertContains(response, "What the user did before the report")
        self.assertContains(response, "core:field_create")
        self.assertContains(response, "/fields/add/")
        self.assertContains(response, f"user__id__exact={self.user.pk}")

    def test_activity_list_search_by_user_number(self):
        UserActivity.objects.create(user=self.user, username="jan", request_id="abcdef0123",
                                    method="GET", path="/fields/", status=200)
        self.client.force_login(self.admin)

        response = self.client.get(reverse("admin:core_useractivity_changelist"), {"q": f"#{self.user.pk}"})

        self.assertContains(response, "abcdef0123")

    def test_activity_is_read_only(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("admin:core_useractivity_add"))

        self.assertEqual(response.status_code, 403)


class ClientErrorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="jan", password=PASSWORD)
        self.url = reverse("core:client_error")

    def send(self, **data):
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def test_browser_error_is_logged_and_stored(self):
        self.client.force_login(self.user)
        with self.assertLogs("farmer.requests", "WARNING") as logs:
            response = self.send(message="x is undefined", source="/static/core/forms.js", line=12, page="/fields/add/")

        self.assertEqual(response.status_code, 204)
        self.assertIn("Browser error on /fields/add/: x is undefined at /static/core/forms.js:12", "".join(logs.output))
        activity = UserActivity.objects.get(method="JS")
        self.assertEqual(activity.path, "/fields/add/")

    def test_works_without_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        response = client.post(self.url, json.dumps({"message": "x"}), content_type="application/json")

        self.assertEqual(response.status_code, 204)

    def test_rate_limited(self):
        with mock.patch("core.activity.CLIENT_ERRORS_PER_MINUTE", 2), \
                self.assertLogs("farmer.requests", "WARNING") as logs:
            for _ in range(4):
                self.send(message="x")

        self.assertEqual(sum("Browser error" in line for line in logs.output), 2)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class PruneActivityTests(TestCase):
    @override_settings(ACTIVITY_RETENTION_DAYS=30)
    def test_removes_old_entries_only(self):
        old = UserActivity.objects.create(request_id="a", method="GET", path="/", status=200, username="x")
        UserActivity.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
        UserActivity.objects.create(request_id="b", method="GET", path="/", status=200, username="x")

        call_command("prune_activity", stdout=StringIO())

        self.assertEqual(list(UserActivity.objects.values_list("request_id", flat=True)), ["b"])


class AccountDeleteActivityTests(TestCase):
    def test_deleting_account_removes_activity_and_login_attempts(self):
        user = get_user_model().objects.create_user(username="jan", password=PASSWORD)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.client.post(reverse("core:login"), {"username": "jan", "password": "wrong"})
        self.client.force_login(user)
        self.client.get(reverse("core:field_list"))

        self.client.post(reverse("core:account_delete"), {"password": PASSWORD, "confirmation": "DELETE"})

        self.assertFalse(UserActivity.objects.filter(username="jan").exists())
