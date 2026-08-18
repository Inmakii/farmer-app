from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Crop, Cultivation, Field, FieldWork, Harvest, Spraying
from .services.reports import calculate_totals, get_cultivation_report


class FinancialReportsTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.user = users.objects.create_user(username="reporter", password="StrongPass!2026")
        self.other = users.objects.create_user(username="other_reporter", password="StrongPass!2026")
        self.field = Field.objects.create(owner=self.user, name="Pole Raportowe", area_ha=Decimal("10"), soil_type=Field.SoilType.LOAMY, location_method=Field.LocationMethod.ADDRESS, address="Toruń")
        self.empty_field = Field.objects.create(owner=self.user, name="Puste Pole", area_ha=Decimal("2"), soil_type=Field.SoilType.SANDY, location_method=Field.LocationMethod.PARCEL, parcel_identifier="EMPTY")
        self.other_field = Field.objects.create(owner=self.other, name="Cudze Pole Raportowe", area_ha=Decimal("8"), soil_type=Field.SoilType.CLAY, location_method=Field.LocationMethod.ADDRESS, address="Bydgoszcz")
        self.crop = Crop.objects.create(name="Pszenica raportowa")
        self.other_crop = Crop.objects.create(name="Tajna uprawa")
        self.cultivation = Cultivation.objects.create(field=self.field, crop=self.crop, season_year=2026, status=Cultivation.Status.ACTIVE)
        self.old_cultivation = Cultivation.objects.create(field=self.field, crop=self.crop, season_year=2025, status=Cultivation.Status.COMPLETED)
        self.other_cultivation = Cultivation.objects.create(field=self.other_field, crop=self.other_crop, season_year=2026, status=Cultivation.Status.ACTIVE)

    def add_events(self, cultivation=None):
        cultivation = cultivation or self.cultivation
        FieldWork.objects.create(cultivation=cultivation, work_type=FieldWork.WorkType.PLOWING, work_date=date(2026, 3, 1), cost=Decimal("10.00"))
        FieldWork.objects.create(cultivation=cultivation, work_type=FieldWork.WorkType.SOWING, work_date=date(2026, 3, 2), cost=Decimal("20.00"))
        Spraying.objects.create(cultivation=cultivation, spraying_date=date(2026, 4, 1), product_name="A", quantity=Decimal("1"), unit=Spraying.Unit.L, cost=Decimal("5.00"))
        Spraying.objects.create(cultivation=cultivation, spraying_date=date(2026, 4, 2), product_name="B", quantity=Decimal("1"), unit=Spraying.Unit.L, cost=Decimal("7.00"))
        Harvest.objects.create(cultivation=cultivation, harvest_date=date(2026, 8, 1), quantity=Decimal("1"), unit=Harvest.Unit.T, revenue=Decimal("100.00"), harvest_cost=Decimal("3.00"))
        Harvest.objects.create(cultivation=cultivation, harvest_date=date(2026, 8, 2), quantity=Decimal("100"), unit=Harvest.Unit.KG, revenue=Decimal("50.00"), harvest_cost=Decimal("4.00"))

    def totals(self, cultivation=None):
        cultivation = cultivation or self.cultivation
        return calculate_totals(Cultivation.objects.filter(pk=cultivation.pk))

    def test_empty_events_return_zero_values(self):
        totals = self.totals()
        for key in ("work_costs", "spraying_costs", "harvest_costs", "total_costs", "total_revenue", "profit"):
            self.assertEqual(totals[key], Decimal("0.00"))

    def test_work_cost_sum(self):
        self.add_events()
        self.assertEqual(self.totals()["work_costs"], Decimal("30.00"))

    def test_spraying_cost_sum(self):
        self.add_events()
        self.assertEqual(self.totals()["spraying_costs"], Decimal("12.00"))

    def test_harvest_cost_sum(self):
        self.add_events()
        self.assertEqual(self.totals()["harvest_costs"], Decimal("7.00"))

    def test_revenue_sum(self):
        self.add_events()
        self.assertEqual(self.totals()["total_revenue"], Decimal("150.00"))

    def test_total_costs(self):
        self.add_events()
        self.assertEqual(self.totals()["total_costs"], Decimal("49.00"))

    def test_positive_profit(self):
        self.add_events()
        self.assertEqual(self.totals()["profit"], Decimal("101.00"))

    def test_loss(self):
        FieldWork.objects.create(cultivation=self.cultivation, work_type=FieldWork.WorkType.OTHER, work_date=date(2026, 1, 1), cost=Decimal("20"))
        Harvest.objects.create(cultivation=self.cultivation, harvest_date=date(2026, 2, 1), quantity=Decimal("1"), unit=Harvest.Unit.T, revenue=Decimal("5"), harvest_cost=Decimal("10"))
        self.assertEqual(self.totals()["profit"], Decimal("-25.00"))

    def test_multiple_relations_do_not_multiply_sums(self):
        self.add_events()
        totals = self.totals()
        self.assertEqual((totals["work_costs"], totals["spraying_costs"], totals["harvest_costs"], totals["total_revenue"]), (Decimal("30"), Decimal("12"), Decimal("7"), Decimal("150")))

    def test_record_counts(self):
        self.add_events()
        totals = self.totals()
        self.assertEqual((totals["field_count"], totals["cultivation_count"], totals["work_count"], totals["spraying_count"], totals["harvest_count"]), (1, 1, 2, 2, 2))

    def test_financial_values_are_decimal(self):
        totals = self.totals()
        for key in ("work_costs", "spraying_costs", "harvest_costs", "total_costs", "total_revenue", "profit"):
            self.assertIsInstance(totals[key], Decimal)

    def test_anonymous_user_redirected(self):
        response = self.client.get(reverse("core:report_dashboard"))
        self.assertRedirects(response, f'{reverse("core:login")}?next={reverse("core:report_dashboard")}')

    def test_dashboard_excludes_other_users_data(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:report_dashboard"))
        self.assertNotContains(response, self.other_field.name)
        self.assertNotContains(response, self.other_crop.name)

    def test_foreign_field_filter_reveals_no_data(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:report_dashboard"), {"field": self.other_field.pk})
        self.assertEqual(response.context["totals"]["cultivation_count"], 0)
        self.assertNotContains(response, self.other_field.name)

    def test_foreign_field_report_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:field_report", kwargs={"pk": self.other_field.pk}))
        self.assertEqual(response.status_code, 404)

    def test_foreign_cultivation_report_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:cultivation_report", kwargs={"pk": self.other_cultivation.pk}))
        self.assertEqual(response.status_code, 404)

    def test_own_field_filter(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:report_dashboard"), {"field": self.field.pk})
        self.assertEqual({item["cultivation"].field_id for item in response.context["cultivation_reports"]}, {self.field.pk})

    def test_season_year_filter(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:report_dashboard"), {"season_year": 2025})
        self.assertEqual([item["cultivation"].season_year for item in response.context["cultivation_reports"]], [2025])

    def test_combined_field_and_year_filter(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:report_dashboard"), {"field": self.field.pk, "season_year": 2026})
        self.assertEqual([item["cultivation"].pk for item in response.context["cultivation_reports"]], [self.cultivation.pk])

    def test_invalid_field_does_not_fail(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:report_dashboard"), {"field": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["invalid_filters"])

    def test_invalid_year_does_not_fail(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:report_dashboard"), {"season_year": "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["invalid_filters"])

    def test_field_report_only_contains_that_fields_cultivations(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:field_report", kwargs={"pk": self.field.pk}))
        self.assertEqual({item["cultivation"].field_id for item in response.context["cultivation_reports"]}, {self.field.pk})

    def test_cultivation_report_lists_works(self):
        self.add_events()
        report = get_cultivation_report(self.cultivation)
        self.assertEqual(report["works"].count(), 2)

    def test_cultivation_report_lists_sprayings(self):
        self.add_events()
        report = get_cultivation_report(self.cultivation)
        self.assertEqual(report["sprayings"].count(), 2)

    def test_cultivation_report_lists_harvests(self):
        self.add_events()
        report = get_cultivation_report(self.cultivation)
        self.assertEqual(report["harvests"].count(), 2)

    def test_empty_field_report_works(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:field_report", kwargs={"pk": self.empty_field.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["totals"]["total_costs"], Decimal("0.00"))

    def test_report_links_exist_in_details(self):
        self.client.force_login(self.user)
        field_response = self.client.get(reverse("core:field_detail", kwargs={"pk": self.field.pk}))
        cultivation_response = self.client.get(reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}))
        self.assertContains(field_response, reverse("core:field_report", kwargs={"pk": self.field.pk}))
        self.assertContains(cultivation_response, reverse("core:cultivation_report", kwargs={"pk": self.cultivation.pk}))

    def test_dashboard_uses_bounded_query_count(self):
        for year in range(2027, 2032):
            Cultivation.objects.create(field=self.field, crop=self.crop, season_year=year, status=Cultivation.Status.PLANNED)
        self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("core:report_dashboard"))
            self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 16)
