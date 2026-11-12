from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from ..models import Crop, Cultivation, ErrorReport, Field, FieldWork, Harvest, Spraying


@tag("integration")
class AdminPanelTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.admin = users.objects.create_superuser(username="boss", password="StrongPass!2026")
        self.farmer = users.objects.create_user(username="farmer", password="StrongPass!2026")
        self.crop = Crop.objects.create(name="Pszenica")
        self.field = Field.objects.create(
            owner=self.farmer, name="Pole Północne", area_ha=Decimal("1234.50"),
            soil_type=Field.SoilType.LOAMY, location_method=Field.LocationMethod.ADDRESS,
        )
        self.cultivation = Cultivation.objects.create(
            field=self.field, crop=self.crop, season_year=2026, status=Cultivation.Status.ACTIVE,
        )
        self.work = FieldWork.objects.create(
            cultivation=self.cultivation, work_type=FieldWork.WorkType.PLOWING,
            work_date=date(2026, 3, 1), cost=Decimal("1500.00"),
        )
        self.spraying = Spraying.objects.create(
            cultivation=self.cultivation, spraying_date=date(2026, 5, 1), product_name="Preparat",
            quantity=Decimal("2.00"), unit=Spraying.Unit.L, cost=Decimal("80.00"),
        )
        self.harvest = Harvest.objects.create(
            cultivation=self.cultivation, harvest_date=date(2026, 8, 1), quantity=Decimal("5.00"),
            unit=Harvest.Unit.T, revenue=Decimal("100.00"), harvest_cost=Decimal("300.00"),
        )
        self.report = ErrorReport.objects.create(
            user=self.farmer, category=ErrorReport.Category.TECHNICAL,
            description="Wykres na stronie raportów się nie ładuje.",
            status=ErrorReport.Status.NEW,
        )
        self.client.force_login(self.admin)

    def test_every_list_and_edit_page_opens(self):
        objects = {
            "crop": self.crop, "field": self.field, "cultivation": self.cultivation,
            "fieldwork": self.work, "spraying": self.spraying, "harvest": self.harvest,
            "errorreport": self.report,
        }
        for model, obj in objects.items():
            with self.subTest(model=model):
                changelist = self.client.get(reverse(f"admin:core_{model}_changelist"))
                change = self.client.get(reverse(f"admin:core_{model}_change", args=[obj.pk]))
                add = self.client.get(reverse(f"admin:core_{model}_add"))
                self.assertEqual(changelist.status_code, 200)
                self.assertEqual(change.status_code, 200)
                self.assertEqual(add.status_code, 200)

    def test_pages_use_farmer_app_branding(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "core/admin.css")
        self.assertContains(response, 'class="fa-logo"')
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Farmer App – administration")
        self.assertContains(response, "Farm data and user reports")

    def test_admin_texts_are_translated(self):
        expected = {
            "pl": ("Farmer App – panel administracyjny", "Dzień dobry, boss!", "Prace i zbiory",
                   "Nowe zgłoszenia czekające na przejrzenie: 1", "Przejrzyj nowe zgłoszenia",
                   "Łączna powierzchnia", "Moje ostatnie działania"),
        }
        for language, texts in expected.items():
            with self.subTest(language=language):
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
                response = self.client.get(reverse("admin:index"))
                for text in texts:
                    self.assertContains(response, text)

    def test_admin_is_shown_in_polish_when_site_language_is_ukrainian(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "uk"
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Farmer App – panel administracyjny")
        self.assertNotContains(response, "Farmer App – адміністрування")
        self.assertEqual(response["Content-Language"], "pl")
        # The site itself keeps the chosen language.
        site = self.client.get(reverse("core:home"))
        self.assertEqual(site["Content-Language"], "uk")

    def test_language_switcher_offers_only_polish_and_english(self):
        for url in (reverse("admin:index"), reverse("admin:login")):
            with self.subTest(url=url):
                if url == reverse("admin:login"):
                    self.client.logout()
                response = self.client.get(url)
                self.assertContains(response, 'class="fa-lang"')
                self.assertContains(response, 'name="language" value="pl"')
                self.assertContains(response, 'name="language" value="en"')
                self.assertNotContains(response, 'name="language" value="uk"')

    def test_switching_language_in_admin_returns_to_the_same_page(self):
        url = reverse("admin:core_field_changelist")
        response = self.client.post(reverse("set_language"), {"language": "en", "next": url})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        page = self.client.get(url)
        self.assertEqual(page["Content-Language"], "en")
        self.assertContains(page, 'value="en" lang="en" title="English" aria-current="true"')

    def test_start_page_shows_tiles_for_every_section(self):
        response = self.client.get(reverse("admin:index"))
        for model in ("field", "cultivation", "crop", "fieldwork", "spraying", "harvest",
                      "errorreport"):
            with self.subTest(model=model):
                self.assertContains(response, f'href="{reverse(f"admin:core_{model}_changelist")}"')
                self.assertContains(response, f'href="{reverse(f"admin:core_{model}_add")}"')
        self.assertContains(response, 'href="#i-map"')
        self.assertContains(response, 'class="fa-tile-count"')

    def test_start_page_shows_farm_numbers(self):
        Cultivation.objects.create(
            field=self.field, crop=Crop.objects.create(name="Rzepak"), season_year=2025,
            status=Cultivation.Status.COMPLETED,
        )
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        response = self.client.get(reverse("admin:index"))
        # One field, one active cultivation (the 2025 one is completed) and one new report.
        self.assertContains(response, '<strong class="fa-stat-value">1</strong>', count=3, html=True)
        self.assertContains(response, "1,234.5<small>ha</small>")

    def test_start_page_shows_new_reports(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "fa-stat-alert")
        self.assertContains(response, "fa-tile-alert")
        self.assertContains(response, "?status__exact=NEW")

    def test_start_page_without_new_reports(self):
        self.report.status = ErrorReport.Status.RESOLVED
        self.report.save()
        response = self.client.get(reverse("admin:index"))
        self.assertNotContains(response, "fa-stat-alert")
        self.assertNotContains(response, "fa-tile-alert")

    def test_staff_sees_only_permitted_tiles(self):
        staff = get_user_model().objects.create_user(
            username="helper", password="StrongPass!2026", is_staff=True
        )
        staff.user_permissions.add(Permission.objects.get(codename="view_crop"))
        self.client.force_login(staff)
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, reverse("admin:core_crop_changelist"))
        self.assertNotContains(response, reverse("admin:core_field_changelist"))
        self.assertNotContains(response, "fa-stat-alert")

    def test_lists_show_badges_and_money(self):
        harvests = self.client.get(reverse("admin:core_harvest_changelist"))
        self.assertContains(harvests, "fa-badge-sold")
        self.assertContains(harvests, 'class="fa-loss"')
        works = self.client.get(reverse("admin:core_fieldwork_changelist"))
        self.assertContains(works, "zł")
        reports = self.client.get(reverse("admin:core_errorreport_changelist"))
        self.assertContains(reports, "fa-badge-new")
        self.assertContains(reports, "fa-badge-technical")

    def test_cultivation_page_lists_its_records(self):
        response = self.client.get(
            reverse("admin:core_cultivation_change", args=[self.cultivation.pk])
        )
        self.assertContains(response, "Preparat")
        self.assertContains(response, reverse("admin:core_fieldwork_change", args=[self.work.pk]))
        self.assertContains(response, reverse("admin:core_harvest_change", args=[self.harvest.pk]))

    def test_field_page_lists_its_cultivations(self):
        response = self.client.get(reverse("admin:core_field_change", args=[self.field.pk]))
        self.assertContains(
            response, reverse("admin:core_cultivation_change", args=[self.cultivation.pk])
        )

    def test_status_actions_update_reports(self):
        changelist = reverse("admin:core_errorreport_changelist")
        for action, status in (
            ("mark_in_progress", ErrorReport.Status.IN_PROGRESS),
            ("mark_resolved", ErrorReport.Status.RESOLVED),
        ):
            with self.subTest(action=action):
                before = self.report.updated_at
                response = self.client.post(
                    changelist, {"action": action, "_selected_action": [self.report.pk]}
                )
                self.assertRedirects(response, changelist)
                self.report.refresh_from_db()
                self.assertEqual(self.report.status, status)
                self.assertGreater(self.report.updated_at, before)

    def test_list_page_names_the_section_and_counts_records(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "pl"
        response = self.client.get(reverse("admin:core_field_changelist"))
        self.assertContains(response, 'class="fa-page-head"')
        self.assertContains(response, "<h1>Pola rolne</h1>", html=True)
        self.assertContains(response, "Liczba wpisów: 1")
        self.assertContains(response, 'href="#i-map"')
        self.assertNotContains(response, "do zmiany")
        # The name cell says where the field is.
        self.assertContains(response, '<span class="fa-sub">Adres</span>', html=True)
        filtered = self.client.get(
            reverse("admin:core_field_changelist"), {"soil_type__exact": Field.SoilType.SANDY}
        )
        self.assertContains(filtered, "Widoczne: 0 z 1")

    def test_side_menu_uses_sections_and_marks_the_current_page(self):
        response = self.client.get(reverse("admin:core_harvest_changelist"))
        self.assertContains(response, 'class="module fa-nav-section"')
        self.assertContains(
            response,
            f'<a href="{reverse("admin:core_harvest_changelist")}" aria-current="page">',
        )

    def test_edit_page_shows_the_record_name_and_grouped_fields(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "pl"
        response = self.client.get(reverse("admin:core_field_change", args=[self.field.pk]))
        self.assertContains(response, f"<h1>{self.field}</h1>", html=True)
        self.assertContains(response, "Podstawowe dane")
        self.assertContains(response, "Wybierz, jak odnaleźć pole")
        self.assertContains(response, "ostatnia zmiana")

    def test_field_page_offers_adding_a_cultivation_for_this_field(self):
        response = self.client.get(reverse("admin:core_field_change", args=[self.field.pk]))
        add_url = f'{reverse("admin:core_cultivation_add")}?field={self.field.pk}'
        self.assertContains(response, f'href="{add_url}"')
        self.assertContains(response, 'class="fa-records-count">1<', html=False)
        added = self.client.get(add_url)
        self.assertContains(added, f'<option value="{self.field.pk}" selected>', html=False)

    def test_related_records_hide_the_add_link_without_permission(self):
        staff = get_user_model().objects.create_user(
            username="viewer", password="StrongPass!2026", is_staff=True
        )
        staff.user_permissions.add(
            Permission.objects.get(codename="view_field"),
            Permission.objects.get(codename="view_cultivation"),
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("admin:core_field_change", args=[self.field.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'{reverse("admin:core_cultivation_add")}?field=')

    def test_empty_related_records_say_so(self):
        response = self.client.get(reverse("admin:core_cultivation_change", args=[
            Cultivation.objects.create(
                field=self.field, crop=self.crop, season_year=2027,
                status=Cultivation.Status.PLANNED,
            ).pk
        ]))
        self.assertContains(response, 'class="fa-records-empty"', count=3)

    def test_saving_a_field_keeps_its_cultivations(self):
        url = reverse("admin:core_field_change", args=[self.field.pk])
        response = self.client.post(url, {
            "owner": self.farmer.pk, "name": "Pole Północne nowe", "area_ha": "1234.50",
            "soil_type": Field.SoilType.LOAMY, "location_method": Field.LocationMethod.ADDRESS,
            "address": "Polna 1", "parcel_identifier": "", "latitude": "", "longitude": "",
            "description": "",
            "cultivations-TOTAL_FORMS": "1", "cultivations-INITIAL_FORMS": "1",
            "cultivations-MIN_NUM_FORMS": "0", "cultivations-MAX_NUM_FORMS": "1000",
            "cultivations-0-id": self.cultivation.pk, "cultivations-0-field": self.field.pk,
            "_save": "Save",
        })
        self.assertRedirects(response, reverse("admin:core_field_changelist"))
        self.field.refresh_from_db()
        self.assertEqual(self.field.name, "Pole Północne nowe")
        self.assertTrue(Cultivation.objects.filter(pk=self.cultivation.pk).exists())

    def count_queries(self, url):
        with CaptureQueriesContext(connection) as queries:
            self.client.get(url)
        return len(queries)

    def test_lists_do_not_run_a_query_per_row(self):
        urls = [
            reverse(f"admin:core_{model}_changelist")
            for model in ("fieldwork", "spraying", "harvest", "cultivation", "field", "errorreport")
        ]
        before = [self.count_queries(url) for url in urls]
        for index in range(5):
            cultivation = Cultivation.objects.create(
                field=Field.objects.create(
                    owner=self.farmer, name=f"Pole {index}", area_ha=Decimal("2.00"),
                    soil_type=Field.SoilType.SANDY, location_method=Field.LocationMethod.GPS,
                ),
                crop=self.crop, season_year=2026, status=Cultivation.Status.PLANNED,
            )
            FieldWork.objects.create(
                cultivation=cultivation, work_type=FieldWork.WorkType.SOWING,
                work_date=date(2026, 4, 1), cost=Decimal("10.00"),
            )
            Spraying.objects.create(
                cultivation=cultivation, spraying_date=date(2026, 5, 1), product_name="Środek",
                quantity=Decimal("1.00"), unit=Spraying.Unit.L,
            )
            Harvest.objects.create(
                cultivation=cultivation, harvest_date=date(2026, 8, 1), quantity=Decimal("1.00"),
                unit=Harvest.Unit.T,
            )
            ErrorReport.objects.create(
                user=self.farmer, category=ErrorReport.Category.OTHER,
                description="Kolejny opis problemu.", status=ErrorReport.Status.NEW,
            )
        after = [self.count_queries(url) for url in urls]
        self.assertEqual(dict(zip(urls, after)), dict(zip(urls, before)))
