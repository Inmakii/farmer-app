from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import HarvestForm
from .models import Crop, Cultivation, Field, Harvest


class HarvestCrudTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user(username="harvester", password="StrongPass!2026")
        self.other = users.objects.create_user(username="other_harvester", password="StrongPass!2026")
        self.field = Field.objects.create(owner=self.owner, name="Moje Pole Zbiorów", area_ha=Decimal("9.00"), soil_type=Field.SoilType.LOAMY, location_method=Field.LocationMethod.ADDRESS, address="Toruń")
        self.other_field = Field.objects.create(owner=self.other, name="Cudze Pole Zbiorów", area_ha=Decimal("8.00"), soil_type=Field.SoilType.SANDY, location_method=Field.LocationMethod.PARCEL, parcel_identifier="HAR-2")
        self.crop = Crop.objects.create(name="Pszenica zbiorowa")
        self.other_crop = Crop.objects.create(name="Kukurydza zbiorowa")
        self.cultivation = Cultivation.objects.create(field=self.field, crop=self.crop, season_year=2026, status=Cultivation.Status.ACTIVE)
        self.other_cultivation = Cultivation.objects.create(field=self.other_field, crop=self.other_crop, season_year=2026, status=Cultivation.Status.ACTIVE)
        self.harvest = Harvest.objects.create(cultivation=self.cultivation, harvest_date=date(2026, 8, 10), quantity=Decimal("12.00"), unit=Harvest.Unit.T, revenue=Decimal("12000.00"), harvest_cost=Decimal("2000.00"), notes="Własny zbiór")
        self.other_harvest = Harvest.objects.create(cultivation=self.other_cultivation, harvest_date=date(2026, 9, 10), quantity=Decimal("15.00"), unit=Harvest.Unit.T, revenue=Decimal("15000.00"), harvest_cost=Decimal("2500.00"), notes="Tajny cudzy zbiór")

    def data(self, **overrides):
        values = {"cultivation": str(self.cultivation.pk), "harvest_date": "2026-08-20", "quantity": "5.50", "unit": Harvest.Unit.T, "revenue": "6000.00", "harvest_cost": "1000.00", "notes": "Nowy zbiór"}
        values.update(overrides)
        return values

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("core:harvest_list"))
        self.assertRedirects(response, f'{reverse("core:login")}?next={reverse("core:harvest_list")}')

    def test_list_only_own_harvests(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_list"))
        self.assertQuerySetEqual(response.context["harvests"], [self.harvest])

    def test_search_does_not_reveal_other_data(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_list"), {"q": "Tajny cudzy zbiór"})
        self.assertQuerySetEqual(response.context["harvests"], [])
        self.assertNotContains(response, reverse("core:harvest_detail", kwargs={"pk": self.other_harvest.pk}))

    def test_filter_cultivation(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_list"), {"cultivation": self.cultivation.pk})
        self.assertQuerySetEqual(response.context["harvests"], [self.harvest])

    def test_filter_field(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_list"), {"field": self.field.pk})
        self.assertQuerySetEqual(response.context["harvests"], [self.harvest])

    def test_filter_unit(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_list"), {"unit": Harvest.Unit.T})
        self.assertQuerySetEqual(response.context["harvests"], [self.harvest])

    def test_filter_dates(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_list"), {"date_from": "2026-08-01", "date_to": "2026-08-31"})
        self.assertQuerySetEqual(response.context["harvests"], [self.harvest])

    def test_invalid_date_does_not_fail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_list"), {"date_from": "wrong", "date_to": "2026-99-99"})
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["harvests"], [self.harvest])

    def test_form_only_own_cultivations(self):
        form = HarvestForm(user=self.owner)
        self.assertQuerySetEqual(form.fields["cultivation"].queryset, [self.cultivation])
        self.assertIn(self.field.name, form.fields["cultivation"].label_from_instance(self.cultivation))

    def test_form_rejects_other_cultivation(self):
        form = HarvestForm(data=self.data(cultivation=str(self.other_cultivation.pk)), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("cultivation", form.errors)

    def test_valid_create(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:harvest_create"), self.data())
        created = Harvest.objects.get(notes="Nowy zbiór")
        self.assertRedirects(response, reverse("core:harvest_detail", kwargs={"pk": created.pk}))

    def test_created_relation(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("core:harvest_create"), self.data())
        self.assertEqual(Harvest.objects.get(notes="Nowy zbiór").cultivation, self.cultivation)

    def test_zero_quantity_rejected(self):
        form = HarvestForm(data=self.data(quantity="0"), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("quantity", form.errors)

    def test_negative_quantity_rejected(self):
        form = HarvestForm(data=self.data(quantity="-1"), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("quantity", form.errors)

    def test_negative_revenue_rejected(self):
        form = HarvestForm(data=self.data(revenue="-0.01"), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("revenue", form.errors)

    def test_zero_revenue_accepted(self):
        form = HarvestForm(data=self.data(revenue="0"), user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)

    def test_negative_harvest_cost_rejected(self):
        form = HarvestForm(data=self.data(harvest_cost="-0.01"), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("harvest_cost", form.errors)

    def test_zero_harvest_cost_accepted(self):
        form = HarvestForm(data=self.data(harvest_cost="0"), user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)

    def test_profit_calculation(self):
        self.assertEqual(self.harvest.profit, Decimal("10000.00"))

    def test_owner_sees_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_detail", kwargs={"pk": self.harvest.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["harvest"], self.harvest)
        self.assertEqual(response.context["harvest"].profit, Decimal("10000.00"))
        self.assertContains(response, "Wynik zbioru")

    def test_other_gets_404_detail(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("core:harvest_detail", kwargs={"pk": self.harvest.pk})).status_code, 404)

    def test_other_gets_404_update(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("core:harvest_update", kwargs={"pk": self.harvest.pk})).status_code, 404)

    def test_other_gets_404_delete(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("core:harvest_delete", kwargs={"pk": self.harvest.pk})).status_code, 404)

    def test_owner_can_update(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:harvest_update", kwargs={"pk": self.harvest.pk}), self.data(notes="Zmieniony zbiór"))
        self.harvest.refresh_from_db()
        self.assertEqual(self.harvest.notes, "Zmieniony zbiór")
        self.assertRedirects(response, reverse("core:harvest_detail", kwargs={"pk": self.harvest.pk}))

    def test_update_cannot_move_to_other_cultivation(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:harvest_update", kwargs={"pk": self.harvest.pk}), self.data(cultivation=str(self.other_cultivation.pk)))
        self.harvest.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.harvest.cultivation, self.cultivation)

    def test_delete_with_post(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:harvest_delete", kwargs={"pk": self.harvest.pk}))
        self.assertRedirects(response, reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}))
        self.assertFalse(Harvest.objects.filter(pk=self.harvest.pk).exists())

    def test_get_does_not_delete(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_delete", kwargs={"pk": self.harvest.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Harvest.objects.filter(pk=self.harvest.pk).exists())

    def test_get_cultivation_sets_own_initial(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_create"), {"cultivation": self.cultivation.pk})
        self.assertEqual(response.context["form"].initial["cultivation"], self.cultivation)

    def test_get_cultivation_does_not_set_other_initial(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:harvest_create"), {"cultivation": self.other_cultivation.pk})
        self.assertNotIn("cultivation", response.context["form"].initial)

    def test_cultivation_detail_only_its_harvests_and_count(self):
        second = Cultivation.objects.create(field=self.field, crop=self.other_crop, season_year=2027, status=Cultivation.Status.PLANNED)
        unrelated = Harvest.objects.create(cultivation=second, harvest_date=date(2027, 9, 1), quantity=Decimal("1"), unit=Harvest.Unit.T, revenue=Decimal("100"), harvest_cost=Decimal("0"))
        Harvest.objects.create(cultivation=self.cultivation, harvest_date=date(2026, 8, 20), quantity=Decimal("1"), unit=Harvest.Unit.T, revenue=Decimal("100"), harvest_cost=Decimal("0"))
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}))
        self.assertEqual(response.context["harvest_count"], 2)
        self.assertEqual(list(response.context["harvests"]), list(self.cultivation.harvests.order_by("-harvest_date", "-id")))
        self.assertNotContains(response, reverse("core:harvest_detail", kwargs={"pk": unrelated.pk}))
