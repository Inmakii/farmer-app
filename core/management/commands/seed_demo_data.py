from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Crop, Cultivation, Field, FieldWork, Harvest, Spraying


class Command(BaseCommand):
    help = "Tworzy lub aktualizuje dane demonstracyjne dla istniejącego użytkownika."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            required=True,
            help="Nazwa istniejącego użytkownika, do którego zostaną przypisane dane.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"]
        user_model = get_user_model()

        try:
            user = user_model._default_manager.get(username=username)
        except user_model.DoesNotExist as error:
            raise CommandError(
                f'Użytkownik o nazwie "{username}" nie istnieje.'
            ) from error

        crops = {}
        for crop_name in ("Pszenica", "Kukurydza", "Rzepak", "Ziemniaki"):
            crop, _ = Crop.objects.get_or_create(name=crop_name)
            crops[crop_name] = crop

        north_field, _ = Field.objects.update_or_create(
            owner=user,
            name="Pole Północne",
            defaults={
                "area_ha": Decimal("12.50"),
                "soil_type": Field.SoilType.LOAMY,
                "location_method": Field.LocationMethod.GPS,
                "latitude": Decimal("53.123456"),
                "longitude": Decimal("18.123456"),
                "parcel_identifier": "040601_1.0123.45/2",
                "address": "",
                "description": "",
            },
        )
        south_field, _ = Field.objects.update_or_create(
            owner=user,
            name="Pole Południowe",
            defaults={
                "area_ha": Decimal("8.75"),
                "soil_type": Field.SoilType.SANDY,
                "location_method": Field.LocationMethod.ADDRESS,
                "address": "Bydgoszcz, ul. Polna",
                "parcel_identifier": "040601_1.0123.46/1",
                "latitude": None,
                "longitude": None,
                "description": "",
            },
        )

        wheat, _ = Cultivation.objects.update_or_create(
            field=north_field,
            crop=crops["Pszenica"],
            season_year=2026,
            defaults={
                "status": Cultivation.Status.ACTIVE,
                "sowing_date": date(2026, 3, 20),
                "planned_harvest_date": date(2026, 8, 10),
                "notes": "Dane demonstracyjne.",
            },
        )
        corn, _ = Cultivation.objects.update_or_create(
            field=south_field,
            crop=crops["Kukurydza"],
            season_year=2026,
            defaults={
                "status": Cultivation.Status.ACTIVE,
                "sowing_date": date(2026, 4, 25),
                "planned_harvest_date": date(2026, 9, 30),
                "notes": "Dane demonstracyjne.",
            },
        )

        work_data = (
            (wheat, FieldWork.WorkType.PLOWING, date(2026, 3, 10), Decimal("1250.00"), "Orka przedsiewna."),
            (wheat, FieldWork.WorkType.SOWING, date(2026, 3, 20), Decimal("980.00"), "Siew pszenicy."),
            (corn, FieldWork.WorkType.PLOWING, date(2026, 4, 12), Decimal("875.00"), "Orka przedsiewna."),
            (corn, FieldWork.WorkType.SOWING, date(2026, 4, 25), Decimal("720.00"), "Siew kukurydzy."),
        )
        for cultivation, work_type, work_date, cost, description in work_data:
            FieldWork.objects.update_or_create(
                cultivation=cultivation,
                work_type=work_type,
                work_date=work_date,
                defaults={"cost": cost, "description": description},
            )

        spraying_data = (
            (wheat, date(2026, 5, 8), "Herbicyd Demo", Decimal("12.50"), Spraying.Unit.L, Decimal("640.00")),
            (corn, date(2026, 5, 20), "Fungicyd Demo", Decimal("875.00"), Spraying.Unit.ML, Decimal("510.00")),
        )
        for cultivation, spraying_date, product_name, quantity, unit, cost in spraying_data:
            Spraying.objects.update_or_create(
                cultivation=cultivation,
                spraying_date=spraying_date,
                product_name=product_name,
                defaults={
                    "quantity": quantity,
                    "unit": unit,
                    "cost": cost,
                    "description": "Oprysk demonstracyjny.",
                },
            )

        harvest_data = (
            (wheat, date(2026, 8, 8), Decimal("82.50"), Harvest.Unit.T, Decimal("74250.00"), Decimal("4300.00")),
            (corn, date(2026, 9, 28), Decimal("96.00"), Harvest.Unit.T, Decimal("76800.00"), Decimal("5100.00")),
        )
        for cultivation, harvest_date, quantity, unit, revenue, harvest_cost in harvest_data:
            Harvest.objects.update_or_create(
                cultivation=cultivation,
                harvest_date=harvest_date,
                defaults={
                    "quantity": quantity,
                    "unit": unit,
                    "revenue": revenue,
                    "harvest_cost": harvest_cost,
                    "notes": "Zbiór demonstracyjny.",
                },
            )

        self.stdout.write(f"Pola utworzone lub zaktualizowane: 2")
        self.stdout.write(f"Uprawy utworzone lub zaktualizowane: 2")
        self.stdout.write(f"Prace utworzone lub zaktualizowane: {len(work_data)}")
        self.stdout.write(f"Opryski utworzone lub zaktualizowane: {len(spraying_data)}")
        self.stdout.write(f"Zbiory utworzone lub zaktualizowane: {len(harvest_data)}")
        self.stdout.write(self.style.SUCCESS("Dane demonstracyjne zostały przygotowane."))
