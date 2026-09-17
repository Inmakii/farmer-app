from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class HomeViewTests(TestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("core:home"))

        self.assertRedirects(response, reverse("core:login"))

    def test_authenticated_user_is_redirected_to_field_list(self):
        user = get_user_model().objects.create_user(
            username="home-route-user",
            password="StrongPass!2026",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("core:home"))

        self.assertRedirects(response, reverse("core:field_list"))

    def test_root_url_does_not_return_not_found(self):
        response = self.client.get("/")

        self.assertNotEqual(response.status_code, 404)
