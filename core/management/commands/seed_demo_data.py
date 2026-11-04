"""Load a consistent demo scenario for an existing user.

The command only creates missing demo records and reuses records that already
match the scenario. It never updates existing rows: when a record with the same
identifying values exists but holds different data, the record is left unchanged
and the command skips it together with the demo records that depend on it.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import capfirst
from django.utils.translation import gettext

from core.models import (
    Crop,
    Cultivation,
    ErrorReport,
    Field,
    FieldWork,
    Harvest,
    Spraying,
)

DEMO_MARKER = "[DEMO]"
DEMO_NOTE = f"{DEMO_MARKER} Dane demonstracyjne."

CREATED = "created"
REUSED = "reused"
SKIPPED = "skipped"

# Shared crop catalog. Existing crops with these names are reused, never changed.
DEMO_CROP_NAMES = ("Pszenica", "Kukurydza", "Rzepak", "Ziemniaki")

# Fields of the scenario with their cultivations and cultivation events.
DEMO_FIELDS = (
    {
        "values": {
            "name": f"{DEMO_MARKER} Pole Północne",
            "area_ha": Decimal("12.50"),
            "soil_type": Field.SoilType.LOAMY,
            "location_method": Field.LocationMethod.GPS,
            "address": "",
            "latitude": Decimal("53.123456"),
            "longitude": Decimal("18.123456"),
            "parcel_identifier": "040601_1.0123.45/2",
            "description": DEMO_NOTE,
        },
        "cultivations": (
            {
                "crop": "Ziemniaki",
                "values": {
                    "season_year": 2025,
                    "status": Cultivation.Status.COMPLETED,
                    "sowing_date": date(2025, 4, 15),
                    "planned_harvest_date": date(2025, 9, 10),
                    "notes": DEMO_NOTE,
                },
                "works": (
                    (FieldWork.WorkType.PLOWING, date(2025, 4, 2), Decimal("1180.00"), "Orka przedsiewna."),
                    (FieldWork.WorkType.SOWING, date(2025, 4, 15), Decimal("2350.00"), "Sadzenie ziemniaków."),
                    (FieldWork.WorkType.FERTILIZING, date(2025, 5, 20), Decimal("1640.00"), "Nawożenie azotowe."),
                ),
                "sprayings": (
                    (date(2025, 6, 25), f"Fungicyd {DEMO_MARKER} proszek", Decimal("2.50"), Spraying.Unit.KG, Decimal("720.00")),
                ),
                "harvests": (
                    (date(2025, 9, 8), Decimal("360.00"), Harvest.Unit.T, Harvest.Disposition.SOLD, Decimal("216000.00"), Decimal("9800.00")),
                    (date(2025, 9, 12), Decimal("15000.00"), Harvest.Unit.KG, Harvest.Disposition.STORED, Decimal("0.00"), Decimal("600.00")),
                ),
            },
            {
                "crop": "Pszenica",
                "values": {
                    "season_year": 2026,
                    "status": Cultivation.Status.COMPLETED,
                    "sowing_date": date(2026, 3, 20),
                    "planned_harvest_date": date(2026, 8, 10),
                    "notes": DEMO_NOTE,
                },
                "works": (
                    (FieldWork.WorkType.PLOWING, date(2026, 3, 10), Decimal("1250.00"), "Orka przedsiewna."),
                    (FieldWork.WorkType.SOWING, date(2026, 3, 20), Decimal("980.00"), "Siew pszenicy."),
                    (FieldWork.WorkType.OTHER, date(2026, 8, 20), Decimal("430.00"), "Bronowanie ścierniska."),
                ),
                "sprayings": (
                    (date(2026, 5, 8), f"Herbicyd {DEMO_MARKER}", Decimal("12.50"), Spraying.Unit.L, Decimal("640.00")),
                ),
                "harvests": (
                    (date(2026, 8, 8), Decimal("82.50"), Harvest.Unit.T, Harvest.Disposition.SOLD, Decimal("74250.00"), Decimal("4300.00")),
                    (date(2026, 8, 9), Decimal("1.20"), Harvest.Unit.T, Harvest.Disposition.DISCARDED, Decimal("0.00"), Decimal("90.00")),
                ),
            },
        ),
    },
    {
        "values": {
            "name": f"{DEMO_MARKER} Pole Południowe",
            "area_ha": Decimal("8.75"),
            "soil_type": Field.SoilType.SANDY,
            "location_method": Field.LocationMethod.ADDRESS,
            "address": "Bydgoszcz, ul. Polna",
            "latitude": None,
            "longitude": None,
            "parcel_identifier": "040601_1.0123.46/1",
            "description": DEMO_NOTE,
        },
        "cultivations": (
            {
                "crop": "Kukurydza",
                "values": {
                    "season_year": 2026,
                    "status": Cultivation.Status.ACTIVE,
                    "sowing_date": date(2026, 4, 25),
                    "planned_harvest_date": date(2026, 11, 20),
                    "notes": DEMO_NOTE,
                },
                "works": (
                    (FieldWork.WorkType.PLOWING, date(2026, 4, 12), Decimal("875.00"), "Orka przedsiewna."),
                    (FieldWork.WorkType.SOWING, date(2026, 4, 25), Decimal("720.00"), "Siew kukurydzy."),
                    (FieldWork.WorkType.WEEDING, date(2026, 6, 5), Decimal("380.00"), "Pielenie międzyrzędzi."),
                    (FieldWork.WorkType.WATERING, date(2026, 7, 15), Decimal("450.00"), "Nawadnianie w czasie suszy."),
                ),
                "sprayings": (
                    (date(2026, 6, 20), f"Fungicyd {DEMO_MARKER}", Decimal("875.00"), Spraying.Unit.ML, Decimal("510.00")),
                    (date(2026, 7, 2), f"Insektycyd {DEMO_MARKER}", Decimal("150.00"), Spraying.Unit.G, Decimal("260.00")),
                ),
                "harvests": (),
            },
        ),
    },
    {
        "values": {
            "name": f"{DEMO_MARKER} Pole przy lesie",
            "area_ha": Decimal("5.20"),
            "soil_type": Field.SoilType.CLAY,
            "location_method": Field.LocationMethod.PARCEL,
            "address": "",
            "latitude": None,
            "longitude": None,
            "parcel_identifier": "040601_1.0123.47/3",
            "description": DEMO_NOTE,
        },
        "cultivations": (
            {
                "crop": "Rzepak",
                "values": {
                    "season_year": 2027,
                    "status": Cultivation.Status.PLANNED,
                    "sowing_date": None,
                    "planned_harvest_date": date(2027, 7, 20),
                    "notes": DEMO_NOTE,
                },
                "works": (),
                "sprayings": (),
                "harvests": (),
            },
        ),
    },
)

DEMO_ERROR_REPORTS = (
    (
        ErrorReport.Category.DATA,
        ErrorReport.Status.NEW,
        f"{DEMO_MARKER} Przykładowe zgłoszenie problemu z danymi. Służy wyłącznie do prezentacji aplikacji.",
    ),
    (
        ErrorReport.Category.TECHNICAL,
        ErrorReport.Status.IN_PROGRESS,
        f"{DEMO_MARKER} Przykładowe zgłoszenie problemu technicznego w trakcie obsługi.",
    ),
    (
        ErrorReport.Category.INTERFACE,
        ErrorReport.Status.RESOLVED,
        f"{DEMO_MARKER} Przykładowe zgłoszenie dotyczące interfejsu, oznaczone jako rozwiązane.",
    ),
)

# Values that identify an existing demo record. A record found by these values
# is reused only when all of its other demo values match as well.
LOOKUP_FIELDS = {
    Field: ("owner", "name"),
    Cultivation: ("field", "crop", "season_year"),
    FieldWork: ("cultivation", "work_type", "work_date"),
    Spraying: ("cultivation", "spraying_date", "product_name"),
    Harvest: ("cultivation", "harvest_date", "disposition"),
    ErrorReport: ("user", "category", "description"),
}

SUMMARY_MODELS = (Crop, Field, Cultivation, FieldWork, Spraying, Harvest, ErrorReport)


def count_cultivation_records(cultivation_spec):
    """Return how many records of each model a cultivation spec describes."""
    return {
        Cultivation: 1,
        FieldWork: len(cultivation_spec["works"]),
        Spraying: len(cultivation_spec["sprayings"]),
        Harvest: len(cultivation_spec["harvests"]),
    }


class Command(BaseCommand):
    help = "Creates missing demo data for an existing user without changing existing records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            required=True,
            help="Name of the existing user the data will be assigned to.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the demo data and show what would be created, without saving anything.",
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.counts = {model: {CREATED: 0, REUSED: 0, SKIPPED: 0} for model in SUMMARY_MODELS}
        user = self._get_user(options["username"])

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING(gettext("Dry run: the data is checked, but no changes will be saved."))
            )

        # Everything runs in one transaction: an error rolls back the whole set,
        # and a dry run always rolls back after the full validation.
        with transaction.atomic():
            self._seed(user)
            if self.dry_run:
                transaction.set_rollback(True)

        self._write_summary()

    def _get_user(self, username):
        user_model = get_user_model()
        try:
            return user_model._default_manager.get(username=username)
        except user_model.DoesNotExist as error:
            raise CommandError(
                gettext('User "%(username)s" does not exist.') % {"username": username}
            ) from error

    def _seed(self, user):
        crops = {name: self._ensure_crop(name) for name in DEMO_CROP_NAMES}

        for field_spec in DEMO_FIELDS:
            field = self._ensure(Field, {"owner": user, **field_spec["values"]})
            if field is None:
                for cultivation_spec in field_spec["cultivations"]:
                    self._skip_dependents(count_cultivation_records(cultivation_spec))
                continue
            for cultivation_spec in field_spec["cultivations"]:
                self._seed_cultivation(field, crops[cultivation_spec["crop"]], cultivation_spec)

        for category, status, description in DEMO_ERROR_REPORTS:
            self._ensure(
                ErrorReport,
                {"user": user, "category": category, "status": status, "description": description},
            )

    def _seed_cultivation(self, field, crop, spec):
        cultivation = self._ensure(Cultivation, {"field": field, "crop": crop, **spec["values"]})
        if cultivation is None:
            dependents = count_cultivation_records(spec)
            dependents.pop(Cultivation)
            self._skip_dependents(dependents)
            return

        for work_type, work_date, cost, description in spec["works"]:
            self._ensure(
                FieldWork,
                {
                    "cultivation": cultivation,
                    "work_type": work_type,
                    "work_date": work_date,
                    "cost": cost,
                    "description": description,
                },
            )
        for spraying_date, product_name, quantity, unit, cost in spec["sprayings"]:
            self._ensure(
                Spraying,
                {
                    "cultivation": cultivation,
                    "spraying_date": spraying_date,
                    "product_name": product_name,
                    "quantity": quantity,
                    "unit": unit,
                    "cost": cost,
                    "description": DEMO_NOTE,
                },
            )
        for harvest_date, quantity, unit, disposition, revenue, harvest_cost in spec["harvests"]:
            self._ensure(
                Harvest,
                {
                    "cultivation": cultivation,
                    "harvest_date": harvest_date,
                    "quantity": quantity,
                    "unit": unit,
                    "disposition": disposition,
                    "revenue": revenue,
                    "harvest_cost": harvest_cost,
                    "notes": DEMO_NOTE,
                },
            )

    def _ensure_crop(self, name):
        """Reuse a crop from the shared catalog or add it when it is missing."""
        crop = Crop.objects.filter(name=name).first()
        if crop is not None:
            self._report(Crop, REUSED, crop)
            return crop
        return self._create(Crop, {"name": name})

    def _ensure(self, model, values):
        """Return a matching demo record, creating it if there is none.

        Returns None when a record with the same identifying values exists but
        holds different data; that record is not modified.
        """
        lookup = {name: values[name] for name in LOOKUP_FIELDS[model]}
        candidates = list(model.objects.filter(**lookup))
        for candidate in candidates:
            if all(getattr(candidate, name) == value for name, value in values.items()):
                self._report(model, REUSED, candidate)
                return candidate
        if candidates:
            self._report(model, SKIPPED, candidates[0])
            return None
        return self._create(model, values)

    def _create(self, model, values):
        instance = model(**values)
        try:
            instance.full_clean()
        except ValidationError as error:
            raise CommandError(
                gettext("Demo data failed validation (%(model)s “%(object)s”): %(errors)s")
                % {
                    "model": model._meta.verbose_name,
                    "object": instance,
                    "errors": "; ".join(error.messages),
                }
            ) from error
        instance.save()
        self._report(model, CREATED, instance)
        return instance

    def _skip_dependents(self, counts):
        for model, count in counts.items():
            self.counts[model][SKIPPED] += count

    def _report(self, model, outcome, instance):
        self.counts[model][outcome] += 1
        params = {"model": model._meta.verbose_name, "object": instance}
        if outcome == SKIPPED:
            self.stderr.write(
                self.style.WARNING(
                    gettext(
                        "Skipped %(model)s “%(object)s”: a record with the same identifying "
                        "values already exists with different data and was left unchanged. "
                        "Dependent demo records were skipped as well."
                    )
                    % params
                )
            )
        elif outcome == CREATED:
            message = (
                gettext("Would create %(model)s: %(object)s")
                if self.dry_run
                else gettext("Created %(model)s: %(object)s")
            )
            self.stdout.write(message % params)
        else:
            message = (
                gettext("Would reuse %(model)s: %(object)s")
                if self.dry_run
                else gettext("Reused %(model)s: %(object)s")
            )
            self.stdout.write(message % params)

    def _write_summary(self):
        self.stdout.write(
            gettext("Summary (dry run, nothing was saved):") if self.dry_run else gettext("Summary:")
        )
        for model in SUMMARY_MODELS:
            counts = self.counts[model]
            self.stdout.write(
                gettext("%(model)s: created %(created)s, reused %(reused)s, skipped %(skipped)s")
                % {
                    "model": capfirst(model._meta.verbose_name_plural),
                    "created": counts[CREATED],
                    "reused": counts[REUSED],
                    "skipped": counts[SKIPPED],
                }
            )
        if self.dry_run:
            self.stdout.write(
                self.style.SUCCESS(gettext("Dry run finished. No changes were saved to the database."))
            )
        else:
            self.stdout.write(self.style.SUCCESS(gettext("Demo data is ready.")))
