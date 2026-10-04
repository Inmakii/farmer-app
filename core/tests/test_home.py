from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Crop, Field


class HomeViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="home-route-user",
            password="StrongPass!2026",
        )

    def test_anonymous_user_sees_landing_page(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")
        self.assertContains(response, reverse("core:register"))
        self.assertContains(response, reverse("core:login"))

    def test_authenticated_user_sees_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/dashboard.html")

    def test_new_user_is_prompted_to_add_first_field(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(
            response.context["next_step"]["url"], reverse("core:field_create")
        )

    def test_next_step_is_cultivation_once_field_exists(self):
        Crop.objects.create(name="Pszenica")
        Field.objects.create(
            owner=self.user,
            name="Pole",
            area_ha="1.00",
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Wieś 1",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(
            response.context["next_step"]["url"], reverse("core:cultivation_create")
        )
        self.assertFalse(response.context["no_crops"])

    def test_dashboard_warns_when_no_crops_exist(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:home"))

        self.assertTrue(response.context["no_crops"])

    def test_root_url_does_not_return_not_found(self):
        response = self.client.get("/")

        self.assertNotEqual(response.status_code, 404)
