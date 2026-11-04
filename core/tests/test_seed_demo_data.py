import copy
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.db.models import Model
from django.test import TestCase
from django.utils.text import capfirst

from ..management.commands import seed_demo_data
from ..management.commands.seed_demo_data import (
    DEMO_CROP_NAMES,
    DEMO_ERROR_REPORTS,
    DEMO_FIELDS,
    SUMMARY_MODELS,
    count_cultivation_records,
)
from ..models import Crop, Cultivation, ErrorReport, Field, FieldWork, Harvest, Spraying

DOMAIN_MODELS = (Field, Cultivation, FieldWork, Spraying, Harvest, ErrorReport)


def expected_counts():
    """Number of records of each model described by the demo scenario."""
    counts = {model: 0 for model in SUMMARY_MODELS}
    counts[Crop] = len(DEMO_CROP_NAMES)
    counts[Field] = len(DEMO_FIELDS)
    counts[ErrorReport] = len(DEMO_ERROR_REPORTS)
    for field_spec in DEMO_FIELDS:
        for cultivation_spec in field_spec["cultivations"]:
            for model, count in count_cultivation_records(cultivation_spec).items():
                counts[model] += count
    return counts


def summary_line(model, created, reused, skipped):
    return (
        f"{capfirst(model._meta.verbose_name_plural)}: utworzono {created}, "
        f"wykorzystano ponownie {reused}, pominięto {skipped}"
    )


def user_records(model, user):
    owner_path = {
        Field: "owner",
        Cultivation: "field__owner",
        FieldWork: "cultivation__field__owner",
        Spraying: "cultivation__field__owner",
        Harvest: "cultivation__field__owner",
        ErrorReport: "user",
    }[model]
    return model.objects.filter(**{owner_path: user})


class SeedDemoDataCommandTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="demo_farmer", password="test-password"
        )
        self.other_user = user_model.objects.create_user(
            username="second_farmer", password="test-password"
        )

    def run_command(self, username=None, **options):
        stdout, stderr = StringIO(), StringIO()
        call_command(
            "seed_demo_data",
            username=username or self.user.username,
            stdout=stdout,
            stderr=stderr,
            **options,
        )
        return stdout.getvalue(), stderr.getvalue()

    def assert_user_counts(self, user, counts):
        for model in DOMAIN_MODELS:
            with self.subTest(model=model.__name__):
                self.assertEqual(user_records(model, user).count(), counts[model])

    def test_scenario_covers_every_domain_model(self):
        counts = expected_counts()
        for model in SUMMARY_MODELS:
            with self.subTest(model=model.__name__):
                self.assertGreater(counts[model], 0)

    def test_command_creates_data_for_all_models(self):
        output, errors = self.run_command()

        counts = expected_counts()
        self.assertEqual(Crop.objects.count(), counts[Crop])
        self.assert_user_counts(self.user, counts)
        self.assertEqual(errors, "")
        for model in SUMMARY_MODELS:
            self.assertIn(summary_line(model, counts[model], 0, 0), output)
        self.assertIn("Dane demonstracyjne zostały przygotowane.", output)

    def test_demo_records_are_marked_and_cover_choices(self):
        self.run_command()

        fields = user_records(Field, self.user)
        self.assertTrue(all(field.name.startswith("[DEMO] ") for field in fields))
        self.assertTrue(
            all(report.description.startswith("[DEMO] ") for report in user_records(ErrorReport, self.user))
        )
        self.assertEqual(
            set(user_records(Cultivation, self.user).values_list("status", flat=True)),
            set(Cultivation.Status.values),
        )
        self.assertEqual(
            set(user_records(FieldWork, self.user).values_list("work_type", flat=True)),
            set(FieldWork.WorkType.values),
        )
        self.assertEqual(
            set(user_records(Spraying, self.user).values_list("unit", flat=True)),
            set(Spraying.Unit.values),
        )
        self.assertEqual(
            set(user_records(Harvest, self.user).values_list("unit", flat=True)),
            set(Harvest.Unit.values),
        )
        self.assertEqual(
            set(user_records(Harvest, self.user).values_list("disposition", flat=True)),
            set(Harvest.Disposition.values),
        )
        self.assertEqual(
            set(user_records(ErrorReport, self.user).values_list("status", flat=True)),
            set(ErrorReport.Status.values),
        )

    def test_created_records_belong_to_the_user(self):
        self.run_command()

        for model in DOMAIN_MODELS:
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    model.objects.count(), user_records(model, self.user).count()
                )
        self.assertFalse(Field.objects.filter(owner=self.other_user).exists())
        self.assertFalse(ErrorReport.objects.filter(user=self.other_user).exists())

    def test_created_records_pass_full_validation(self):
        self.run_command()

        for model in SUMMARY_MODELS:
            for instance in model.objects.all():
                with self.subTest(model=model.__name__, pk=instance.pk):
                    instance.full_clean()
        for cultivation in Cultivation.objects.all():
            with self.subTest(cultivation=cultivation.pk):
                if cultivation.sowing_date:
                    self.assertEqual(cultivation.sowing_date.year, cultivation.season_year)
                for harvest in cultivation.harvests.all():
                    self.assertIsNotNone(cultivation.sowing_date)
                    self.assertGreaterEqual(harvest.harvest_date, cultivation.sowing_date)
        for harvest in Harvest.objects.exclude(disposition=Harvest.Disposition.SOLD):
            self.assertEqual(harvest.revenue, 0)

    def test_each_new_object_is_validated_before_saving(self):
        original_full_clean = Model.full_clean
        validated = []

        def tracking_full_clean(instance, *args, **kwargs):
            validated.append((type(instance), instance.pk))
            return original_full_clean(instance, *args, **kwargs)

        with mock.patch("django.db.models.Model.full_clean", tracking_full_clean):
            self.run_command()

        counts = expected_counts()
        for model in SUMMARY_MODELS:
            with self.subTest(model=model.__name__):
                calls = [pk for validated_model, pk in validated if validated_model is model]
                self.assertEqual(len(calls), counts[model])
                # full_clean() runs on unsaved objects, i.e. before the INSERT.
                self.assertTrue(all(pk is None for pk in calls))

    def test_invalid_demo_data_is_rejected_and_nothing_is_saved(self):
        invalid_fields = copy.deepcopy(DEMO_FIELDS)
        invalid_fields[-1]["cultivations"][0]["values"]["season_year"] = 1970

        with mock.patch.object(seed_demo_data, "DEMO_FIELDS", invalid_fields):
            with self.assertRaisesMessage(CommandError, "Dane demonstracyjne nie przeszły walidacji"):
                self.run_command()

        self.assertEqual(Crop.objects.count(), 0)
        self.assert_user_counts(self.user, {model: 0 for model in SUMMARY_MODELS})

    def test_running_command_twice_does_not_duplicate_data(self):
        self.run_command()
        output, errors = self.run_command()

        counts = expected_counts()
        self.assertEqual(Crop.objects.count(), counts[Crop])
        self.assert_user_counts(self.user, counts)
        self.assertEqual(errors, "")
        for model in SUMMARY_MODELS:
            self.assertIn(summary_line(model, 0, counts[model], 0), output)
        self.assertNotIn("Utworzono (", output)

    def test_second_user_gets_own_records_and_shares_crops(self):
        self.run_command()
        output, _errors = self.run_command(username=self.other_user.username)

        counts = expected_counts()
        self.assertEqual(Crop.objects.count(), counts[Crop])
        self.assert_user_counts(self.user, counts)
        self.assert_user_counts(self.other_user, counts)
        self.assertIn(summary_line(Crop, 0, counts[Crop], 0), output)
        self.assertIn(summary_line(Field, counts[Field], 0, 0), output)
        for model in DOMAIN_MODELS:
            with self.subTest(model=model.__name__):
                self.assertEqual(model.objects.count(), 2 * counts[model])

    def test_existing_crop_is_reused_without_changes(self):
        crop = Crop.objects.create(name="Pszenica", description="Opis użytkownika")

        self.run_command()

        crop.refresh_from_db()
        self.assertEqual(crop.description, "Opis użytkownika")
        self.assertEqual(Crop.objects.filter(name="Pszenica").count(), 1)
        self.assertTrue(Cultivation.objects.filter(crop=crop, field__owner=self.user).exists())

    def test_existing_field_with_different_data_is_not_overwritten(self):
        demo_spec = DEMO_FIELDS[0]
        user_field = Field.objects.create(
            owner=self.user,
            name=demo_spec["values"]["name"],
            area_ha="99.00",
            soil_type=Field.SoilType.PEAT,
            location_method=Field.LocationMethod.ADDRESS,
            address="Adres użytkownika",
        )
        real_field = Field.objects.create(
            owner=self.user,
            name="Pole Północne",
            area_ha="3.00",
            soil_type=Field.SoilType.CLAY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Prawdziwe pole",
        )

        output, errors = self.run_command()

        user_field.refresh_from_db()
        real_field.refresh_from_db()
        self.assertEqual(str(user_field.area_ha), "99.00")
        self.assertEqual(user_field.soil_type, Field.SoilType.PEAT)
        self.assertEqual(user_field.address, "Adres użytkownika")
        self.assertFalse(user_field.cultivations.exists())
        self.assertEqual(real_field.address, "Prawdziwe pole")
        self.assertIn("Pominięto (pole rolne)", errors)

        skipped = {model: 0 for model in SUMMARY_MODELS}
        skipped[Field] = 1
        for cultivation_spec in demo_spec["cultivations"]:
            for model, count in count_cultivation_records(cultivation_spec).items():
                skipped[model] += count
        counts = expected_counts()
        for model in DOMAIN_MODELS:
            with self.subTest(model=model.__name__):
                created = counts[model] - skipped[model]
                self.assertIn(summary_line(model, created, 0, skipped[model]), output)
        self.assertEqual(Field.objects.filter(owner=self.user).count(), counts[Field] + 1)

    def test_changed_demo_cultivation_is_left_unchanged_and_its_events_skipped(self):
        corn_spec = DEMO_FIELDS[1]["cultivations"][0]
        self.assertEqual(corn_spec["crop"], "Kukurydza")
        self.run_command()
        cultivation = Cultivation.objects.get(
            field__owner=self.user, crop__name="Kukurydza", season_year=2026
        )
        cultivation.status = Cultivation.Status.COMPLETED
        cultivation.save()
        cultivation.works.all().delete()

        output, errors = self.run_command()

        cultivation.refresh_from_db()
        self.assertEqual(cultivation.status, Cultivation.Status.COMPLETED)
        self.assertFalse(cultivation.works.exists())
        self.assertIn("Pominięto (uprawa)", errors)
        self.assertEqual(
            Cultivation.objects.filter(field__owner=self.user).count(),
            expected_counts()[Cultivation],
        )
        counts = expected_counts()
        skipped_works = len(corn_spec["works"])
        self.assertIn(
            summary_line(FieldWork, 0, counts[FieldWork] - skipped_works, skipped_works), output
        )
        self.assertIn(summary_line(Cultivation, 0, counts[Cultivation] - 1, 1), output)

    def test_dry_run_does_not_save_anything(self):
        output, errors = self.run_command(dry_run=True)

        self.assertEqual(Crop.objects.count(), 0)
        self.assert_user_counts(self.user, {model: 0 for model in SUMMARY_MODELS})
        self.assertEqual(errors, "")
        self.assertIn("Tryb próbny", output)
        self.assertIn("Do utworzenia (pole rolne): [DEMO] Pole Północne", output)
        self.assertIn("Podsumowanie (tryb próbny, nic nie zapisano):", output)
        counts = expected_counts()
        for model in SUMMARY_MODELS:
            self.assertIn(summary_line(model, counts[model], 0, 0), output)
        self.assertNotIn("Dane demonstracyjne zostały przygotowane.", output)

    def test_dry_run_after_seeding_reports_reused_records(self):
        self.run_command()

        output, _errors = self.run_command(dry_run=True)

        counts = expected_counts()
        self.assert_user_counts(self.user, counts)
        self.assertIn("Do ponownego wykorzystania (pole rolne): [DEMO] Pole Północne", output)
        for model in SUMMARY_MODELS:
            self.assertIn(summary_line(model, 0, counts[model], 0), output)

    def test_error_in_the_middle_rolls_back_everything(self):
        with mock.patch.object(ErrorReport, "save", side_effect=IntegrityError("simulated failure")):
            with self.assertRaises(IntegrityError):
                self.run_command()

        self.assertEqual(Crop.objects.count(), 0)
        self.assert_user_counts(self.user, {model: 0 for model in SUMMARY_MODELS})

    def test_command_fails_for_unknown_user(self):
        with self.assertRaisesMessage(
            CommandError, 'Użytkownik o nazwie "missing" nie istnieje.'
        ):
            call_command("seed_demo_data", username="missing", stdout=StringIO())

        self.assertEqual(Crop.objects.count(), 0)
        self.assertFalse(Field.objects.exists())
        self.assertFalse(get_user_model().objects.filter(username="missing").exists())
