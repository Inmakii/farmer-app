from django.core.management.base import BaseCommand
from django.db import transaction

from core.crop_catalog import catalog
from core.models import Crop


class Command(BaseCommand):
    help = (
        "Add the common crop types (core/crop_catalog.py) to the crop catalog. "
        "Crops that already exist (any letter case) are left unchanged."
    )

    def handle(self, *args, **options):
        existing = {name.casefold() for name in Crop.objects.values_list("name", flat=True)}
        missing = [
            Crop(name=name, description=group)
            for name, group in catalog()
            if name.casefold() not in existing
        ]
        with transaction.atomic():
            Crop.objects.bulk_create(missing, ignore_conflicts=True)
        self.stdout.write(f"Crop catalog: added {len(missing)}, already present {len(catalog()) - len(missing)}.")
