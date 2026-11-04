"""Regression tests: a unique conflict that slips past form validation.

Two requests can validate the same unique values at the same moment (for example
a double-clicked submit button). The second save then fails on the MySQL unique
index. These tests simulate that race by disabling the form-level duplicate check
and expect a form error instead of an unhandled IntegrityError (HTTP 500).
"""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from ..forms import CropForm, CultivationForm, FieldForm
from ..models import Crop, Cultivation, Field


def _field_form_clean_name_without_duplicate_check(self):
    return self.cleaned_data["name"].strip()


def _model_form_clean_without_unique_validation(self):
    return self.cleaned_data


def _crop_form_clean_name_without_duplicate_check(self):
    return self.cleaned_data["name"].strip()


class UniqueConflictTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="race_owner", password="StrongPass!2026"
        )
        self.client.force_login(self.owner)
        self.field = Field.objects.create(
            owner=self.owner,
            name="Pole Wschodnie",
            area_ha=Decimal("5.00"),
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Toruń, ul. Polna 2",
        )
        self.wheat = Crop.objects.create(name="Pszenica")
        self.cultivation = Cultivation.objects.create(
            field=self.field,
            crop=self.wheat,
            season_year=2026,
            status=Cultivation.Status.PLANNED,
        )

    def _field_data(self, name):
        return {
            "name": name,
            "area_ha": "3.50",
            "soil_type": Field.SoilType.SANDY,
            "location_method": Field.LocationMethod.ADDRESS,
            "address": "Toruń, ul. Leśna 5",
            "parcel_identifier": "",
            "latitude": "",
            "longitude": "",
            "description": "",
        }

    def _assert_no_success_message(self, response):
        self.assertEqual(list(get_messages(response.wsgi_request)), [])

    @mock.patch.object(FieldForm, "clean_name", _field_form_clean_name_without_duplicate_check)
    def test_field_create_conflict_shows_form_error(self):
        response = self.client.post(
            reverse("core:field_create"), self._field_data("Pole Wschodnie")
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "name", "Masz już pole o tej nazwie.")
        self.assertEqual(Field.objects.filter(owner=self.owner).count(), 1)
        self._assert_no_success_message(response)

    @mock.patch.object(FieldForm, "clean_name", _field_form_clean_name_without_duplicate_check)
    def test_field_update_conflict_shows_form_error(self):
        other = Field.objects.create(
            owner=self.owner,
            name="Pole Zachodnie",
            area_ha=Decimal("2.00"),
            soil_type=Field.SoilType.CLAY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Toruń, ul. Krótka 1",
        )

        response = self.client.post(
            reverse("core:field_update", kwargs={"pk": other.pk}),
            self._field_data("Pole Wschodnie"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "name", "Masz już pole o tej nazwie.")
        other.refresh_from_db()
        self.assertEqual(other.name, "Pole Zachodnie")
        self._assert_no_success_message(response)

    @mock.patch.object(CultivationForm, "clean", _model_form_clean_without_unique_validation)
    def test_cultivation_create_conflict_shows_form_error(self):
        response = self.client.post(
            reverse("core:cultivation_create"),
            {
                "field": self.field.pk,
                "crop": self.wheat.pk,
                "season_year": 2026,
                "status": Cultivation.Status.ACTIVE,
                "sowing_date": "",
                "planned_harvest_date": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], None, "Taka uprawa jest już przypisana do tego pola i sezonu."
        )
        self.assertEqual(Cultivation.objects.count(), 1)
        self._assert_no_success_message(response)

    @mock.patch.object(CultivationForm, "clean", _model_form_clean_without_unique_validation)
    def test_cultivation_update_conflict_shows_form_error(self):
        corn = Crop.objects.create(name="Kukurydza")
        other = Cultivation.objects.create(
            field=self.field,
            crop=corn,
            season_year=2026,
            status=Cultivation.Status.PLANNED,
        )

        response = self.client.post(
            reverse("core:cultivation_update", kwargs={"pk": other.pk}),
            {
                "field": self.field.pk,
                "crop": self.wheat.pk,
                "season_year": 2026,
                "status": Cultivation.Status.PLANNED,
                "sowing_date": "",
                "planned_harvest_date": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], None, "Taka uprawa jest już przypisana do tego pola i sezonu."
        )
        other.refresh_from_db()
        self.assertEqual(other.crop, corn)
        self._assert_no_success_message(response)

    @mock.patch.object(CropForm, "clean_name", _crop_form_clean_name_without_duplicate_check)
    @mock.patch.object(CropForm, "validate_unique", lambda self: None)
    def test_crop_create_conflict_shows_form_error(self):
        response = self.client.post(
            reverse("core:crop_create"), {"name": "Pszenica", "description": ""}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "name", "Rodzaj uprawy o tej nazwie już istnieje."
        )
        self.assertEqual(Crop.objects.count(), 1)
        self._assert_no_success_message(response)

    @mock.patch.object(FieldForm, "clean_name", _field_form_clean_name_without_duplicate_check)
    def test_unrelated_integrity_error_is_not_hidden(self):
        with mock.patch.object(Field, "save", side_effect=IntegrityError("other")):
            with self.assertRaises(IntegrityError):
                self.client.post(reverse("core:field_create"), self._field_data("Pole Nowe"))
