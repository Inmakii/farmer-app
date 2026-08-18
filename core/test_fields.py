from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import FieldForm
from .models import Field


class FieldCrudTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="field_owner", password="StrongPass!2026"
        )
        self.other_user = user_model.objects.create_user(
            username="other_farmer", password="StrongPass!2026"
        )
        self.own_field = Field.objects.create(
            owner=self.owner,
            name="Pole Własne",
            area_ha=Decimal("10.00"),
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Bydgoszcz, ul. Rolna 1",
            parcel_identifier="OWN-123",
        )
        self.other_field = Field.objects.create(
            owner=self.other_user,
            name="Tajne Pole Sąsiada",
            area_ha=Decimal("7.00"),
            soil_type=Field.SoilType.SANDY,
            location_method=Field.LocationMethod.GPS,
            latitude=Decimal("53.100000"),
            longitude=Decimal("18.100000"),
            parcel_identifier="OTHER-456",
        )

    def valid_field_data(self, **overrides):
        data = {
            "name": "Nowe Pole",
            "area_ha": "5.50",
            "soil_type": Field.SoilType.CLAY,
            "parcel_identifier": "",
            "location_method": Field.LocationMethod.ADDRESS,
            "address": "Toruń, ul. Polna 2",
            "latitude": "",
            "longitude": "",
            "description": "Pole testowe",
        }
        data.update(overrides)
        return data

    def test_anonymous_user_is_redirected_from_field_list(self):
        response = self.client.get(reverse("core:field_list"))

        expected = f'{reverse("core:login")}?next={reverse("core:field_list")}'
        self.assertRedirects(response, expected)

    def test_field_list_contains_only_current_users_fields(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("core:field_list"))

        self.assertContains(response, self.own_field.name)
        self.assertNotContains(response, self.other_field.name)
        self.assertQuerySetEqual(response.context["fields"], [self.own_field])

    def test_search_does_not_reveal_other_users_fields(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:field_list"), {"q": "Tajne Pole Sąsiada"}
        )

        self.assertQuerySetEqual(response.context["fields"], [])
        self.assertNotContains(
            response,
            reverse("core:field_detail", kwargs={"pk": self.other_field.pk}),
        )

    def test_filter_by_soil_type(self):
        second_field = Field.objects.create(
            owner=self.owner,
            name="Pole Piaszczyste",
            area_ha=Decimal("2.00"),
            soil_type=Field.SoilType.SANDY,
            location_method=Field.LocationMethod.PARCEL,
            parcel_identifier="SAND-1",
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:field_list"), {"soil_type": Field.SoilType.SANDY}
        )

        self.assertQuerySetEqual(response.context["fields"], [second_field])

    def test_filter_by_location_method(self):
        gps_field = Field.objects.create(
            owner=self.owner,
            name="Pole GPS",
            area_ha=Decimal("3.00"),
            soil_type=Field.SoilType.PEAT,
            location_method=Field.LocationMethod.GPS,
            latitude=Decimal("52.000000"),
            longitude=Decimal("19.000000"),
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:field_list"),
            {"location_method": Field.LocationMethod.GPS},
        )

        self.assertQuerySetEqual(response.context["fields"], [gps_field])

    def test_create_assigns_authenticated_user_as_owner(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("core:field_create"),
            self.valid_field_data(owner=self.other_user.pk),
        )

        created_field = Field.objects.get(name="Nowe Pole")
        self.assertEqual(created_field.owner, self.owner)
        self.assertRedirects(
            response, reverse("core:field_detail", kwargs={"pk": created_field.pk})
        )

    def test_owner_is_not_present_in_field_form(self):
        form = FieldForm(user=self.owner)

        self.assertNotIn("owner", form.fields)
        self.assertNotIn("created_at", form.fields)
        self.assertNotIn("updated_at", form.fields)

    def test_zero_area_is_rejected(self):
        form = FieldForm(data=self.valid_field_data(area_ha="0"), user=self.owner)

        self.assertFalse(form.is_valid())
        self.assertIn("area_ha", form.errors)

    def test_duplicate_name_is_rejected_case_insensitively(self):
        form = FieldForm(
            data=self.valid_field_data(name="pole własne"), user=self.owner
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["name"], ["Masz już pole o tej nazwie."])

    def test_address_location_requires_address(self):
        invalid_form = FieldForm(
            data=self.valid_field_data(address=""), user=self.owner
        )
        valid_form = FieldForm(data=self.valid_field_data(), user=self.owner)

        self.assertFalse(invalid_form.is_valid())
        self.assertIn("address", invalid_form.errors)
        self.assertTrue(valid_form.is_valid(), valid_form.errors)

    def test_gps_location_requires_both_coordinates(self):
        invalid_form = FieldForm(
            data=self.valid_field_data(
                location_method=Field.LocationMethod.GPS,
                address="",
                latitude="",
                longitude="",
            ),
            user=self.owner,
        )
        valid_form = FieldForm(
            data=self.valid_field_data(
                location_method=Field.LocationMethod.GPS,
                address="",
                latitude="52.123456",
                longitude="18.123456",
            ),
            user=self.owner,
        )

        self.assertFalse(invalid_form.is_valid())
        self.assertIn("latitude", invalid_form.errors)
        self.assertIn("longitude", invalid_form.errors)
        self.assertTrue(valid_form.is_valid(), valid_form.errors)

    def test_coordinate_ranges_are_validated(self):
        form = FieldForm(
            data=self.valid_field_data(
                location_method=Field.LocationMethod.MAP,
                address="",
                latitude="90.000001",
                longitude="-180.000001",
            ),
            user=self.owner,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("latitude", form.errors)
        self.assertIn("longitude", form.errors)

    def test_owner_can_open_field_detail(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:field_detail", kwargs={"pk": self.own_field.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["field"], self.own_field)

    def test_other_user_gets_404_for_field_detail(self):
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse("core:field_detail", kwargs={"pk": self.own_field.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_other_user_gets_404_for_field_update(self):
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse("core:field_update", kwargs={"pk": self.own_field.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_other_user_gets_404_for_field_delete(self):
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse("core:field_delete", kwargs={"pk": self.own_field.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_owner_can_update_field(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("core:field_update", kwargs={"pk": self.own_field.pk}),
            self.valid_field_data(name="Pole Zaktualizowane"),
        )

        self.own_field.refresh_from_db()
        self.assertEqual(self.own_field.name, "Pole Zaktualizowane")
        self.assertRedirects(
            response,
            reverse("core:field_detail", kwargs={"pk": self.own_field.pk}),
        )

    def test_owner_can_delete_field_with_post(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("core:field_delete", kwargs={"pk": self.own_field.pk})
        )

        self.assertRedirects(response, reverse("core:field_list"))
        self.assertFalse(Field.objects.filter(pk=self.own_field.pk).exists())

    def test_get_does_not_delete_field(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:field_delete", kwargs={"pk": self.own_field.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Field.objects.filter(pk=self.own_field.pk).exists())

    def test_update_cannot_change_owner(self):
        self.client.force_login(self.owner)

        self.client.post(
            reverse("core:field_update", kwargs={"pk": self.own_field.pk}),
            self.valid_field_data(
                name=self.own_field.name, owner=self.other_user.pk
            ),
        )

        self.own_field.refresh_from_db()
        self.assertEqual(self.own_field.owner, self.owner)
