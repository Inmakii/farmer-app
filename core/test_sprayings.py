from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import SprayingForm
from .models import Crop, Cultivation, Field, Spraying


class SprayingCrudTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user(username="sprayer", password="StrongPass!2026")
        self.other = users.objects.create_user(username="other_sprayer", password="StrongPass!2026")
        self.field = Field.objects.create(owner=self.owner, name="Moje Pole Opryskowe", area_ha=Decimal("6.00"), soil_type=Field.SoilType.LOAMY, location_method=Field.LocationMethod.ADDRESS, address="Toruń")
        self.other_field = Field.objects.create(owner=self.other, name="Cudze Pole Opryskowe", area_ha=Decimal("7.00"), soil_type=Field.SoilType.SANDY, location_method=Field.LocationMethod.PARCEL, parcel_identifier="SPR-2")
        self.crop = Crop.objects.create(name="Pszenica opryskowa")
        self.other_crop = Crop.objects.create(name="Kukurydza opryskowa")
        self.cultivation = Cultivation.objects.create(field=self.field, crop=self.crop, season_year=2026, status=Cultivation.Status.ACTIVE)
        self.other_cultivation = Cultivation.objects.create(field=self.other_field, crop=self.other_crop, season_year=2026, status=Cultivation.Status.ACTIVE)
        self.spraying = Spraying.objects.create(cultivation=self.cultivation, spraying_date=date(2026, 5, 10), product_name="Herbicyd Własny", quantity=Decimal("2.50"), unit=Spraying.Unit.L, cost=Decimal("120.00"), description="Oprysk własny")
        self.other_spraying = Spraying.objects.create(cultivation=self.other_cultivation, spraying_date=date(2026, 6, 10), product_name="Tajny Preparat", quantity=Decimal("3.00"), unit=Spraying.Unit.KG, cost=Decimal("220.00"), description="Cudzy oprysk")

    def data(self, **overrides):
        values = {"cultivation": str(self.cultivation.pk), "spraying_date": "2026-05-20", "product_name": "Fungicyd Nowy", "quantity": "1.50", "unit": Spraying.Unit.L, "cost": "80.00", "description": "Nowy oprysk"}
        values.update(overrides)
        return values

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("core:spraying_list"))
        self.assertRedirects(response, f'{reverse("core:login")}?next={reverse("core:spraying_list")}')

    def test_list_only_own_sprayings(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_list"))
        self.assertQuerySetEqual(response.context["sprayings"], [self.spraying])

    def test_search_does_not_reveal_other_data(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_list"), {"q": "Tajny Preparat"})
        self.assertQuerySetEqual(response.context["sprayings"], [])
        self.assertNotContains(response, reverse("core:spraying_detail", kwargs={"pk": self.other_spraying.pk}))

    def test_filter_cultivation(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_list"), {"cultivation": self.cultivation.pk})
        self.assertQuerySetEqual(response.context["sprayings"], [self.spraying])

    def test_filter_field(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_list"), {"field": self.field.pk})
        self.assertQuerySetEqual(response.context["sprayings"], [self.spraying])

    def test_filter_unit(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_list"), {"unit": Spraying.Unit.L})
        self.assertQuerySetEqual(response.context["sprayings"], [self.spraying])

    def test_filter_date_range(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_list"), {"date_from": "2026-05-01", "date_to": "2026-05-31"})
        self.assertQuerySetEqual(response.context["sprayings"], [self.spraying])

    def test_invalid_date_filter_does_not_fail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_list"), {"date_from": "wrong", "date_to": "2026-99-99"})
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["sprayings"], [self.spraying])

    def test_form_only_own_cultivations(self):
        form = SprayingForm(user=self.owner)
        self.assertQuerySetEqual(form.fields["cultivation"].queryset, [self.cultivation])
        self.assertIn(self.field.name, form.fields["cultivation"].label_from_instance(self.cultivation))

    def test_form_rejects_other_cultivation(self):
        form = SprayingForm(data=self.data(cultivation=str(self.other_cultivation.pk)), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("cultivation", form.errors)

    def test_valid_create(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:spraying_create"), self.data())
        created = Spraying.objects.get(product_name="Fungicyd Nowy")
        self.assertRedirects(response, reverse("core:spraying_detail", kwargs={"pk": created.pk}))

    def test_created_relation(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("core:spraying_create"), self.data())
        self.assertEqual(Spraying.objects.get(product_name="Fungicyd Nowy").cultivation, self.cultivation)

    def test_zero_quantity_rejected(self):
        form = SprayingForm(data=self.data(quantity="0"), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("quantity", form.errors)

    def test_negative_quantity_rejected(self):
        form = SprayingForm(data=self.data(quantity="-1"), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("quantity", form.errors)

    def test_negative_cost_rejected(self):
        form = SprayingForm(data=self.data(cost="-0.01"), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("cost", form.errors)

    def test_zero_cost_accepted(self):
        form = SprayingForm(data=self.data(cost="0"), user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)

    def test_owner_sees_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_detail", kwargs={"pk": self.spraying.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["spraying"], self.spraying)

    def test_other_gets_404_detail(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("core:spraying_detail", kwargs={"pk": self.spraying.pk})).status_code, 404)

    def test_other_gets_404_update(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("core:spraying_update", kwargs={"pk": self.spraying.pk})).status_code, 404)

    def test_other_gets_404_delete(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("core:spraying_delete", kwargs={"pk": self.spraying.pk})).status_code, 404)

    def test_owner_can_update(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:spraying_update", kwargs={"pk": self.spraying.pk}), self.data(product_name="Preparat Zmieniony"))
        self.spraying.refresh_from_db()
        self.assertEqual(self.spraying.product_name, "Preparat Zmieniony")
        self.assertRedirects(response, reverse("core:spraying_detail", kwargs={"pk": self.spraying.pk}))

    def test_update_cannot_move_to_other_cultivation(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:spraying_update", kwargs={"pk": self.spraying.pk}), self.data(cultivation=str(self.other_cultivation.pk)))
        self.spraying.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.spraying.cultivation, self.cultivation)

    def test_owner_deletes_with_post(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:spraying_delete", kwargs={"pk": self.spraying.pk}))
        self.assertRedirects(response, reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}))
        self.assertFalse(Spraying.objects.filter(pk=self.spraying.pk).exists())

    def test_get_does_not_delete(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_delete", kwargs={"pk": self.spraying.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Spraying.objects.filter(pk=self.spraying.pk).exists())

    def test_get_cultivation_sets_own_initial(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_create"), {"cultivation": self.cultivation.pk})
        self.assertEqual(response.context["form"].initial["cultivation"], self.cultivation)

    def test_get_cultivation_does_not_set_other_initial(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:spraying_create"), {"cultivation": self.other_cultivation.pk})
        self.assertNotIn("cultivation", response.context["form"].initial)

    def test_cultivation_detail_only_its_sprayings(self):
        second = Cultivation.objects.create(field=self.field, crop=self.other_crop, season_year=2027, status=Cultivation.Status.PLANNED)
        unrelated = Spraying.objects.create(cultivation=second, spraying_date=date(2027, 5, 1), product_name="Inny własny", quantity=Decimal("1"), unit=Spraying.Unit.L, cost=Decimal("0"))
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}))
        self.assertQuerySetEqual(response.context["sprayings"], [self.spraying])
        self.assertNotContains(response, reverse("core:spraying_detail", kwargs={"pk": unrelated.pk}))

    def test_cultivation_detail_correct_spraying_count(self):
        Spraying.objects.create(cultivation=self.cultivation, spraying_date=date(2026, 5, 20), product_name="Drugi", quantity=Decimal("1"), unit=Spraying.Unit.L, cost=Decimal("0"))
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}))
        self.assertEqual(response.context["spraying_count"], 2)
