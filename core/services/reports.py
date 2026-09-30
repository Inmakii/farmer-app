from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce

from core.models import Cultivation, Field, FieldWork, Harvest, Spraying


ZERO = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=20, decimal_places=2)


def _sum(expression, *, filter_condition=None):
    return Coalesce(
        Sum(expression, filter=filter_condition), ZERO, output_field=MONEY_FIELD
    )


def _quantity_in_kg():
    return Case(
        When(
            unit=Harvest.Unit.T,
            then=F("quantity") * Value(Decimal("1000")),
        ),
        default=F("quantity"),
        output_field=MONEY_FIELD,
    )


def _harvest_aggregates():
    quantity_in_kg = _quantity_in_kg()
    return {
        "harvest_costs": _sum("harvest_cost"),
        "total_revenue": _sum("revenue"),
        "harvest_count": Count("id"),
        "total_quantity_kg": _sum(quantity_in_kg),
        "sold_quantity_kg": _sum(
            quantity_in_kg,
            filter_condition=Q(disposition=Harvest.Disposition.SOLD),
        ),
        "stored_quantity_kg": _sum(
            quantity_in_kg,
            filter_condition=Q(disposition=Harvest.Disposition.STORED),
        ),
        "discarded_quantity_kg": _sum(
            quantity_in_kg,
            filter_condition=Q(disposition=Harvest.Disposition.DISCARDED),
        ),
    }


def calculate_totals(cultivations_queryset):
    """Zwraca bezpiecznie zagregowane kwoty i liczniki dla querysetu upraw."""
    works = FieldWork.objects.filter(cultivation__in=cultivations_queryset).aggregate(
        work_costs=_sum("cost"), work_count=Count("id")
    )
    sprayings = Spraying.objects.filter(
        cultivation__in=cultivations_queryset
    ).aggregate(spraying_costs=_sum("cost"), spraying_count=Count("id"))
    harvests = Harvest.objects.filter(
        cultivation__in=cultivations_queryset
    ).aggregate(**_harvest_aggregates())
    cultivation_counts = cultivations_queryset.aggregate(
        cultivation_count=Count("id"), field_count=Count("field_id", distinct=True)
    )
    total_costs = (
        works["work_costs"]
        + sprayings["spraying_costs"]
        + harvests["harvest_costs"]
    )
    return {
        "work_costs": works["work_costs"],
        "spraying_costs": sprayings["spraying_costs"],
        "harvest_costs": harvests["harvest_costs"],
        "total_costs": total_costs,
        "total_revenue": harvests["total_revenue"],
        "total_quantity_kg": harvests["total_quantity_kg"],
        "sold_quantity_kg": harvests["sold_quantity_kg"],
        "stored_quantity_kg": harvests["stored_quantity_kg"],
        "discarded_quantity_kg": harvests["discarded_quantity_kg"],
        "profit": harvests["total_revenue"] - total_costs,
        "field_count": cultivation_counts["field_count"],
        "cultivation_count": cultivation_counts["cultivation_count"],
        "work_count": works["work_count"],
        "spraying_count": sprayings["spraying_count"],
        "harvest_count": harvests["harvest_count"],
    }


def get_cultivation_reports(cultivations_queryset):
    """Buduje raporty wielu upraw stałą liczbą zapytań, bez problemu N+1."""
    cultivations = list(
        cultivations_queryset.select_related("field", "crop").order_by(
            "-season_year", "field__name", "crop__name"
        )
    )
    ids = [cultivation.pk for cultivation in cultivations]
    works = {
        row["cultivation_id"]: row
        for row in FieldWork.objects.filter(cultivation_id__in=ids)
        .values("cultivation_id")
        .annotate(work_costs=_sum("cost"), work_count=Count("id"))
    }
    sprayings = {
        row["cultivation_id"]: row
        for row in Spraying.objects.filter(cultivation_id__in=ids)
        .values("cultivation_id")
        .annotate(spraying_costs=_sum("cost"), spraying_count=Count("id"))
    }
    harvests = {
        row["cultivation_id"]: row
        for row in Harvest.objects.filter(cultivation_id__in=ids)
        .values("cultivation_id")
        .annotate(**_harvest_aggregates())
    }
    reports = []
    for cultivation in cultivations:
        work = works.get(cultivation.pk, {})
        spraying = sprayings.get(cultivation.pk, {})
        harvest = harvests.get(cultivation.pk, {})
        work_costs = work.get("work_costs", ZERO)
        spraying_costs = spraying.get("spraying_costs", ZERO)
        harvest_costs = harvest.get("harvest_costs", ZERO)
        revenue = harvest.get("total_revenue", ZERO)
        total_costs = work_costs + spraying_costs + harvest_costs
        reports.append(
            {
                "cultivation": cultivation,
                "work_costs": work_costs,
                "spraying_costs": spraying_costs,
                "harvest_costs": harvest_costs,
                "total_costs": total_costs,
                "total_revenue": revenue,
                "total_quantity_kg": harvest.get("total_quantity_kg", ZERO),
                "sold_quantity_kg": harvest.get("sold_quantity_kg", ZERO),
                "stored_quantity_kg": harvest.get("stored_quantity_kg", ZERO),
                "discarded_quantity_kg": harvest.get(
                    "discarded_quantity_kg", ZERO
                ),
                "profit": revenue - total_costs,
                "work_count": work.get("work_count", 0),
                "spraying_count": spraying.get("spraying_count", 0),
                "harvest_count": harvest.get("harvest_count", 0),
            }
        )
    return reports


def get_cultivation_report(cultivation):
    """Zwraca podsumowanie i zdarzenia jednej, wcześniej autoryzowanej uprawy."""
    queryset = Cultivation.objects.filter(pk=cultivation.pk)
    report = get_cultivation_reports(queryset)[0]
    report.update(
        {
            "works": cultivation.works.order_by("-work_date", "-id"),
            "sprayings": cultivation.sprayings.order_by("-spraying_date", "-id"),
            "harvests": cultivation.harvests.order_by("-harvest_date", "-id"),
        }
    )
    return report


def get_field_report(field, season_year=None):
    """Zwraca raport pola, opcjonalnie ograniczony do jednego sezonu."""
    queryset = Cultivation.objects.filter(field=field)
    if season_year is not None:
        queryset = queryset.filter(season_year=season_year)
    totals = calculate_totals(queryset)
    totals["field_count"] = 1
    return {
        "field": field,
        "totals": totals,
        "cultivation_reports": get_cultivation_reports(queryset),
    }


def get_user_report(user, field=None, season_year=None):
    """Zwraca raport wyłącznie z pól wskazanego użytkownika."""
    queryset = Cultivation.objects.filter(field__owner=user)
    fields = Field.objects.filter(owner=user)
    if field is not None:
        queryset = queryset.filter(field=field)
        fields = fields.filter(pk=field.pk)
    if season_year is not None:
        queryset = queryset.filter(season_year=season_year)
    totals = calculate_totals(queryset)
    totals["field_count"] = fields.count()
    return {
        "totals": totals,
        "cultivation_reports": get_cultivation_reports(queryset),
    }
