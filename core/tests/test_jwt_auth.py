import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse


class JwtAuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.password = "StrongPass!2026"
        self.user = get_user_model().objects.create_user(
            username="api_farmer",
            email="api_farmer@example.com",
            password=self.password,
        )

    def obtain_tokens(self):
        return self.client.post(
            reverse("token_obtain_pair"),
            data=json.dumps(
                {"username": self.user.username, "password": self.password}
            ),
            content_type="application/json",
        )

    def test_valid_credentials_return_access_and_refresh_tokens(self):
        response = self.obtain_tokens()
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())

    def test_invalid_credentials_are_rejected(self):
        response = self.client.post(
            reverse("token_obtain_pair"),
            data=json.dumps(
                {"username": self.user.username, "password": "wrong-password"}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_refresh_and_verify_endpoints_accept_valid_tokens(self):
        tokens = self.obtain_tokens().json()
        refresh_response = self.client.post(
            reverse("token_refresh"),
            data=json.dumps({"refresh": tokens["refresh"]}),
            content_type="application/json",
        )
        verify_response = self.client.post(
            reverse("token_verify"),
            data=json.dumps({"token": tokens["access"]}),
            content_type="application/json",
        )
        self.assertEqual(refresh_response.status_code, 200)
        self.assertIn("access", refresh_response.json())
        self.assertEqual(verify_response.status_code, 200)

    def test_current_user_endpoint_requires_and_accepts_bearer_token(self):
        anonymous_response = self.client.get(reverse("api_current_user"))
        access_token = self.obtain_tokens().json()["access"]
        authenticated_response = self.client.get(
            reverse("api_current_user"),
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(anonymous_response.status_code, 401)
        self.assertEqual(authenticated_response.status_code, 200)
        self.assertEqual(
            authenticated_response.json(),
            {
                "id": self.user.pk,
                "username": self.user.username,
                "email": self.user.email,
            },
        )

    def test_token_endpoint_is_throttled_after_too_many_requests(self):
        statuses = [
            self.client.post(
                reverse("token_obtain_pair"),
                data=json.dumps(
                    {"username": self.user.username, "password": "wrong-password"}
                ),
                content_type="application/json",
            ).status_code
            for _ in range(11)
        ]
        self.assertEqual(statuses[:10], [401] * 10)
        self.assertEqual(statuses[10], 429)
