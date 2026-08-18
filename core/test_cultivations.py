from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import CultivationForm
from .models import Crop, Cultivation, Field, FieldWork, Harvest, Spraying


class CultivationCrudTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="cultivation_owner", password="StrongPass!2026"
        )
        self.other_user = user_model.objects.create_user(
            username="other_cultivator", password="StrongPass!2026"
        )
        self.own_field = Field.objects.create(
            owner=self.owner,
            name="Pole Uprawne",
            area_ha=Decimal("10.00"),
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Bydgoszcz",
        )
        self.other_field = Field.objects.create(
            owner=self.other_user,
            name="Cudze Pole",
            area_ha=Decimal("8.00"),
            soil_type=Field.SoilType.SANDY,
            location_method=Field.LocationMethod.PARCEL,
            parcel_identifier="OTHER-1",
        )
        self.wheat = Crop.objects.create(name="Pszenica")
        self.corn = Crop.objects.create(name="Kukurydza")
        self.own_cultivation = Cultivation.objects.create(
            field=self.own_field,
            crop=self.wheat,
            season_year=2026,
            status=Cultivation.Status.ACTIVE,
            sowing_date=date(2026, 3, 20),
            planned_harvest_date=date(2026, 8, 20),
        )
        self.other_cultivation = Cultivation.objects.create(
            field=self.other_field,
            crop=self.corn,
            season_year=2025,
            status=Cultivation.Status.PLANNED,
        )

    def valid_data(self, **overrides):
        data = {
            "field": str(self.own_field.pk),
            "crop": str(self.corn.pk),
            "season_year": "2027",
            "status": Cultivation.Status.PLANNED,
            "sowing_date": "2027-04-10",
            "planned_harvest_date": "2027-09-15",
            "notes": "Uprawa testowa",
        }
        data.update(overrides)
        return data

    def test_anonymous_user_is_redirected_from_list(self):
        response = self.client.get(reverse("core:cultivation_list"))

        expected = (
            f'{reverse("core:login")}?next={reverse("core:cultivation_list")}'
        )
        self.assertRedirects(response, expected)

    def test_list_contains_only_own_cultivations(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("core:cultivation_list"))

        self.assertQuerySetEqual(
            response.context["cultivations"], [self.own_cultivation]
        )
        self.assertNotContains(
            response,
            reverse(
                "core:cultivation_detail", kwargs={"pk": self.other_cultivation.pk}
            ),
        )

    def test_field_filter_does_not_reveal_other_users_data(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:cultivation_list"), {"field": self.other_field.pk}
        )

        self.assertQuerySetEqual(response.context["cultivations"], [])
        self.assertNotContains(response, self.other_field.name)

    def test_filter_by_crop(self):
        second = Cultivation.objects.create(
            field=self.own_field,
            crop=self.corn,
            season_year=2027,
            status=Cultivation.Status.PLANNED,
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:cultivation_list"), {"crop": self.corn.pk}
        )

        self.assertQuerySetEqual(response.context["cultivations"], [second])

    def test_filter_by_status(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:cultivation_list"),
            {"status": Cultivation.Status.ACTIVE},
        )

        self.assertQuerySetEqual(
            response.context["cultivations"], [self.own_cultivation]
        )

    def test_filter_by_season_year(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:cultivation_list"), {"season_year": 2026}
        )

        self.assertQuerySetEqual(
            response.context["cultivations"], [self.own_cultivation]
        )

    def test_form_contains_only_current_users_fields(self):
        form = CultivationForm(user=self.owner)

        self.assertQuerySetEqual(form.fields["field"].queryset, [self.own_field])
        self.assertNotIn(self.other_field, form.fields["field"].queryset)

    def test_form_rejects_other_users_field_from_post(self):
        form = CultivationForm(
            data=self.valid_data(field=str(self.other_field.pk)), user=self.owner
        )

        self.assertFalse(form.is_valid())
        self.assertIn("field", form.errors)

    def test_valid_cultivation_can_be_created(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("core:cultivation_create"), self.valid_data()
        )

        cultivation = Cultivation.objects.get(
            field=self.own_field, crop=self.corn, season_year=2027
        )
        self.assertRedirects(
            response,
            reverse("core:cultivation_detail", kwargs={"pk": cultivation.pk}),
        )

    def test_created_cultivation_has_selected_field_and_crop(self):
        self.client.force_login(self.owner)

        self.client.post(reverse("core:cultivation_create"), self.valid_data())

        cultivation = Cultivation.objects.get(season_year=2027)
        self.assertEqual(cultivation.field, self.own_field)
        self.assertEqual(cultivation.crop, self.corn)

    def test_year_below_2000_is_rejected(self):
        form = CultivationForm(
            data=self.valid_data(season_year="1999"), user=self.owner
        )

        self.assertFalse(form.is_valid())
        self.assertIn("season_year", form.errors)

    def test_year_above_2100_is_rejected(self):
        form = CultivationForm(
            data=self.valid_data(season_year="2101"), user=self.owner
        )

        self.assertFalse(form.is_valid())
        self.assertIn("season_year", form.errors)

    def test_harvest_date_before_sowing_date_is_rejected(self):
        form = CultivationForm(
            data=self.valid_data(
                sowing_date="2027-05-10", planned_harvest_date="2027-05-09"
            ),
            user=self.owner,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("planned_harvest_date", form.errors)

    def test_duplicate_field_crop_and_year_is_rejected(self):
        form = CultivationForm(
            data=self.valid_data(
                crop=str(self.wheat.pk), season_year="2026"
            ),
            user=self.owner,
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "Taka uprawa jest już przypisana do tego pola i sezonu.",
            form.non_field_errors(),
        )

    def test_owner_can_open_cultivation_detail(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse(
                "core:cultivation_detail", kwargs={"pk": self.own_cultivation.pk}
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cultivation"], self.own_cultivation)

    def test_other_user_gets_404_for_detail(self):
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "core:cultivation_detail", kwargs={"pk": self.own_cultivation.pk}
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_other_user_gets_404_for_update(self):
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "core:cultivation_update", kwargs={"pk": self.own_cultivation.pk}
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_other_user_gets_404_for_delete(self):
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "core:cultivation_delete", kwargs={"pk": self.own_cultivation.pk}
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_owner_can_update_cultivation(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse(
                "core:cultivation_update", kwargs={"pk": self.own_cultivation.pk}
            ),
            self.valid_data(
                crop=str(self.wheat.pk),
                season_year="2026",
                status=Cultivation.Status.COMPLETED,
            ),
        )

        self.own_cultivation.refresh_from_db()
        self.assertEqual(self.own_cultivation.status, Cultivation.Status.COMPLETED)
        self.assertRedirects(
            response,
            reverse(
                "core:cultivation_detail", kwargs={"pk": self.own_cultivation.pk}
            ),
        )

    def test_owner_can_delete_with_post(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse(
                "core:cultivation_delete", kwargs={"pk": self.own_cultivation.pk}
            )
        )

        self.assertRedirects(response, reverse("core:cultivation_list"))
        self.assertFalse(
            Cultivation.objects.filter(pk=self.own_cultivation.pk).exists()
        )

    def test_get_does_not_delete_cultivation(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse(
                "core:cultivation_delete", kwargs={"pk": self.own_cultivation.pk}
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Cultivation.objects.filter(pk=self.own_cultivation.pk).exists()
        )

    def test_get_field_sets_initial_value_for_own_field(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:cultivation_create"), {"field": self.own_field.pk}
        )

        self.assertEqual(response.context["form"].initial["field"], self.own_field)

    def test_get_field_does_not_set_other_users_field(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("core:cultivation_create"), {"field": self.other_field.pk}
        )

        self.assertNotIn("field", response.context["form"].initial)
        self.assertNotIn(
            self.other_field, response.context["form"].fields["field"].queryset
        )

    def test_detail_shows_related_object_counts(self):
        FieldWork.objects.create(
            cultivation=self.own_cultivation,
            work_type=FieldWork.WorkType.SOWING,
            work_date=date(2026, 3, 20),
            cost=Decimal("100.00"),
        )
        Spraying.objects.create(
            cultivation=self.own_cultivation,
            spraying_date=date(2026, 5, 10),
            product_name="Preparat testowy",
            quantity=Decimal("2.00"),
            unit=Spraying.Unit.L,
            cost=Decimal("50.00"),
        )
        Harvest.objects.create(
            cultivation=self.own_cultivation,
            harvest_date=date(2026, 8, 18),
            quantity=Decimal("10.00"),
            unit=Harvest.Unit.T,
            revenue=Decimal("1000.00"),
            harvest_cost=Decimal("200.00"),
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse(
                "core:cultivation_detail", kwargs={"pk": self.own_cultivation.pk}
            )
        )

        self.assertEqual(response.context["work_count"], 1)
        self.assertEqual(response.context["spraying_count"], 1)
        self.assertEqual(response.context["harvest_count"], 1)
