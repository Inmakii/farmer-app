from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext, pgettext_lazy
from django.utils.translation import gettext_lazy as _

SEASON_YEAR_MIN = 1980
SEASON_YEAR_MAX = 2100


class Crop(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    description = models.TextField(_("description"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("crop type")
        verbose_name_plural = _("crop types")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Field(models.Model):
    class SoilType(models.TextChoices):
        SANDY = "SANDY", _("Sandy soil")
        CLAY = "CLAY", _("Clay soil")
        LOAMY = "LOAMY", _("Loamy soil")
        SILT = "SILT", _("Silt soil")
        PEAT = "PEAT", _("Peat soil")
        OTHER = "OTHER", pgettext_lazy("soil type", "Other")

    class LocationMethod(models.TextChoices):
        ADDRESS = "ADDRESS", _("Address")
        GPS = "GPS", _("GPS coordinates")
        MAP = "MAP", _("Point on a map")
        PARCEL = "PARCEL", _("Parcel identifier")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fields",
        verbose_name=_("owner"),
    )
    name = models.CharField(_("name"), max_length=150)
    area_ha = models.DecimalField(
        _("area (ha)"), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    soil_type = models.CharField(_("soil type"), max_length=10, choices=SoilType.choices)
    parcel_identifier = models.CharField(_("parcel identifier"), max_length=100, blank=True)
    location_method = models.CharField(
        _("location method"), max_length=10, choices=LocationMethod.choices
    )
    address = models.CharField(_("address"), max_length=255, blank=True)
    latitude = models.DecimalField(
        _("latitude"), max_digits=9, decimal_places=6,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("-90")), MaxValueValidator(Decimal("90"))],
    )
    longitude = models.DecimalField(
        _("longitude"), max_digits=9, decimal_places=6,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("-180")), MaxValueValidator(Decimal("180"))],
    )
    description = models.TextField(_("description"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("model name", "field")
        verbose_name_plural = pgettext_lazy("model name", "fields")
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
        PLANNED = "PLANNED", _("Planned")
        ACTIVE = "ACTIVE", _("Active")
        COMPLETED = "COMPLETED", _("Completed")

    field = models.ForeignKey(
        Field, on_delete=models.CASCADE, related_name="cultivations", verbose_name=_("field")
    )
    crop = models.ForeignKey(
        Crop, on_delete=models.PROTECT, related_name="cultivations",
        verbose_name=_("crop type"),
    )
    season_year = models.PositiveSmallIntegerField(
        _("season year"), validators=[
            MinValueValidator(SEASON_YEAR_MIN),
            MaxValueValidator(SEASON_YEAR_MAX),
        ],
    )
    status = models.CharField(_("status"), max_length=10, choices=Status.choices)
    sowing_date = models.DateField(_("sowing date"), null=True, blank=True)
    planned_harvest_date = models.DateField(_("planned harvest date"), null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("cultivation")
        verbose_name_plural = _("cultivations")
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
            errors["sowing_date"] = gettext("The sowing date year must match the season year.")
        if (self.sowing_date and self.planned_harvest_date
                and self.planned_harvest_date < self.sowing_date):
            errors["planned_harvest_date"] = gettext(
                "The planned harvest date cannot be earlier than the sowing date."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return gettext("%(crop)s on field %(field)s (%(year)s)") % {
            "crop": self.crop, "field": self.field.name, "year": self.season_year,
        }


class FieldWork(models.Model):
    class WorkType(models.TextChoices):
        PLOWING = "PLOWING", _("Plowing")
        SOWING = "SOWING", _("Sowing")
        FERTILIZING = "FERTILIZING", _("Fertilizing")
        WATERING = "WATERING", _("Watering")
        WEEDING = "WEEDING", _("Weeding")
        OTHER = "OTHER", pgettext_lazy("work type", "Other")

    cultivation = models.ForeignKey(
        Cultivation, on_delete=models.CASCADE, related_name="works", verbose_name=_("cultivation")
    )
    work_type = models.CharField(_("work type"), max_length=12, choices=WorkType.choices)
    work_date = models.DateField(_("work date"))
    cost = models.DecimalField(
        _("cost"), max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    description = models.TextField(_("description"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("field work")
        verbose_name_plural = _("field works")
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
                "work_date": gettext("The sowing date year must match the cultivation season year.")
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
        Cultivation, on_delete=models.CASCADE, related_name="sprayings", verbose_name=_("cultivation")
    )
    spraying_date = models.DateField(_("spraying date"))
    product_name = models.CharField(_("product name"), max_length=150)
    quantity = models.DecimalField(
        _("quantity"), max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit = models.CharField(_("unit"), max_length=2, choices=Unit.choices)
    cost = models.DecimalField(
        _("cost"), max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    description = models.TextField(_("description"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("spraying")
        verbose_name_plural = _("sprayings")
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
        SOLD = "SOLD", _("Sold")
        STORED = "STORED", _("Kept in storage")
        DISCARDED = "DISCARDED", _("Loss / discarded")

    cultivation = models.ForeignKey(
        Cultivation, on_delete=models.CASCADE, related_name="harvests", verbose_name=_("cultivation")
    )
    harvest_date = models.DateField(_("harvest date"))
    quantity = models.DecimalField(
        _("quantity"), max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit = models.CharField(_("unit"), max_length=2, choices=Unit.choices)
    disposition = models.CharField(
        _("harvest disposition"),
        max_length=10,
        choices=Disposition.choices,
        default=Disposition.SOLD,
    )
    revenue = models.DecimalField(
        _("revenue"), max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    harvest_cost = models.DecimalField(
        _("harvest cost"), max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("harvest")
        verbose_name_plural = _("harvests")
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
                "revenue": gettext("Revenue must be 0 if the harvest was not sold.")
            })

    @property
    def profit(self):
        return self.revenue - self.harvest_cost

    def __str__(self):
        return gettext("Harvest %(cultivation)s — %(date)s") % {
            "cultivation": self.cultivation, "date": self.harvest_date,
        }


class ErrorReport(models.Model):
    class Category(models.TextChoices):
        TECHNICAL = "TECHNICAL", _("Technical problem")
        DATA = "DATA", _("Data problem")
        INTERFACE = "INTERFACE", _("Interface problem")
        OTHER = "OTHER", pgettext_lazy("report category", "Other")

    class Status(models.TextChoices):
        NEW = "NEW", _("New")
        IN_PROGRESS = "IN_PROGRESS", _("In progress")
        RESOLVED = "RESOLVED", _("Resolved")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="error_reports", verbose_name=_("user"),
    )
    category = models.CharField(_("category"), max_length=10, choices=Category.choices)
    description = models.TextField(_("description"))
    status = models.CharField(_("status"), max_length=11, choices=Status.choices)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("error report")
        verbose_name_plural = _("error reports")
        ordering = ["-created_at"]

    def __str__(self):
        return gettext("Report #%(number)s — %(category)s") % {
            "number": self.pk or gettext("new"),
            "category": self.get_category_display(),
        }
