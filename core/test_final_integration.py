from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Crop, Cultivation, ErrorReport, Field, FieldWork, Harvest, Spraying


class FinalSecurityIntegrationTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user(username="integration_owner", password="StrongPass!2026")
        self.other = users.objects.create_user(username="integration_other", password="StrongPass!2026")
        self.crop = Crop.objects.create(name="Uprawa integracyjna")
        self.field = Field.objects.create(owner=self.owner, name="Pole integracyjne", area_ha=Decimal("10.00"), soil_type=Field.SoilType.LOAMY, location_method=Field.LocationMethod.ADDRESS)
        self.other_field = Field.objects.create(owner=self.other, name="Cudze pole integracyjne", area_ha=Decimal("7.00"), soil_type=Field.SoilType.SANDY, location_method=Field.LocationMethod.PARCEL)
        self.cultivation = Cultivation.objects.create(field=self.field, crop=self.crop, season_year=2026, status=Cultivation.Status.ACTIVE)
        self.other_cultivation = Cultivation.objects.create(field=self.other_field, crop=self.crop, season_year=2026, status=Cultivation.Status.ACTIVE)
        self.work = FieldWork.objects.create(cultivation=self.cultivation, work_type=FieldWork.WorkType.PLOWING, work_date=date(2026, 3, 1), cost=Decimal("100.00"))
        self.spraying = Spraying.objects.create(cultivation=self.cultivation, spraying_date=date(2026, 4, 1), product_name="Preparat", quantity=Decimal("2.00"), unit=Spraying.Unit.L, cost=Decimal("50.00"))
        self.harvest = Harvest.objects.create(cultivation=self.cultivation, harvest_date=date(2026, 8, 1), quantity=Decimal("5.00"), unit=Harvest.Unit.T, revenue=Decimal("1000.00"), harvest_cost=Decimal("150.00"))
        self.error_report = ErrorReport.objects.create(user=self.owner, category=ErrorReport.Category.TECHNICAL, description="Integracyjne zgłoszenie problemu.", status=ErrorReport.Status.NEW)

    def test_complete_farm_workflow_reaches_correct_financial_report(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:cultivation_report", kwargs={"pk": self.cultivation.pk}))
        self.assertEqual(response.status_code, 200)
        report = response.context["report"]
        self.assertEqual(report["work_costs"], Decimal("100.00"))
        self.assertEqual(report["spraying_costs"], Decimal("50.00"))
        self.assertEqual(report["harvest_costs"], Decimal("150.00"))
        self.assertEqual(report["total_revenue"], Decimal("1000.00"))
        self.assertEqual(report["profit"], Decimal("700.00"))

    def test_full_workflow_is_isolated_between_users(self):
        other_work = FieldWork.objects.create(cultivation=self.other_cultivation, work_type=FieldWork.WorkType.SOWING, work_date=date(2026, 3, 2), cost=Decimal("999.00"))
        other_spraying = Spraying.objects.create(cultivation=self.other_cultivation, spraying_date=date(2026, 4, 2), product_name="Cudzy preparat", quantity=Decimal("3.00"), unit=Spraying.Unit.L, cost=Decimal("999.00"))
        other_harvest = Harvest.objects.create(cultivation=self.other_cultivation, harvest_date=date(2026, 8, 2), quantity=Decimal("6.00"), unit=Harvest.Unit.T, revenue=Decimal("9999.00"), harvest_cost=Decimal("999.00"))
        self.client.force_login(self.owner)
        private_objects = (
            ("field_detail", self.other_field.pk),
            ("cultivation_detail", self.other_cultivation.pk),
            ("fieldwork_detail", other_work.pk),
            ("spraying_detail", other_spraying.pk),
            ("harvest_detail", other_harvest.pk),
            ("field_report", self.other_field.pk),
            ("cultivation_report", self.other_cultivation.pk),
        )
        for name, pk in private_objects:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"core:{name}", kwargs={"pk": pk})).status_code, 404)
        dashboard = self.client.get(reverse("core:report_dashboard"))
        self.assertEqual(dashboard.context["totals"]["profit"], Decimal("700.00"))

    def test_every_private_get_route_requires_login(self):
        urls = [
            reverse("core:profile"), reverse("core:profile_edit"), reverse("core:password_change"),
            reverse("core:field_list"), reverse("core:field_create"), reverse("core:field_detail", kwargs={"pk": self.field.pk}), reverse("core:field_update", kwargs={"pk": self.field.pk}), reverse("core:field_delete", kwargs={"pk": self.field.pk}),
            reverse("core:cultivation_list"), reverse("core:cultivation_create"), reverse("core:cultivation_detail", kwargs={"pk": self.cultivation.pk}), reverse("core:cultivation_update", kwargs={"pk": self.cultivation.pk}), reverse("core:cultivation_delete", kwargs={"pk": self.cultivation.pk}),
            reverse("core:fieldwork_list"), reverse("core:fieldwork_create"), reverse("core:fieldwork_detail", kwargs={"pk": self.work.pk}), reverse("core:fieldwork_update", kwargs={"pk": self.work.pk}), reverse("core:fieldwork_delete", kwargs={"pk": self.work.pk}),
            reverse("core:spraying_list"), reverse("core:spraying_create"), reverse("core:spraying_detail", kwargs={"pk": self.spraying.pk}), reverse("core:spraying_update", kwargs={"pk": self.spraying.pk}), reverse("core:spraying_delete", kwargs={"pk": self.spraying.pk}),
            reverse("core:harvest_list"), reverse("core:harvest_create"), reverse("core:harvest_detail", kwargs={"pk": self.harvest.pk}), reverse("core:harvest_update", kwargs={"pk": self.harvest.pk}), reverse("core:harvest_delete", kwargs={"pk": self.harvest.pk}),
            reverse("core:report_dashboard"), reverse("core:field_report", kwargs={"pk": self.field.pk}), reverse("core:cultivation_report", kwargs={"pk": self.cultivation.pk}),
            reverse("core:error_report_list"), reverse("core:error_report_create"), reverse("core:error_report_detail", kwargs={"pk": self.error_report.pk}),
        ]
        login_url = reverse("core:login")
        for url in urls:
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f"{login_url}?next={url}")
