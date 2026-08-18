from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from .models import Crop, Cultivation, Field, FieldWork, Harvest, Spraying


class SeedDemoDataCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="demo_farmer", password="test-password"
        )

    def run_command(self):
        output = StringIO()
        call_command("seed_demo_data", username=self.user.username, stdout=output)
        return output.getvalue()

    def test_command_creates_demo_data(self):
        output = self.run_command()

        self.assertEqual(Crop.objects.count(), 4)
        self.assertEqual(Field.objects.filter(owner=self.user).count(), 2)
        self.assertEqual(Cultivation.objects.count(), 2)
        self.assertEqual(FieldWork.objects.count(), 4)
        self.assertEqual(Spraying.objects.count(), 2)
        self.assertEqual(Harvest.objects.count(), 2)
        north_field = Field.objects.get(owner=self.user, name="Pole Północne")
        self.assertEqual(north_field.area_ha, Decimal("12.50"))
        self.assertEqual(north_field.latitude, Decimal("53.123456"))
        self.assertEqual(north_field.longitude, Decimal("18.123456"))
        wheat = Cultivation.objects.get(field=north_field, crop__name="Pszenica")
        self.assertEqual(wheat.status, Cultivation.Status.ACTIVE)
        self.assertEqual(wheat.sowing_date, date(2026, 3, 20))
        self.assertEqual(wheat.planned_harvest_date, date(2026, 8, 10))
        self.assertIn("Dane demonstracyjne zostały przygotowane.", output)

    def test_running_command_twice_does_not_duplicate_data(self):
        self.run_command()
        self.run_command()

        self.assertEqual(Crop.objects.count(), 4)
        self.assertEqual(Field.objects.filter(owner=self.user).count(), 2)
        self.assertEqual(Cultivation.objects.count(), 2)
        self.assertEqual(FieldWork.objects.count(), 4)
        self.assertEqual(Spraying.objects.count(), 2)
        self.assertEqual(Harvest.objects.count(), 2)

    def test_command_fails_for_unknown_user(self):
        with self.assertRaisesMessage(
            CommandError, 'Użytkownik o nazwie "missing" nie istnieje.'
        ):
            call_command("seed_demo_data", username="missing")
