from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

SEASON_YEAR_MIN = 1980
SEASON_YEAR_MAX = 2100


class Crop(models.Model):
    name = models.CharField("nazwa", max_length=100, unique=True)
    description = models.TextField("opis", blank=True)
    created_at = models.DateTimeField("data utworzenia", auto_now_add=True)

    class Meta:
        verbose_name = "rodzaj uprawy"
        verbose_name_plural = "rodzaje upraw"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Field(models.Model):
    class SoilType(models.TextChoices):
        SANDY = "SANDY", "Gleba piaszczysta"
        CLAY = "CLAY", "Gleba gliniasta"
        LOAMY = "LOAMY", "Gleba ilasta"
        SILT = "SILT", "Gleba pyłowa"
        PEAT = "PEAT", "Gleba torfowa"
        OTHER = "OTHER", "Inna"

    class LocationMethod(models.TextChoices):
        ADDRESS = "ADDRESS", "Adres"
        GPS = "GPS", "Współrzędne GPS"
        MAP = "MAP", "Punkt na mapie"
        PARCEL = "PARCEL", "Identyfikator działki"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fields",
        verbose_name="właściciel",
    )
    name = models.CharField("nazwa", max_length=150)
    area_ha = models.DecimalField(
        "powierzchnia (ha)", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    soil_type = models.CharField("rodzaj gleby", max_length=10, choices=SoilType.choices)
    parcel_identifier = models.CharField("identyfikator działki", max_length=100, blank=True)
    location_method = models.CharField(
        "metoda lokalizacji", max_length=10, choices=LocationMethod.choices
    )
    address = models.CharField("adres", max_length=255, blank=True)
    latitude = models.DecimalField(
        "szerokość geograficzna", max_digits=9, decimal_places=6,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("-90")), MaxValueValidator(Decimal("90"))],
    )
    longitude = models.DecimalField(
        "długość geograficzna", max_digits=9, decimal_places=6,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("-180")), MaxValueValidator(Decimal("180"))],
    )
    description = models.TextField("opis", blank=True)
    created_at = models.DateTimeField("data utworzenia", auto_now_add=True)
    updated_at = models.DateTimeField("data aktualizacji", auto_now=True)

    class Meta:
        verbose_name = "pole rolne"
        verbose_name_plural = "pola rolne"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(area_ha__gt=0), name="core_field_area_ha_gt_zero"
            ),
            models.UniqueConstraint(
                fields=["owner", "name"], name="core_field_unique_owner_name"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.area_ha} ha)"


class Cultivation(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planowana"
        ACTIVE = "ACTIVE", "Aktywna"
        COMPLETED = "COMPLETED", "Zakończona"

    field = models.ForeignKey(
        Field, on_delete=models.CASCADE, related_name="cultivations", verbose_name="pole"
    )
    crop = models.ForeignKey(
        Crop, on_delete=models.PROTECT, related_name="cultivations",
        verbose_name="rodzaj uprawy",
    )
    season_year = models.PositiveSmallIntegerField(
        "rok sezonu", validators=[
            MinValueValidator(SEASON_YEAR_MIN),
            MaxValueValidator(SEASON_YEAR_MAX),
        ],
    )
    status = models.CharField("status", max_length=10, choices=Status.choices)
    sowing_date = models.DateField("data siewu", null=True, blank=True)
    planned_harvest_date = models.DateField("planowana data zbioru", null=True, blank=True)
    notes = models.TextField("notatki", blank=True)
    created_at = models.DateTimeField("data utworzenia", auto_now_add=True)

    class Meta:
        verbose_name = "uprawa"
        verbose_name_plural = "uprawy"
        ordering = ["-season_year", "field__name", "crop__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["field", "crop", "season_year"],
                name="core_cultivation_unique_field_crop_season",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        if (self.sowing_date and self.season_year
                and self.sowing_date.year != self.season_year):
            errors["sowing_date"] = "Rok daty siewu musi być zgodny z rokiem sezonu."
        if (self.sowing_date and self.planned_harvest_date
                and self.planned_harvest_date < self.sowing_date):
            errors["planned_harvest_date"] = (
                "Planowana data zbioru nie może być wcześniejsza od daty siewu."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.crop} na polu {self.field.name} ({self.season_year})"


class FieldWork(models.Model):
    class WorkType(models.TextChoices):
        PLOWING = "PLOWING", "Orka"
        SOWING = "SOWING", "Siew"
        FERTILIZING = "FERTILIZING", "Nawożenie"
        WATERING = "WATERING", "Nawadnianie"
        WEEDING = "WEEDING", "Odchwaszczanie"
        OTHER = "OTHER", "Inna"

    cultivation = models.ForeignKey(
        Cultivation, on_delete=models.CASCADE, related_name="works", verbose_name="uprawa"
    )
    work_type = models.CharField("rodzaj pracy", max_length=12, choices=WorkType.choices)
    work_date = models.DateField("data wykonania")
    cost = models.DecimalField(
        "koszt", max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    description = models.TextField("opis", blank=True)
    created_at = models.DateTimeField("data utworzenia", auto_now_add=True)

    class Meta:
        verbose_name = "wykonana praca"
        verbose_name_plural = "wykonane prace"
        ordering = ["-work_date", "-created_at"]
        constraints = [models.CheckConstraint(
            condition=Q(cost__gte=0), name="core_fieldwork_cost_gte_zero"
        )]

    def clean(self):
        super().clean()
        if (self.work_type == self.WorkType.SOWING and self.work_date
                and self.cultivation_id
                and self.work_date.year != self.cultivation.season_year):
            raise ValidationError({
                "work_date": "Rok daty siewu musi być zgodny z rokiem sezonu uprawy."
            })

    def __str__(self):
        return f"{self.get_work_type_display()} — {self.cultivation} ({self.work_date})"


class Spraying(models.Model):
    class Unit(models.TextChoices):
        L = "L", "l"
        ML = "ML", "ml"
        KG = "KG", "kg"
        G = "G", "g"

    cultivation = models.ForeignKey(
        Cultivation, on_delete=models.CASCADE, related_name="sprayings", verbose_name="uprawa"
    )
    spraying_date = models.DateField("data oprysku")
    product_name = models.CharField("nazwa środka", max_length=150)
    quantity = models.DecimalField(
        "ilość", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit = models.CharField("jednostka", max_length=2, choices=Unit.choices)
    cost = models.DecimalField(
        "koszt", max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    description = models.TextField("opis", blank=True)
    created_at = models.DateTimeField("data utworzenia", auto_now_add=True)

    class Meta:
        verbose_name = "oprysk"
        verbose_name_plural = "opryski"
        ordering = ["-spraying_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="core_spraying_quantity_gt_zero"
            ),
            models.CheckConstraint(
                condition=Q(cost__gte=0), name="core_spraying_cost_gte_zero"
            ),
        ]

    def __str__(self):
        return f"{self.product_name} — {self.cultivation} ({self.spraying_date})"


class Harvest(models.Model):
    class Unit(models.TextChoices):
        KG = "KG", "kg"
        T = "T", "t"

    class Disposition(models.TextChoices):
        SOLD = "SOLD", "Sprzedany"
        STORED = "STORED", "Pozostawiony w magazynie"
        DISCARDED = "DISCARDED", "Strata / zutylizowany"

    cultivation = models.ForeignKey(
        Cultivation, on_delete=models.CASCADE, related_name="harvests", verbose_name="uprawa"
    )
    harvest_date = models.DateField("data zbioru")
    quantity = models.DecimalField(
        "ilość", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit = models.CharField("jednostka", max_length=2, choices=Unit.choices)
    disposition = models.CharField(
        "przeznaczenie zbioru",
        max_length=10,
        choices=Disposition.choices,
        default=Disposition.SOLD,
    )
    revenue = models.DecimalField(
        "przychód", max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    harvest_cost = models.DecimalField(
        "koszt zbioru", max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.TextField("notatki", blank=True)
    created_at = models.DateTimeField("data utworzenia", auto_now_add=True)

    class Meta:
        verbose_name = "zbiór"
        verbose_name_plural = "zbiory"
        ordering = ["-harvest_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="core_harvest_quantity_gt_zero"
            ),
            models.CheckConstraint(
                condition=Q(revenue__gte=0), name="core_harvest_revenue_gte_zero"
            ),
            models.CheckConstraint(
                condition=Q(harvest_cost__gte=0), name="core_harvest_cost_gte_zero"
            ),
            models.CheckConstraint(
                condition=Q(disposition="SOLD") | Q(revenue=0),
                name="core_harvest_unsold_revenue_zero",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.disposition != self.Disposition.SOLD
            and self.revenue != Decimal("0")
        ):
            raise ValidationError({
                "revenue": (
                    "Przychód musi wynosić 0, jeśli zbiór nie został sprzedany."
                )
            })

    @property
    def profit(self):
        return self.revenue - self.harvest_cost

    def __str__(self):
        return f"Zbiór {self.cultivation} — {self.harvest_date}"


class ErrorReport(models.Model):
    class Category(models.TextChoices):
        TECHNICAL = "TECHNICAL", "Problem techniczny"
        DATA = "DATA", "Problem z danymi"
        INTERFACE = "INTERFACE", "Problem z interfejsem"
        OTHER = "OTHER", "Inny"

    class Status(models.TextChoices):
        NEW = "NEW", "Nowe"
        IN_PROGRESS = "IN_PROGRESS", "W trakcie"
        RESOLVED = "RESOLVED", "Rozwiązane"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="error_reports", verbose_name="użytkownik",
    )
    category = models.CharField("kategoria", max_length=10, choices=Category.choices)
    description = models.TextField("opis")
    status = models.CharField("status", max_length=11, choices=Status.choices)
    created_at = models.DateTimeField("data utworzenia", auto_now_add=True)
    updated_at = models.DateTimeField("data aktualizacji", auto_now=True)

    class Meta:
        verbose_name = "zgłoszenie błędu"
        verbose_name_plural = "zgłoszenia błędów"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Zgłoszenie #{self.pk or 'nowe'} — {self.get_category_display()}"
