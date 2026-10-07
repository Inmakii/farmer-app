from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .forms import CultivationForm, FieldWorkForm
from .models import Crop, Cultivation, Field, FieldWork
from .views import parse_season_year

SOWING_YEAR_ERROR = "Rok daty siewu musi być zgodny z rokiem sezonu."
SOWING_WORK_YEAR_ERROR = "Rok daty siewu musi być zgodny z rokiem sezonu uprawy."
INVALID_SEASON_VALUES = ["²", "٢٠٢٦", "abc", "1999", "2101", "2026 ", "9" * 40]


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
        for value, expected in [("2000", 2000), ("2026", 2026), ("2100", 2100)]:
            with self.subTest(value=value):
                self.assertEqual(parse_season_year(value), (expected, True))

    def test_rejects_invalid_values_without_exception(self):
        for value in INVALID_SEASON_VALUES:
            with self.subTest(value=value):
                self.assertEqual(parse_season_year(value), (None, False))


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
