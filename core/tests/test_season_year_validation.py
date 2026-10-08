from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ..forms import CultivationForm, FieldWorkForm
from ..models import Crop, Cultivation, Field, FieldWork
from ..views import parse_season_year

SOWING_YEAR_ERROR = "Rok daty siewu musi być zgodny z rokiem sezonu."
SOWING_WORK_YEAR_ERROR = "Rok daty siewu musi być zgodny z rokiem sezonu uprawy."
SEASON_RANGE_ERROR = "Rok sezonu musi mieścić się w zakresie 1980–2100."
INVALID_SEASON_VALUES = [
    "²",
    "٢٠٢٦",
    "１９８０",
    "abc",
    "1979",
    "2101",
    "0000",
    "2026 ",
    "-1980",
    "9" * 40,
    "1980" * 10,
]


class SeasonYearTestData(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="season_owner", password="StrongPass!2026"
        )
        self.field = Field.objects.create(
            owner=self.owner,
            name="Pole Sezonowe",
            area_ha=Decimal("5.00"),
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Poznań",
        )
        self.wheat = Crop.objects.create(name="Pszenica")
        self.rye = Crop.objects.create(name="Żyto")
        self.cultivation = Cultivation.objects.create(
            field=self.field,
            crop=self.wheat,
            season_year=2026,
            status=Cultivation.Status.ACTIVE,
            sowing_date=date(2026, 4, 1),
        )


class CultivationSowingYearTests(SeasonYearTestData):
    def form_data(self, **overrides):
        data = {
            "field": str(self.field.pk),
            "crop": str(self.rye.pk),
            "season_year": "2026",
            "status": Cultivation.Status.PLANNED,
            "sowing_date": "2026-09-20",
            "planned_harvest_date": "2027-07-15",
            "notes": "",
        }
        data.update(overrides)
        return data

    def test_form_rejects_sowing_date_from_other_year(self):
        form = CultivationForm(
            data=self.form_data(sowing_date="2027-03-10"), user=self.owner
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["sowing_date"], [SOWING_YEAR_ERROR])

    def test_form_update_reports_sowing_year_error_once(self):
        form = CultivationForm(
            data=self.form_data(
                crop=str(self.wheat.pk),
                season_year="2027",
                sowing_date="2026-04-01",
                planned_harvest_date="",
            ),
            instance=self.cultivation,
            user=self.owner,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["sowing_date"], [SOWING_YEAR_ERROR])

    def test_full_clean_rejects_sowing_date_from_other_year(self):
        cultivation = Cultivation(
            field=self.field,
            crop=self.rye,
            season_year=2026,
            status=Cultivation.Status.PLANNED,
            sowing_date=date(2027, 3, 10),
        )

        with self.assertRaises(ValidationError) as context:
            cultivation.full_clean()

        self.assertEqual(
            context.exception.message_dict["sowing_date"], [SOWING_YEAR_ERROR]
        )

    def test_sowing_date_in_season_year_is_accepted(self):
        form = CultivationForm(data=self.form_data(), user=self.owner)

        self.assertTrue(form.is_valid(), form.errors)
        Cultivation(
            field=self.field,
            crop=self.rye,
            season_year=2026,
            status=Cultivation.Status.PLANNED,
            sowing_date=date(2026, 9, 20),
        ).full_clean()

    def test_winter_crop_harvest_may_be_planned_next_year(self):
        form = CultivationForm(data=self.form_data(), user=self.owner)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["planned_harvest_date"], date(2027, 7, 15)
        )

    def test_harvest_before_sowing_is_still_rejected(self):
        form = CultivationForm(
            data=self.form_data(planned_harvest_date="2026-08-01"), user=self.owner
        )

        self.assertFalse(form.is_valid())
        self.assertIn("planned_harvest_date", form.errors)

    def test_cultivation_without_sowing_date_is_accepted(self):
        form = CultivationForm(
            data=self.form_data(sowing_date="", planned_harvest_date=""),
            user=self.owner,
        )

        self.assertTrue(form.is_valid(), form.errors)


class FieldWorkSowingYearTests(SeasonYearTestData):
    def form_data(self, **overrides):
        data = {
            "season_year": "2026",
            "cultivation": str(self.cultivation.pk),
            "work_type": FieldWork.WorkType.SOWING,
            "work_date": "2026-04-01",
            "cost": "100.00",
            "description": "",
        }
        data.update(overrides)
        return data

    def test_form_rejects_sowing_work_from_other_year(self):
        form = FieldWorkForm(
            data=self.form_data(work_date="2027-04-01"), user=self.owner
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["work_date"], [SOWING_WORK_YEAR_ERROR])

    def test_full_clean_rejects_sowing_work_from_other_year(self):
        work = FieldWork(
            cultivation=self.cultivation,
            work_type=FieldWork.WorkType.SOWING,
            work_date=date(2025, 10, 1),
            cost=Decimal("0.00"),
        )

        with self.assertRaises(ValidationError) as context:
            work.full_clean()

        self.assertEqual(
            context.exception.message_dict["work_date"], [SOWING_WORK_YEAR_ERROR]
        )

    def test_sowing_work_in_season_year_is_accepted(self):
        form = FieldWorkForm(data=self.form_data(), user=self.owner)

        self.assertTrue(form.is_valid(), form.errors)

    def test_other_work_type_may_be_in_adjacent_year(self):
        for work_type, work_date in [
            (FieldWork.WorkType.PLOWING, "2025-10-15"),
            (FieldWork.WorkType.FERTILIZING, "2027-03-01"),
        ]:
            with self.subTest(work_type=work_type):
                form = FieldWorkForm(
                    data=self.form_data(work_type=work_type, work_date=work_date),
                    user=self.owner,
                )

                self.assertTrue(form.is_valid(), form.errors)
                FieldWork(
                    cultivation=self.cultivation,
                    work_type=work_type,
                    work_date=date.fromisoformat(work_date),
                ).full_clean()

    def test_create_view_does_not_save_sowing_from_other_year(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("core:fieldwork_create"),
            self.form_data(work_date="2027-04-01"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(FieldWork.objects.exists())


class ParseSeasonYearTests(SimpleTestCase):
    def test_accepts_empty_value_as_no_filter(self):
        self.assertEqual(parse_season_year(""), (None, True))

    def test_accepts_four_ascii_digits_in_range(self):
        for value, expected in [
            ("1980", 1980),
            ("2000", 2000),
            ("2026", 2026),
            ("2100", 2100),
        ]:
            with self.subTest(value=value):
                self.assertEqual(parse_season_year(value), (expected, True))

    def test_rejects_invalid_values_without_exception(self):
        for value in INVALID_SEASON_VALUES:
            with self.subTest(value=value):
                self.assertEqual(parse_season_year(value), (None, False))

    def test_range_boundaries(self):
        self.assertEqual(parse_season_year("1979"), (None, False))
        self.assertEqual(parse_season_year("1980"), (1980, True))
        self.assertEqual(parse_season_year("2100"), (2100, True))
        self.assertEqual(parse_season_year("2101"), (None, False))


class SeasonYearFilterViewTests(SeasonYearTestData):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)

    def test_cultivation_list_ignores_invalid_season_filter(self):
        for value in INVALID_SEASON_VALUES:
            with self.subTest(value=value):
                response = self.client.get(
                    reverse("core:cultivation_list"), {"season_year": value}
                )

                self.assertEqual(response.status_code, 200)
                self.assertQuerySetEqual(
                    response.context["cultivations"], [self.cultivation]
                )

    def test_cultivation_list_filters_valid_season(self):
        response = self.client.get(
            reverse("core:cultivation_list"), {"season_year": "2025"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["cultivations"], [])

    def test_report_dashboard_marks_invalid_season_filter(self):
        for value in INVALID_SEASON_VALUES:
            with self.subTest(value=value):
                response = self.client.get(
                    reverse("core:report_dashboard"), {"season_year": value}
                )

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["invalid_filters"])

    def test_field_report_marks_invalid_season_filter(self):
        url = reverse("core:field_report", kwargs={"pk": self.field.pk})
        for value in INVALID_SEASON_VALUES:
            with self.subTest(value=value):
                response = self.client.get(url, {"season_year": value})

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["invalid_filter"])


class SeasonYearRangeTests(SeasonYearTestData):
    def form_data(self, **overrides):
        data = {
            "field": str(self.field.pk),
            "crop": str(self.rye.pk),
            "season_year": "1980",
            "status": Cultivation.Status.PLANNED,
            "sowing_date": "",
            "planned_harvest_date": "",
            "notes": "",
        }
        data.update(overrides)
        return data

    def build_cultivation(self, season_year, **extra):
        return Cultivation(
            field=self.field,
            crop=self.rye,
            season_year=season_year,
            status=Cultivation.Status.PLANNED,
            **extra,
        )

    def test_form_accepts_boundary_years(self):
        for year in ["1980", "2100"]:
            with self.subTest(year=year):
                form = CultivationForm(
                    data=self.form_data(season_year=year), user=self.owner
                )

                self.assertTrue(form.is_valid(), form.errors)

    def test_form_rejects_years_outside_range_with_polish_message(self):
        for year in ["1979", "2101"]:
            with self.subTest(year=year):
                form = CultivationForm(
                    data=self.form_data(season_year=year), user=self.owner
                )

                self.assertFalse(form.is_valid())
                self.assertEqual(form.errors["season_year"], [SEASON_RANGE_ERROR])

    def test_model_accepts_boundary_years(self):
        for year in [1980, 2100]:
            with self.subTest(year=year):
                self.build_cultivation(year).full_clean()

    def test_model_rejects_years_outside_range(self):
        for year in [1979, 2101]:
            with self.subTest(year=year):
                with self.assertRaises(ValidationError) as context:
                    self.build_cultivation(year).full_clean()

                self.assertIn("season_year", context.exception.message_dict)

    def test_sowing_date_may_start_on_1980_01_01(self):
        form = CultivationForm(
            data=self.form_data(sowing_date="1980-01-01"), user=self.owner
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.build_cultivation(1980, sowing_date=date(1980, 1, 1)).full_clean()

    def test_sowing_date_before_1980_is_rejected(self):
        form = CultivationForm(
            data=self.form_data(sowing_date="1979-12-31"), user=self.owner
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["sowing_date"], [SOWING_YEAR_ERROR])

    def test_sowing_date_on_last_day_of_2100_is_accepted(self):
        form = CultivationForm(
            data=self.form_data(season_year="2100", sowing_date="2100-12-31"),
            user=self.owner,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_winter_crop_from_1980_may_be_harvested_in_1981(self):
        form = CultivationForm(
            data=self.form_data(
                sowing_date="1980-09-20", planned_harvest_date="1981-07-15"
            ),
            user=self.owner,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_winter_crop_from_2100_may_be_harvested_in_2101(self):
        form = CultivationForm(
            data=self.form_data(
                season_year="2100",
                sowing_date="2100-09-20",
                planned_harvest_date="2101-07-15",
            ),
            user=self.owner,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.build_cultivation(
            2100,
            sowing_date=date(2100, 9, 20),
            planned_harvest_date=date(2101, 7, 15),
        ).full_clean()

    def test_create_view_saves_cultivation_from_1980(self):
        self.client.force_login(self.owner)

        self.client.post(
            reverse("core:cultivation_create"),
            self.form_data(sowing_date="1980-01-01"),
        )

        self.assertTrue(
            Cultivation.objects.filter(
                season_year=1980, sowing_date=date(1980, 1, 1)
            ).exists()
        )

    def test_create_view_does_not_save_year_1979(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("core:cultivation_create"),
            self.form_data(season_year="1979"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SEASON_RANGE_ERROR)
        self.assertFalse(Cultivation.objects.filter(season_year=1979).exists())

    def test_form_html_inputs_use_range(self):
        form = CultivationForm(user=self.owner)

        season_attrs = form["season_year"].field.widget.attrs
        self.assertEqual(season_attrs["min"], 1980)
        self.assertEqual(season_attrs["max"], 2100)
        sowing_attrs = form["sowing_date"].field.widget.attrs
        self.assertEqual(sowing_attrs["min"], "1980-01-01")
        self.assertEqual(sowing_attrs["max"], "2100-12-31")
        harvest_attrs = form["planned_harvest_date"].field.widget.attrs
        self.assertEqual(harvest_attrs["min"], "1980-01-01")
        self.assertEqual(harvest_attrs["max"], "2101-12-31")


class SeasonYearRangeFilterTests(SeasonYearTestData):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)
        self.old_cultivation = Cultivation.objects.create(
            field=self.field,
            crop=self.rye,
            season_year=1980,
            status=Cultivation.Status.COMPLETED,
            sowing_date=date(1980, 1, 1),
        )

    def test_cultivation_list_filters_year_1980(self):
        response = self.client.get(
            reverse("core:cultivation_list"), {"season_year": "1980"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(
            response.context["cultivations"], [self.old_cultivation]
        )

    def test_cultivation_list_filters_year_2100(self):
        response = self.client.get(
            reverse("core:cultivation_list"), {"season_year": "2100"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["cultivations"], [])

    def test_cultivation_list_ignores_years_outside_range(self):
        for value in ["1979", "2101"]:
            with self.subTest(value=value):
                response = self.client.get(
                    reverse("core:cultivation_list"), {"season_year": value}
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context["cultivations"]), 2)

    def test_reports_accept_boundary_years(self):
        field_report_url = reverse("core:field_report", kwargs={"pk": self.field.pk})
        for value in ["1980", "2100"]:
            with self.subTest(value=value):
                dashboard = self.client.get(
                    reverse("core:report_dashboard"), {"season_year": value}
                )
                field_report = self.client.get(
                    field_report_url, {"season_year": value}
                )

                self.assertEqual(dashboard.status_code, 200)
                self.assertFalse(dashboard.context["invalid_filters"])
                self.assertEqual(field_report.status_code, 200)
                self.assertFalse(field_report.context["invalid_filter"])

    def test_reports_reject_years_outside_range(self):
        field_report_url = reverse("core:field_report", kwargs={"pk": self.field.pk})
        for value in ["1979", "2101"]:
            with self.subTest(value=value):
                dashboard = self.client.get(
                    reverse("core:report_dashboard"), {"season_year": value}
                )
                field_report = self.client.get(
                    field_report_url, {"season_year": value}
                )

                self.assertTrue(dashboard.context["invalid_filters"])
                self.assertTrue(field_report.context["invalid_filter"])

    def test_filter_inputs_use_range(self):
        pages = [
            reverse("core:cultivation_list"),
            reverse("core:report_dashboard"),
            reverse("core:field_report", kwargs={"pk": self.field.pk}),
        ]
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertContains(response, 'min="1980" max="2100"')
                self.assertNotContains(response, 'min="2000"')
