from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from ..models import Crop, Cultivation, Field


def create_field(owner, name, **overrides):
    values = {
        "owner": owner,
        "name": name,
        "area_ha": Decimal("5.00"),
        "soil_type": Field.SoilType.LOAMY,
        "location_method": Field.LocationMethod.ADDRESS,
        "address": "Bydgoszcz",
    }
    values.update(overrides)
    return Field.objects.create(**values)


class FieldYearCardsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="year_owner", password="StrongPass!2026")
        self.other = user_model.objects.create_user(username="year_other", password="StrongPass!2026")

        self.wheat = Crop.objects.create(name="Pszenica")
        self.corn = Crop.objects.create(name="Kukurydza")
        self.rye = Crop.objects.create(name="Żyto")
        self.secret_crop = Crop.objects.create(name="Len sąsiada")

        self.field = create_field(self.owner, "Pole Sezonowe", parcel_identifier="SEZ-1")
        self.wheat_2026 = Cultivation.objects.create(
            field=self.field,
            crop=self.wheat,
            season_year=2026,
            status=Cultivation.Status.ACTIVE,
            sowing_date="2026-03-20",
            planned_harvest_date="2026-08-10",
        )
        self.corn_2026 = Cultivation.objects.create(
            field=self.field, crop=self.corn, season_year=2026, status=Cultivation.Status.PLANNED
        )
        self.rye_2024 = Cultivation.objects.create(
            field=self.field, crop=self.rye, season_year=2024, status=Cultivation.Status.COMPLETED
        )
        self.wheat_2025 = Cultivation.objects.create(
            field=self.field, crop=self.wheat, season_year=2025, status=Cultivation.Status.COMPLETED
        )
        self.empty_field = create_field(self.owner, "Pole Bez Upraw", address="Toruń")

        self.other_field = create_field(self.other, "Cudze Pole Sezonowe")
        Cultivation.objects.create(
            field=self.other_field,
            crop=self.secret_crop,
            season_year=2019,
            status=Cultivation.Status.ACTIVE,
        )

    def detail_url(self, field):
        return reverse("core:field_detail", kwargs={"pk": field.pk})

    def report_url(self, field, year):
        return f'{reverse("core:field_report", kwargs={"pk": field.pk})}?season_year={year}'

    def season_card(self, response, year):
        """Return the HTML of a single season card from a field detail response."""
        content = response.content.decode()
        start = content.index(f'id="season-{year}"')
        return content[start:content.index("</article>", start)]

    def listed_field(self, response, field):
        return next(item for item in response.context["fields"] if item.pk == field.pk)

    # Access control and owner isolation

    def test_anonymous_user_is_redirected_to_login(self):
        for url in (reverse("core:field_list"), self.detail_url(self.field)):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f'{reverse("core:login")}?next={url}')

    def test_other_users_field_detail_returns_404(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.detail_url(self.other_field))

        self.assertEqual(response.status_code, 404)

    def test_list_shows_only_years_of_own_fields(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("core:field_list"))

        self.assertEqual(
            {field.pk for field in response.context["fields"]}, {self.field.pk, self.empty_field.pk}
        )
        self.assertNotContains(response, "season-2019")
        self.assertNotContains(response, "Cudze Pole Sezonowe")

    def test_other_users_data_does_not_leak_in_either_direction(self):
        self.client.force_login(self.owner)
        detail = self.client.get(self.detail_url(self.field))
        self.assertNotContains(detail, "Len sąsiada")
        self.assertNotContains(detail, "season-2019")

        self.client.force_login(self.other)
        other_list = self.client.get(reverse("core:field_list"))
        other_detail = self.client.get(self.detail_url(self.other_field))
        self.assertEqual(self.listed_field(other_list, self.other_field).season_years, [2019])
        for year in (2024, 2025, 2026):
            self.assertNotContains(other_list, f"season-{year}")
            self.assertNotContains(other_detail, f"season-{year}")
        self.assertNotContains(other_detail, "Pszenica")

    # Field list

    def test_list_years_are_unique_and_sorted_descending(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("core:field_list"))

        self.assertEqual(self.listed_field(response, self.field).season_years, [2026, 2025, 2024])
        # 2026 has two cultivations but appears as a single link.
        self.assertContains(response, f'{self.detail_url(self.field)}#season-2026"', count=1)
        content = response.content.decode()
        positions = [content.index(f"#season-{year}") for year in (2026, 2025, 2024)]
        self.assertEqual(positions, sorted(positions))

    def test_field_without_cultivations_shows_empty_state(self):
        self.client.force_login(self.owner)

        list_response = self.client.get(reverse("core:field_list"))
        detail_response = self.client.get(self.detail_url(self.empty_field))

        self.assertEqual(self.listed_field(list_response, self.empty_field).season_years, [])
        self.assertContains(list_response, "Brak zarejestrowanych sezonów", count=1)
        self.assertEqual(detail_response.context["season_groups"], [])
        self.assertNotContains(detail_response, 'class="season-card"')
        self.assertContains(detail_response, "Na tym polu nie zarejestrowano jeszcze żadnych upraw.")
        self.assertContains(
            detail_response, f'{reverse("core:cultivation_create")}?field={self.empty_field.pk}'
        )

    def test_list_link_points_to_existing_year_card(self):
        self.client.force_login(self.owner)
        list_response = self.client.get(reverse("core:field_list"))
        link = f"{self.detail_url(self.field)}#season-2025"
        self.assertContains(list_response, f'href="{link}"')

        path, anchor = link.split("#")
        detail_response = self.client.get(path)

        self.assertContains(detail_response, f'id="{anchor}"', count=1)

    def test_list_season_years_use_a_constant_number_of_queries(self):
        self.client.force_login(self.owner)
        with CaptureQueriesContext(connection) as small_list:
            self.client.get(reverse("core:field_list"))

        for index in range(6):
            extra_field = create_field(self.owner, f"Pole Dodatkowe {index}")
            Cultivation.objects.create(
                field=extra_field, crop=self.wheat, season_year=2020 + index, status=Cultivation.Status.ACTIVE
            )
        with CaptureQueriesContext(connection) as large_list:
            response = self.client.get(reverse("core:field_list"))

        self.assertEqual(len(response.context["fields"]), 8)
        self.assertEqual(len(large_list), len(small_list))

    def test_search_filters_and_pagination_still_work(self):
        self.client.force_login(self.owner)

        search = self.client.get(reverse("core:field_list"), {"q": "SEZ-1"})
        self.assertEqual([field.pk for field in search.context["fields"]], [self.field.pk])
        self.assertEqual(self.listed_field(search, self.field).season_years, [2026, 2025, 2024])

        create_field(self.owner, "Pole Piaszczyste", soil_type=Field.SoilType.SANDY)
        soil_filter = self.client.get(reverse("core:field_list"), {"soil_type": Field.SoilType.SANDY})
        self.assertEqual([field.name for field in soil_filter.context["fields"]], ["Pole Piaszczyste"])

        for index in range(10):
            create_field(self.owner, f"Pole Strona {index:02d}")
        page_two_field = create_field(self.owner, "Zz Pole Ostatnie")
        Cultivation.objects.create(
            field=page_two_field, crop=self.corn, season_year=2023, status=Cultivation.Status.COMPLETED
        )
        page_one = self.client.get(reverse("core:field_list"))
        page_two = self.client.get(reverse("core:field_list"), {"page": 2})

        self.assertTrue(page_one.context["is_paginated"])
        self.assertEqual(len(page_one.context["fields"]), 10)
        self.assertEqual(self.listed_field(page_two, page_two_field).season_years, [2023])
        self.assertContains(page_two, f'{self.detail_url(page_two_field)}#season-2023"')

    # Field detail

    def test_detail_groups_cultivations_of_one_year_in_one_card(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.detail_url(self.field))

        groups = response.context["season_groups"]
        self.assertEqual(groups[0]["year"], 2026)
        self.assertEqual(
            [cultivation.pk for cultivation in groups[0]["cultivations"]],
            [self.corn_2026.pk, self.wheat_2026.pk],
        )
        self.assertContains(response, 'id="season-2026"', count=1)
        card = self.season_card(response, 2026)
        for cultivation in (self.corn_2026, self.wheat_2026):
            self.assertIn(cultivation.crop.name, card)
            self.assertIn(reverse("core:cultivation_detail", kwargs={"pk": cultivation.pk}), card)
        self.assertNotIn(self.rye.name, card)

    def test_detail_creates_separate_cards_sorted_descending(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.detail_url(self.field))

        self.assertEqual([group["year"] for group in response.context["season_groups"]], [2026, 2025, 2024])
        content = response.content.decode()
        positions = [content.index(f'id="season-{year}"') for year in (2026, 2025, 2024)]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(content.count('class="season-card"'), 3)

    def test_card_shows_status_and_dates_or_dash(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.detail_url(self.field))

        card = self.season_card(response, 2026)
        self.assertIn("Data siewu: 20.03.2026", card)
        self.assertIn("Planowana data zbioru: 10.08.2026", card)
        self.assertIn("Data siewu: —", card)
        self.assertIn("Planowana data zbioru: —", card)
        self.assertIn('<span class="tag tag-active">Aktywna</span>', card)
        self.assertIn('<span class="tag tag-planned">Planowana</span>', card)
        self.assertIn('<span class="tag tag-completed">Zakończona</span>', self.season_card(response, 2024))

    def test_report_link_contains_season_year(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.detail_url(self.field))

        for year in (2026, 2025, 2024):
            with self.subTest(year=year):
                self.assertIn(f'href="{self.report_url(self.field, year)}"', self.season_card(response, year))
        report = self.client.get(self.report_url(self.field, 2025))
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.context["selected_season_year"], "2025")
        self.assertFalse(report.context["invalid_filter"])

    # Translations

    def test_new_texts_are_polish_by_default(self):
        self.client.force_login(self.owner)

        list_response = self.client.get(reverse("core:field_list"))
        detail_response = self.client.get(self.detail_url(self.field))

        self.assertContains(list_response, "Brak zarejestrowanych sezonów")
        self.assertContains(list_response, 'aria-label="Sezony pola Pole Sezonowe"')
        self.assertContains(detail_response, "Historia pola według lat")
        self.assertContains(detail_response, "Sezon 2026")
        self.assertContains(detail_response, "Raport za ten rok", count=3)

    def test_new_texts_are_translated_to_english_and_ukrainian(self):
        expected = {
            "en": ["No registered seasons", "Field history by year", "Report for this year", "Season 2026"],
            "uk": ["Немає зареєстрованих сезонів", "Історія поля за роками", "Звіт за цей рік", "Сезон 2026"],
        }
        self.client.force_login(self.owner)
        for language, texts in expected.items():
            with self.subTest(language=language):
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
                list_response = self.client.get(reverse("core:field_list"))
                detail_response = self.client.get(self.detail_url(self.field))

                self.assertContains(list_response, texts[0])
                for text in texts[1:]:
                    self.assertContains(detail_response, text)
                self.assertNotContains(detail_response, "Historia pola według lat")
