from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Crop, Cultivation, Field, FieldWork, Harvest


class FarmModelsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="farmer", password="test-password"
        )
        self.field = Field.objects.create(
            owner=self.user,
            name="Pole północne",
            area_ha=Decimal("12.50"),
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.GPS,
            latitude=Decimal("52.229676"),
            longitude=Decimal("21.012229"),
        )
        self.crop = Crop.objects.create(name="Pszenica")
        self.cultivation = Cultivation.objects.create(
            field=self.field,
            crop=self.crop,
            season_year=2026,
            status=Cultivation.Status.ACTIVE,
        )

    def test_create_field_with_valid_data(self):
        self.field.full_clean()
        self.assertEqual(self.field.owner, self.user)
        self.assertEqual(self.field.area_ha, Decimal("12.50"))

    def test_zero_field_area_is_rejected(self):
        invalid_field = Field(
            owner=self.user,
            name="Pole zerowe",
            area_ha=Decimal("0"),
            soil_type=Field.SoilType.SANDY,
            location_method=Field.LocationMethod.ADDRESS,
        )

        with self.assertRaises(ValidationError):
            invalid_field.full_clean()

    def test_field_name_must_be_unique_for_owner(self):
        duplicate = Field(
            owner=self.user,
            name=self.field.name,
            area_ha=Decimal("1.00"),
            soil_type=Field.SoilType.CLAY,
            location_method=Field.LocationMethod.PARCEL,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_negative_work_cost_is_rejected(self):
        work = FieldWork(
            cultivation=self.cultivation,
            work_type=FieldWork.WorkType.PLOWING,
            work_date=date(2026, 3, 1),
            cost=Decimal("-0.01"),
        )

        with self.assertRaises(ValidationError):
            work.full_clean()

    def test_harvest_profit(self):
        harvest = Harvest(
            cultivation=self.cultivation,
            harvest_date=date(2026, 8, 15),
            quantity=Decimal("10.00"),
            unit=Harvest.Unit.T,
            revenue=Decimal("15000.00"),
            harvest_cost=Decimal("3500.50"),
        )

        self.assertEqual(harvest.profit, Decimal("11499.50"))
