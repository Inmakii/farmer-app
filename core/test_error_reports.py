from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from .admin import ErrorReportAdmin
from .forms import ErrorReportForm
from .models import ErrorReport


class ErrorReportTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.user = users.objects.create_user(
            username="reporter", email="reporter@example.com", password="StrongPass!2026"
        )
        self.other = users.objects.create_user(
            username="other_reporter", email="other@example.com", password="StrongPass!2026"
        )
        self.report = ErrorReport.objects.create(
            user=self.user,
            category=ErrorReport.Category.TECHNICAL,
            description="Opis własnego problemu technicznego.",
            status=ErrorReport.Status.IN_PROGRESS,
        )
        self.other_report = ErrorReport.objects.create(
            user=self.other,
            category=ErrorReport.Category.DATA,
            description="Opis cudzego problemu z danymi.",
            status=ErrorReport.Status.RESOLVED,
        )

    def valid_data(self, **overrides):
        data = {
            "category": ErrorReport.Category.INTERFACE,
            "description": "  Szczegółowy opis problemu z interfejsem.  ",
        }
        data.update(overrides)
        return data

    def test_anonymous_user_is_redirected(self):
        for name in ("error_report_list", "error_report_create"):
            url = reverse(f"core:{name}")
            self.assertRedirects(self.client.get(url), f"{reverse('core:login')}?next={url}")

    def test_list_contains_only_own_reports(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:error_report_list"))
        self.assertQuerySetEqual(response.context["error_reports"], [self.report])
        self.assertNotContains(response, f"Zgłoszenie #{self.other_report.pk}")

    def test_category_filter(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:error_report_list"), {"category": ErrorReport.Category.DATA})
        self.assertQuerySetEqual(response.context["error_reports"], [])

    def test_status_filter(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:error_report_list"), {"status": ErrorReport.Status.IN_PROGRESS})
        self.assertQuerySetEqual(response.context["error_reports"], [self.report])

    def test_valid_create(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("core:error_report_create"), self.valid_data())
        created = ErrorReport.objects.exclude(pk__in=[self.report.pk, self.other_report.pk]).get()
        self.assertRedirects(response, reverse("core:error_report_detail", kwargs={"pk": created.pk}))
        self.assertEqual(created.description, "Szczegółowy opis problemu z interfejsem.")

    def test_create_assigns_current_user(self):
        self.client.force_login(self.user)
        self.client.post(reverse("core:error_report_create"), self.valid_data())
        self.assertTrue(ErrorReport.objects.filter(user=self.user, category=ErrorReport.Category.INTERFACE).exists())

    def test_create_assigns_new_status(self):
        self.client.force_login(self.user)
        self.client.post(reverse("core:error_report_create"), self.valid_data())
        self.assertEqual(ErrorReport.objects.filter(user=self.user).latest("pk").status, ErrorReport.Status.NEW)

    def test_post_cannot_replace_user(self):
        self.client.force_login(self.user)
        data = self.valid_data(user=self.other.pk)
        self.client.post(reverse("core:error_report_create"), data)
        self.assertEqual(ErrorReport.objects.filter(user=self.user).latest("pk").user, self.user)

    def test_post_cannot_replace_status(self):
        self.client.force_login(self.user)
        data = self.valid_data(status=ErrorReport.Status.RESOLVED)
        self.client.post(reverse("core:error_report_create"), data)
        self.assertEqual(ErrorReport.objects.filter(user=self.user).latest("pk").status, ErrorReport.Status.NEW)

    def test_form_excludes_protected_fields(self):
        self.assertEqual(tuple(ErrorReportForm().fields), ("category", "description"))

    def test_short_description_is_rejected(self):
        form = ErrorReportForm(data=self.valid_data(description="Za krótki"))
        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)

    def test_long_description_is_rejected(self):
        form = ErrorReportForm(data=self.valid_data(description="a" * 5001))
        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)

    def test_owner_can_view_detail(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:error_report_detail", kwargs={"pk": self.report.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.report.description)

    def test_other_user_gets_404(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("core:error_report_detail", kwargs={"pk": self.report.pk}))
        self.assertEqual(response.status_code, 404)

    def test_edit_and_delete_routes_do_not_exist(self):
        for name in ("error_report_update", "error_report_delete"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"core:{name}", kwargs={"pk": self.report.pk})

    def test_profile_shows_own_report_count(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:profile"))
        self.assertEqual(response.context["error_report_count"], 1)
        self.assertContains(response, "Liczba Twoich zgłoszeń: 1")

    def test_profile_does_not_count_other_reports(self):
        ErrorReport.objects.create(user=self.other, category=ErrorReport.Category.OTHER, description="Kolejny cudzy opis problemu.", status=ErrorReport.Status.NEW)
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:profile"))
        self.assertEqual(response.context["error_report_count"], 1)

    def test_admin_configuration(self):
        model_admin = admin.site._registry[ErrorReport]
        self.assertIsInstance(model_admin, ErrorReportAdmin)
        self.assertEqual(model_admin.list_display, ("user", "category", "status", "created_at", "updated_at"))
        self.assertEqual(model_admin.list_filter, ("category", "status", "created_at"))
        self.assertEqual(model_admin.search_fields, ("user__username", "user__email", "description"))
        self.assertIn("status", model_admin.list_editable)
