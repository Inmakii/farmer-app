from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthenticationViewsTests(TestCase):
    password = "StrongPass!2026"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="existing_user",
            first_name="Jan",
            last_name="Kowalski",
            email="existing@example.com",
            password=self.password,
        )

    def registration_data(self, **overrides):
        data = {
            "username": "new_farmer",
            "first_name": "Anna",
            "last_name": "Nowak",
            "email": "anna@example.com",
            "password1": self.password,
            "password2": self.password,
        }
        data.update(overrides)
        return data

    def test_registration_page_opens(self):
        response = self.client.get(reverse("core:register"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/register.html")
        self.assertContains(response, "Utwórz konto")

    def test_valid_registration_creates_user(self):
        response = self.client.post(
            reverse("core:register"), self.registration_data(), follow=True
        )

        self.assertRedirects(response, reverse("core:login"))
        user = get_user_model().objects.get(username="new_farmer")
        self.assertEqual(user.first_name, "Anna")
        self.assertEqual(user.last_name, "Nowak")
        self.assertEqual(user.email, "anna@example.com")
        self.assertTrue(user.check_password(self.password))
        self.assertContains(response, "Konto zostało utworzone")

    def test_duplicate_username_is_rejected(self):
        response = self.client.post(
            reverse("core:register"),
            self.registration_data(
                username=self.user.username, email="different@example.com"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "username",
            "Użytkownik o tej nazwie już istnieje.",
        )
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        response = self.client.post(
            reverse("core:register"),
            self.registration_data(email="EXISTING@EXAMPLE.COM"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "email",
            "Użytkownik z tym adresem e-mail już istnieje.",
        )
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_mismatched_passwords_are_rejected(self):
        response = self.client.post(
            reverse("core:register"),
            self.registration_data(password2="DifferentPass!2026"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "password2",
            "Podane hasła nie są takie same.",
        )
        self.assertFalse(
            get_user_model().objects.filter(username="new_farmer").exists()
        )

    def test_valid_login_redirects_to_profile(self):
        response = self.client.post(
            reverse("core:login"),
            {"username": self.user.username, "password": self.password},
        )

        self.assertRedirects(response, reverse("core:profile"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_invalid_login_does_not_authenticate(self):
        response = self.client.post(
            reverse("core:login"),
            {"username": self.user.username, "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_anonymous_user_is_redirected_from_profile(self):
        response = self.client.get(reverse("core:profile"))

        expected_url = f'{reverse("core:login")}?next={reverse("core:profile")}'
        self.assertRedirects(response, expected_url)

    def test_authenticated_user_can_open_own_profile(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/profile.html")
        self.assertEqual(response.context["user"], self.user)
        self.assertContains(response, self.user.username)
        self.assertContains(response, self.user.email)

    def test_logout_via_post(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("core:logout"))

        self.assertRedirects(response, reverse("core:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_via_get_is_not_allowed(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:logout"))

        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_authenticated_user_is_redirected_from_login_and_register(self):
        self.client.force_login(self.user)

        login_response = self.client.get(reverse("core:login"))
        register_response = self.client.get(reverse("core:register"))

        self.assertRedirects(login_response, reverse("core:profile"))
        self.assertRedirects(register_response, reverse("core:profile"))
