"""The "About the app" flyer page (one A4 sheet, open to everyone)."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AboutPageTests(TestCase):
    def test_open_without_login_in_each_language(self):
        for language, text in (("pl", "Cyfrowy notatnik gospodarstwa"),
                               ("uk", "Цифровий записник господарства"),
                               ("en", "A digital farm notebook")):
            with self.subTest(language=language):
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
                response = self.client.get(reverse("core:about"))
                self.assertContains(response, text)

    def test_shows_site_address(self):
        response = self.client.get(reverse("core:about"), HTTP_HOST="testserver")

        self.assertContains(response, '<p class="flyer-url">testserver</p>', html=True)

    def test_has_print_button_and_no_inline_script(self):
        content = self.client.get(reverse("core:about")).content.decode()

        self.assertIn("data-print", content)
        self.assertNotIn("onclick", content)

    def test_linked_in_menu_for_signed_in_users(self):
        user = get_user_model().objects.create_user(username="jan", password="StrongPass!2026")
        self.client.force_login(user)
        response = self.client.get(reverse("core:about"))

        self.assertContains(response, f'href="{reverse("core:about")}" aria-current="page"')

    def test_linked_in_header_and_footer_for_visitors(self):
        content = self.client.get(reverse("core:home")).content.decode()

        self.assertGreaterEqual(content.count(f'href="{reverse("core:about")}"'), 2)
