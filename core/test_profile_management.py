from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .forms import ProfileEditForm


class ProfileManagementTests(TestCase):
    password = "StrongPass!2026"
    new_password = "EvenStrongerPass!2027"

    def setUp(self):
        users = get_user_model()
        self.user = users.objects.create_user(
            username="profile_owner",
            first_name="Jan",
            last_name="Kowalski",
            email="owner@example.com",
            password=self.password,
        )
        self.other = users.objects.create_user(
            username="other_profile",
            email="other@example.com",
            password=self.password,
            is_staff=True,
        )

    def profile_data(self, **overrides):
        data = {
            "first_name": "Anna",
            "last_name": "Nowak",
            "email": "anna@example.com",
        }
        data.update(overrides)
        return data

    def password_data(self, **overrides):
        data = {
            "old_password": self.password,
            "new_password1": self.new_password,
            "new_password2": self.new_password,
        }
        data.update(overrides)
        return data

    def test_anonymous_user_is_redirected(self):
        for name in ("profile_edit", "password_change"):
            url = reverse(f"core:{name}")
            self.assertRedirects(self.client.get(url), f"{reverse('core:login')}?next={url}")

    def test_valid_profile_edit(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("core:profile_edit"), self.profile_data(), follow=True)
        self.assertRedirects(response, reverse("core:profile"))
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name, self.user.email), ("Anna", "Nowak", "anna@example.com"))
        self.assertContains(response, "Dane profilu zostały zaktualizowane.")

    def test_email_must_be_case_insensitively_unique(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("core:profile_edit"), self.profile_data(email="OTHER@EXAMPLE.COM"))
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "email", "Użytkownik z tym adresem e-mail już istnieje.")

    def test_current_email_can_be_kept(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("core:profile_edit"), self.profile_data(email="OWNER@EXAMPLE.COM"))
        self.assertRedirects(response, reverse("core:profile"))

    def test_protected_fields_cannot_be_modified(self):
        self.client.force_login(self.user)
        data = self.profile_data(username=self.other.username, is_staff="on", is_superuser="on", is_active="", groups=[1], user_permissions=[1])
        self.client.post(reverse("core:profile_edit"), data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "profile_owner")
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.user.groups.count(), 0)
        self.assertEqual(self.user.user_permissions.count(), 0)
        self.assertEqual(tuple(ProfileEditForm(instance=self.user).fields), ("first_name", "last_name", "email"))

    def test_valid_password_change(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("core:password_change"), self.password_data(), follow=True)
        self.assertRedirects(response, reverse("core:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertContains(response, "Hasło zostało zmienione.")

    def test_wrong_current_password_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("core:password_change"), self.password_data(old_password="WrongPass!2026"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("old_password", response.context["form"].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_session_is_preserved_after_password_change(self):
        self.client.force_login(self.user)
        self.client.post(reverse("core:password_change"), self.password_data())
        response = self.client.get(reverse("core:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_forms_require_csrf_for_post(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for name, data in (("profile_edit", self.profile_data()), ("password_change", self.password_data())):
            response = client.post(reverse(f"core:{name}"), data)
            self.assertEqual(response.status_code, 403)

    def test_username_is_displayed_but_not_editable(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:profile_edit"))
        self.assertContains(response, self.user.username)
        self.assertNotIn("username", response.context["form"].fields)
