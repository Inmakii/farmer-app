"""Field form: the location method comes first and marks the fields that belong to it."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..forms import FieldForm
from ..models import Field


class LocationFieldFormTests(TestCase):
    def test_location_method_comes_before_location_fields(self):
        names = list(FieldForm().fields)

        method = names.index("location_method")
        for name in ("parcel_identifier", "address", "latitude", "longitude"):
            self.assertLess(method, names.index(name), name)

    def test_location_fields_are_tagged_with_their_methods(self):
        form = FieldForm()

        self.assertIn("data-location-method", form.fields["location_method"].widget.attrs)
        expected = {
            "parcel_identifier": "PARCEL",
            "address": "ADDRESS",
            "latitude": "GPS MAP",
            "longitude": "GPS MAP",
        }
        for name, methods in expected.items():
            self.assertEqual(form.fields[name].widget.attrs["data-location-for"], methods)

    def test_values_of_other_methods_are_kept(self):
        # Hiding is only visual; a parcel number saved with an address is not lost.
        form = FieldForm(data={
            "name": "Pole", "area_ha": "2.00", "soil_type": Field.SoilType.LOAMY,
            "location_method": Field.LocationMethod.ADDRESS, "address": "Polna 1",
            "parcel_identifier": "P-1", "latitude": "", "longitude": "", "description": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["parcel_identifier"], "P-1")


class LocationFieldPageTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="location_owner", password="StrongPass!2026"
        )
        self.client.force_login(self.owner)

    def create_field(self, **values):
        return Field.objects.create(
            owner=self.owner, name=values.pop("name", "Pole"), area_ha=Decimal("3.00"),
            soil_type=Field.SoilType.LOAMY, **values,
        )

    def test_add_page_renders_method_select_before_location_inputs(self):
        content = self.client.get(reverse("core:field_create")).content.decode()

        method = content.index('name="location_method"')
        self.assertIn("data-location-method", content)
        for name in ("parcel_identifier", "address", "latitude", "longitude"):
            self.assertLess(method, content.index(f'name="{name}"'), name)

    def test_detail_shows_only_location_data_of_the_method(self):
        field = self.create_field(
            location_method=Field.LocationMethod.ADDRESS, address="Toruń, Polna 2"
        )

        content = self.client.get(reverse("core:field_detail", args=[field.pk])).content.decode()

        self.assertIn("Toruń, Polna 2", content)
        self.assertNotIn("<dt>Szerokość geograficzna</dt>", content)
        self.assertNotIn("<dt>Identyfikator działki</dt>", content)

    def test_detail_still_shows_extra_saved_values(self):
        field = self.create_field(
            location_method=Field.LocationMethod.GPS, latitude=Decimal("53.1"),
            longitude=Decimal("18.1"), parcel_identifier="EXTRA-1",
        )

        content = self.client.get(reverse("core:field_detail", args=[field.pk])).content.decode()

        self.assertIn("EXTRA-1", content)
        self.assertIn("53", content)
