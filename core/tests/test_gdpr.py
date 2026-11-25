"""GDPR: privacy policy page, acceptance at sign-up, data export, self-hosted fonts."""

import json
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ..models import (
    Crop,
    Cultivation,
    ErrorReport,
    Field,
    FieldWork,
    Harvest,
    PrivacyAcceptance,
    UserActivity,
)

PASSWORD = "StrongPass!2026"


class PrivacyPolicyPageTests(TestCase):
    def test_open_to_everyone_in_each_language(self):
        for language, text in (("pl", "Administratorem danych"), ("uk", "Розпорядником даних"),
                               ("en", "The data controller")):
            with self.subTest(language=language):
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
                response = self.client.get(reverse("core:privacy"))
                self.assertContains(response, text)
                self.assertContains(response, settings.PRIVACY_POLICY_VERSION)

    @override_settings(ACTIVITY_RETENTION_DAYS=14)
    def test_shows_activity_retention(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.assertContains(self.client.get(reverse("core:privacy")), "14 days")

    @override_settings(PRIVACY_CONTROLLER="Jan Kowalski", PRIVACY_CONTACT_EMAIL="rodo@example.com")
    def test_shows_configured_controller_and_contact(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        response = self.client.get(reverse("core:privacy"))

        self.assertContains(response, "Jan Kowalski")
        self.assertContains(response, 'href="mailto:rodo@example.com"')

    def test_without_contact_points_to_report_form(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.assertContains(self.client.get(reverse("core:privacy")), reverse("core:error_report_create"))

    def test_footer_links_to_policy(self):
        self.assertContains(self.client.get(reverse("core:home")), f'href="{reverse("core:privacy")}"')


class RegistrationAcceptanceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

    def data(self, **overrides):
        data = {
            "username": "anna", "first_name": "Anna", "last_name": "Nowak",
            "email": "anna@example.com", "password1": PASSWORD, "password2": PASSWORD,
            "accept_privacy": "on",
        }
        data.update(overrides)
        return data

    def test_form_links_to_policy(self):
        response = self.client.get(reverse("core:register"))

        self.assertContains(response, 'name="accept_privacy"')
        self.assertContains(response, f'href="{reverse("core:privacy")}"')

    def test_registration_requires_acceptance(self):
        data = self.data()
        del data["accept_privacy"]
        response = self.client.post(reverse("core:register"), data)

        self.assertFormError(response.context["form"], "accept_privacy",
                             "To create an account, confirm that you have read the privacy policy.")
        self.assertFalse(get_user_model().objects.exists())

    def test_acceptance_is_saved_with_version(self):
        self.client.post(reverse("core:register"), self.data())

        acceptance = PrivacyAcceptance.objects.get(user__username="anna")
        self.assertEqual(acceptance.policy_version, settings.PRIVACY_POLICY_VERSION)
        self.assertIsNotNone(acceptance.accepted_at)


class DataExportTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.user = users.objects.create_user(
            username="jan", password=PASSWORD, first_name="Jan", last_name="Kowalski",
            email="jan@example.com",
        )
        PrivacyAcceptance.objects.create(user=self.user, policy_version="2026-11-25")
        self.other = users.objects.create_user(username="ola", password=PASSWORD)
        crop = Crop.objects.create(name="Pszenica ozima")
        field = Field.objects.create(owner=self.user, name="Za stodołą", area_ha=Decimal("3.50"),
                                     soil_type="LOAMY", location_method="MAP",
                                     latitude=Decimal("52.1"), longitude=Decimal("21.0"))
        cultivation = Cultivation.objects.create(field=field, crop=crop, season_year=2026, status="ACTIVE")
        FieldWork.objects.create(cultivation=cultivation, work_type="PLOWING", work_date=date(2026, 3, 1))
        Harvest.objects.create(cultivation=cultivation, harvest_date=date(2026, 8, 1),
                               quantity=Decimal("10"), unit="T", revenue=Decimal("9000"))
        ErrorReport.objects.create(user=self.user, category="DATA", description="Zły wynik", status="NEW")
        Field.objects.create(owner=self.other, name="Cudze pole", area_ha=1, soil_type="SANDY",
                             location_method="ADDRESS")
        UserActivity.objects.create(user=None, username="jan", request_id="0123456789",
                                    method="POST", path="/accounts/login/", status=200)
        self.client.force_login(self.user)

    def export(self):
        response = self.client.get(reverse("core:data_export"))
        self.assertEqual(response.status_code, 200)
        return response, json.loads(response.content)

    def test_download_is_json_attachment(self):
        response, _ = self.export()

        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn(f"farmer-app-data-{self.user.pk}-", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_contains_account_farm_reports_and_activity(self):
        _, data = self.export()

        self.assertEqual(data["account"]["email"], "jan@example.com")
        self.assertEqual(data["privacy_policy"]["accepted_version"], "2026-11-25")
        self.assertEqual([f["name"] for f in data["fields"]], ["Za stodołą"])
        cultivation = data["fields"][0]["cultivations"][0]
        self.assertEqual(cultivation["crop"], "Pszenica ozima")
        self.assertEqual(cultivation["works"][0]["work_type"], "PLOWING")
        self.assertEqual(cultivation["harvests"][0]["revenue"], "9000.00")
        self.assertEqual(data["error_reports"][0]["description"], "Zły wynik")
        self.assertIn("0123456789", [e["request_id"] for e in data["activity"]["entries"]])

    def test_has_no_password_or_other_users_data(self):
        response, _ = self.export()
        text = response.content.decode()

        self.assertNotIn(self.user.password, text)
        self.assertNotIn('"password"', text)
        self.assertNotIn("Cudze pole", text)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("core:data_export"))

        self.assertEqual(response.status_code, 302)

    def test_profile_and_delete_page_link_to_export(self):
        url = reverse("core:data_export")
        self.assertContains(self.client.get(reverse("core:profile")), f'href="{url}"')
        self.assertContains(self.client.get(reverse("core:account_delete")), f'href="{url}"')

    def test_deleting_account_removes_acceptance(self):
        self.client.post(reverse("core:account_delete"), {"password": PASSWORD, "confirmation": "USUŃ"})

        self.assertFalse(PrivacyAcceptance.objects.filter(policy_version="2026-11-25").exists())


class SelfHostedFontsTests(TestCase):
    def test_pages_do_not_load_google_fonts(self):
        for name in ("core:home", "core:login"):
            with self.subTest(page=name):
                content = self.client.get(reverse(name)).content.decode()
                self.assertNotIn("fonts.googleapis.com", content)
                self.assertNotIn("fonts.gstatic.com", content)

    def test_font_files_exist(self):
        for css in ("core/vendor/fonts/fonts.css", "core/vendor/fonts/fonts-uk.css"):
            path = finders.find(css)
            self.assertIsNotNone(path, css)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertNotIn("https://", text)
            for name in set(part.split(")")[0] for part in text.split("url(")[1:]):
                self.assertIsNotNone(finders.find(f"core/vendor/fonts/{name}"), name)
