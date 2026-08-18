from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import FieldWorkForm
from .models import Crop, Cultivation, Field, FieldWork


class FieldWorkCrudTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user(username="worker", password="StrongPass!2026")
        self.other = users.objects.create_user(username="other_worker", password="StrongPass!2026")
        self.field = Field.objects.create(owner=self.owner, name="Moje Pole", area_ha=Decimal("4.00"), soil_type=Field.SoilType.LOAMY, location_method=Field.LocationMethod.ADDRESS, address="Toruń")
        self.other_field = Field.objects.create(owner=self.other, name="Cudze Pole", area_ha=Decimal("5.00"), soil_type=Field.SoilType.SANDY, location_method=Field.LocationMethod.PARCEL, parcel_identifier="X-1")
        self.crop = Crop.objects.create(name="Pszenica")
        self.other_crop = Crop.objects.create(name="Kukurydza")
        self.cultivation = Cultivation.objects.create(field=self.field, crop=self.crop, season_year=2026, status=Cultivation.Status.ACTIVE)
        self.other_cultivation = Cultivation.objects.create(field=self.other_field, crop=self.other_crop, season_year=2026, status=Cultivation.Status.ACTIVE)
        self.work = FieldWork.objects.create(cultivation=self.cultivation, work_type=FieldWork.WorkType.PLOWING, work_date=date(2026, 3, 10), cost=Decimal("100.00"), description="Głęboka orka")
        self.other_work = FieldWork.objects.create(cultivation=self.other_cultivation, work_type=FieldWork.WorkType.SOWING, work_date=date(2026, 4, 10), cost=Decimal("200.00"), description="Cudzy siew")

    def data(self, **overrides):
        values = {"cultivation": str(self.cultivation.pk), "work_type": FieldWork.WorkType.SOWING, "work_date": "2026-04-01", "cost": "50.00", "description": "Nowa praca"}
        values.update(overrides)
        return values

    def test_anonymous_redirected_from_list(self):
        response = self.client.get(reverse("core:fieldwork_list"))
        self.assertRedirects(response, f'{reverse("core:login")}?next={reverse("core:fieldwork_list")}')

    def test_list_shows_only_own_works(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_list"))
        self.assertQuerySetEqual(response.context["works"], [self.work])

    def test_search_does_not_reveal_other_works(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_list"), {"q": "Cudzy siew"})
        self.assertQuerySetEqual(response.context["works"], [])
        self.assertNotContains(response, reverse("core:fieldwork_detail", kwargs={"pk": self.other_work.pk}))

    def test_filter_cultivation(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_list"), {"cultivation": self.cultivation.pk})
        self.assertQuerySetEqual(response.context["works"], [self.work])

    def test_filter_field(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_list"), {"field": self.field.pk})
        self.assertQuerySetEqual(response.context["works"], [self.work])

    def test_filter_work_type(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_list"), {"work_type": FieldWork.WorkType.PLOWING})
        self.assertQuerySetEqual(response.context["works"], [self.work])

    def test_filter_date_range(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_list"), {"date_from": "2026-03-01", "date_to": "2026-03-31"})
        self.assertQuerySetEqual(response.context["works"], [self.work])

    def test_invalid_filter_date_does_not_fail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_list"), {"date_from": "not-a-date", "date_to": "2026-99-99"})
        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["works"], [self.work])

    def test_form_shows_only_own_cultivations(self):
        form = FieldWorkForm(user=self.owner)
        self.assertQuerySetEqual(form.fields["cultivation"].queryset, [self.cultivation])
        self.assertIn(self.field.name, form.fields["cultivation"].label_from_instance(self.cultivation))

    def test_form_rejects_other_cultivation(self):
        form = FieldWorkForm(data=self.data(cultivation=str(self.other_cultivation.pk)), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("cultivation", form.errors)

    def test_create_work(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:fieldwork_create"), self.data())
        created = FieldWork.objects.get(description="Nowa praca")
        self.assertRedirects(response, reverse("core:fieldwork_detail", kwargs={"pk": created.pk}))

    def test_created_work_keeps_cultivation_relation(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("core:fieldwork_create"), self.data())
        self.assertEqual(FieldWork.objects.get(description="Nowa praca").cultivation, self.cultivation)

    def test_negative_cost_rejected(self):
        form = FieldWorkForm(data=self.data(cost="-0.01"), user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("cost", form.errors)

    def test_zero_cost_accepted(self):
        form = FieldWorkForm(data=self.data(cost="0"), user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)

    def test_owner_sees_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_detail", kwargs={"pk": self.work.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["work"], self.work)

    def test_other_user_gets_404_detail(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("core:fieldwork_detail", kwargs={"pk": self.work.pk})).status_code, 404)

    def test_other_user_gets_404_update(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("core:fieldwork_update", kwargs={"pk": self.work.pk})).status_code, 404)

    def test_other_user_gets_404_delete(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("core:fieldwork_delete", kwargs={"pk": self.work.pk})).status_code, 404)

    def test_owner_can_update(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:fieldwork_update", kwargs={"pk": self.work.pk}), self.data(work_type=FieldWork.WorkType.WEEDING, description="Aktualizacja"))
        self.work.refresh_from_db()
        self.assertEqual(self.work.work_type, FieldWork.WorkType.WEEDING)
        self.assertRedirects(response, reverse("core:fieldwork_detail", kwargs={"pk": self.work.pk}))

    def test_update_cannot_move_to_other_cultivation(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:fieldwork_update", kwargs={"pk": self.work.pk}), self.data(cultivation=str(self.other_cultivation.pk)))
        self.work.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.work.cultivation, self.cultivation)

    def test_owner_can_delete_with_post(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("core:fieldwork_delete", kwargs={"pk": self.work.pk}))
        self.assertRedirects(response, reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}))
        self.assertFalse(FieldWork.objects.filter(pk=self.work.pk).exists())

    def test_get_does_not_delete(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_delete", kwargs={"pk": self.work.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(FieldWork.objects.filter(pk=self.work.pk).exists())

    def test_get_cultivation_sets_own_initial(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_create"), {"cultivation": self.cultivation.pk})
        self.assertEqual(response.context["form"].initial["cultivation"], self.cultivation)

    def test_get_cultivation_does_not_set_other_initial(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:fieldwork_create"), {"cultivation": self.other_cultivation.pk})
        self.assertNotIn("cultivation", response.context["form"].initial)

    def test_cultivation_detail_shows_only_its_works(self):
        second = Cultivation.objects.create(field=self.field, crop=self.other_crop, season_year=2027, status=Cultivation.Status.PLANNED)
        unrelated = FieldWork.objects.create(cultivation=second, work_type=FieldWork.WorkType.OTHER, work_date=date(2027, 1, 1), cost=Decimal("0"))
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}))
        self.assertQuerySetEqual(response.context["works"], [self.work])
        self.assertNotContains(response, reverse("core:fieldwork_detail", kwargs={"pk": unrelated.pk}))

    def test_cultivation_detail_shows_correct_work_count(self):
        FieldWork.objects.create(cultivation=self.cultivation, work_type=FieldWork.WorkType.SOWING, work_date=date(2026, 4, 1), cost=Decimal("0"))
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}))
        self.assertEqual(response.context["work_count"], 2)
