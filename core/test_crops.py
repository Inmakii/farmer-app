from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import NoReverseMatch, reverse

from .forms import CropForm, CultivationForm
from .models import Crop, Field

DUPLICATE_ERROR = "Rodzaj uprawy o tej nazwie już istnieje."
REQUIRED_ERROR = "Nazwa rodzaju uprawy jest wymagana."


class CropTestData(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="crop_user", password="StrongPass!2026"
        )
        self.other_user = user_model.objects.create_user(
            username="crop_other", password="StrongPass!2026"
        )
        self.wheat = Crop.objects.create(name="Pszenica", description="Zboże")
        self.list_url = reverse("core:crop_list")
        self.create_url = reverse("core:crop_create")


class CropAccessTests(CropTestData):
    def test_anonymous_user_is_redirected_to_login(self):
        login_url = reverse("core:login")
        for url in [self.list_url, self.create_url]:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertRedirects(response, f"{login_url}?next={url}")

    def test_anonymous_post_does_not_create_crop(self):
        response = self.client.post(self.create_url, {"name": "Owies"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Crop.objects.filter(name="Owies").exists())

    def test_urls_have_expected_paths(self):
        self.assertEqual(self.list_url, "/crops/")
        self.assertEqual(self.create_url, "/crops/add/")


class CropListTests(CropTestData):
    def test_logged_in_user_sees_sorted_list(self):
        Crop.objects.create(name="żyto ozime")
        Crop.objects.create(name="Burak cukrowy")
        Crop.objects.create(name="owies")
        self.client.force_login(self.user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/crop_list.html")
        names = [crop.name for crop in response.context["crops"]]
        self.assertEqual(names[:3], ["Burak cukrowy", "owies", "Pszenica"])
        self.assertContains(response, "Zboże")

    def test_catalog_is_shared_between_users(self):
        self.client.force_login(self.user)
        self.client.post(self.create_url, {"name": "Rzepak", "description": ""})
        self.client.logout()
        self.client.force_login(self.other_user)

        response = self.client.get(self.list_url)

        self.assertContains(response, "Rzepak")
        self.assertContains(response, "Pszenica")

    def test_empty_catalog_shows_information_and_link(self):
        Crop.objects.all().delete()
        self.client.force_login(self.user)

        response = self.client.get(self.list_url)

        self.assertContains(response, "Katalog rodzajów upraw jest pusty.")
        self.assertContains(response, "Dodaj pierwszy rodzaj uprawy")
        self.assertContains(response, f'href="{self.create_url}"')

    def test_list_has_add_button(self):
        self.client.force_login(self.user)

        response = self.client.get(self.list_url)

        self.assertContains(
            response,
            f'<a class="button" href="{self.create_url}">Dodaj rodzaj uprawy</a>',
            html=True,
        )

    def test_list_does_not_offer_edit_or_delete(self):
        self.client.force_login(self.user)

        response = self.client.get(self.list_url)

        self.assertNotContains(response, f"/crops/{self.wheat.pk}/")
        self.assertNotContains(response, "Usuń")


class CropCreateTests(CropTestData):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_valid_crop_is_created_with_message_and_redirect(self):
        response = self.client.post(
            self.create_url,
            {"name": "Kukurydza", "description": "Na ziarno"},
            follow=True,
        )

        self.assertRedirects(response, self.list_url)
        crop = Crop.objects.get(name="Kukurydza")
        self.assertEqual(crop.description, "Na ziarno")
        self.assertContains(response, "Rodzaj uprawy „Kukurydza” został dodany.")

    def test_whitespace_is_trimmed(self):
        self.client.post(
            self.create_url, {"name": "   Jęczmień  \t", "description": "  opis  "}
        )

        crop = Crop.objects.get(name="Jęczmień")
        self.assertEqual(crop.description, "opis")

    def test_empty_name_is_rejected(self):
        for name in ["", "   ", "\t\n"]:
            with self.subTest(name=repr(name)):
                form = CropForm(data={"name": name, "description": ""})

                self.assertFalse(form.is_valid())
                self.assertEqual(form.errors["name"], [REQUIRED_ERROR])

    def test_duplicate_is_rejected_case_insensitively(self):
        for name in ["Pszenica", "pszenica", "PSZENICA", "  pSzEnIcA  "]:
            with self.subTest(name=name):
                form = CropForm(data={"name": name, "description": ""})

                self.assertFalse(form.is_valid())
                self.assertEqual(form.errors["name"], [DUPLICATE_ERROR])

    def test_duplicate_with_polish_letters_is_rejected(self):
        Crop.objects.create(name="Łubin żółty")

        form = CropForm(data={"name": "łubin ŻÓŁTY", "description": ""})

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["name"], [DUPLICATE_ERROR])

    def test_duplicate_post_does_not_create_crop(self):
        response = self.client.post(
            self.create_url, {"name": "pszenica", "description": ""}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, DUPLICATE_ERROR)
        self.assertEqual(Crop.objects.filter(name__iexact="pszenica").count(), 1)

    def test_too_long_name_is_rejected_in_polish(self):
        form = CropForm(data={"name": "a" * 101, "description": ""})

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["name"], ["Nazwa może mieć maksymalnie 100 znaków."]
        )

    def test_too_long_description_is_rejected_in_polish(self):
        form = CropForm(data={"name": "Owies", "description": "a" * 1001})

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["description"], ["Opis może mieć maksymalnie 1000 znaków."]
        )

    def test_form_contains_only_safe_fields(self):
        self.assertEqual(list(CropForm().fields), ["name", "description"])

        response = self.client.get(self.create_url)

        self.assertContains(response, 'name="name"')
        self.assertContains(response, 'name="description"')
        for unsafe in ["owner", "user", "status", "created_at", 'name="id"', "is_staff"]:
            with self.subTest(unsafe=unsafe):
                self.assertNotContains(response, unsafe)

    def test_extra_posted_fields_are_ignored(self):
        self.client.post(
            self.create_url,
            {
                "name": "Gryka",
                "description": "",
                "id": str(self.wheat.pk),
                "pk": str(self.wheat.pk),
                "created_at": "2000-01-01 00:00",
                "owner": str(self.other_user.pk),
                "status": "ADMIN",
            },
        )

        crop = Crop.objects.get(name="Gryka")
        self.assertNotEqual(crop.pk, self.wheat.pk)
        self.assertNotEqual(crop.created_at.year, 2000)
        self.wheat.refresh_from_db()
        self.assertEqual(self.wheat.name, "Pszenica")
        self.assertEqual(self.wheat.description, "Zboże")

    def test_form_uses_csrf_token(self):
        response = self.client.get(self.create_url)

        self.assertContains(response, "csrfmiddlewaretoken")

    def test_post_without_csrf_token_is_rejected(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(self.create_url, {"name": "Proso"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Crop.objects.filter(name="Proso").exists())


class CropNoEditOrDeleteTests(CropTestData):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_edit_and_delete_routes_do_not_exist(self):
        for name in ["crop_update", "crop_edit", "crop_delete", "crop_detail"]:
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(f"core:{name}", kwargs={"pk": self.wheat.pk})

    def test_crafted_urls_return_404_and_do_not_change_data(self):
        pk = self.wheat.pk
        for url in [f"/crops/{pk}/", f"/crops/{pk}/edit/", f"/crops/{pk}/delete/"]:
            with self.subTest(url=url):
                get_response = self.client.get(url)
                post_response = self.client.post(url, {"name": "Zmieniona"})

                self.assertEqual(get_response.status_code, 404)
                self.assertEqual(post_response.status_code, 404)

        self.wheat.refresh_from_db()
        self.assertEqual(self.wheat.name, "Pszenica")

    def test_disallowed_http_methods_are_rejected(self):
        cases = [
            ("post", self.list_url),
            ("put", self.list_url),
            ("delete", self.list_url),
            ("put", self.create_url),
            ("patch", self.create_url),
            ("delete", self.create_url),
        ]
        for method, url in cases:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url)

                self.assertEqual(response.status_code, 405)

        self.assertTrue(Crop.objects.filter(pk=self.wheat.pk).exists())


class CropIntegrationTests(CropTestData):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.field = Field.objects.create(
            owner=self.user,
            name="Pole Katalogowe",
            area_ha="3.00",
            soil_type=Field.SoilType.LOAMY,
            location_method=Field.LocationMethod.ADDRESS,
            address="Lublin",
        )

    def test_new_crop_is_available_in_cultivation_form(self):
        self.client.post(self.create_url, {"name": "Soja", "description": ""})
        soy = Crop.objects.get(name="Soja")

        form = CultivationForm(user=self.other_user)
        response = self.client.get(reverse("core:cultivation_create"))

        self.assertIn(soy, form.fields["crop"].queryset)
        self.assertContains(response, f'<option value="{soy.pk}">Soja</option>', html=True)

    def test_navigation_contains_crop_link(self):
        response = self.client.get(reverse("core:field_list"))

        self.assertContains(
            response, f'<a href="{self.list_url}">Rodzaje upraw</a>', html=True
        )
        for name in ["core:cultivation_list", "core:report_dashboard", "core:profile"]:
            with self.subTest(name=name):
                self.assertContains(response, f'href="{reverse(name)}"')

    def test_navigation_hidden_for_anonymous_user(self):
        self.client.logout()

        response = self.client.get(reverse("core:login"))

        self.assertNotContains(response, "Rodzaje upraw")

    def test_cultivation_form_links_to_crop_creation(self):
        response = self.client.get(reverse("core:cultivation_create"))

        self.assertContains(response, "Dodaj brakujący rodzaj uprawy")
        self.assertContains(response, f'href="{self.create_url}"')

    def test_cultivation_form_explains_empty_catalog(self):
        Crop.objects.all().delete()

        response = self.client.get(reverse("core:cultivation_create"))

        self.assertContains(response, "Katalog rodzajów upraw jest pusty.")
        self.assertContains(response, "Dodaj pierwszy rodzaj uprawy")

    def test_admin_still_manages_crops(self):
        admin = get_user_model().objects.create_superuser(
            username="crop_admin", password="StrongPass!2026", email="a@example.com"
        )
        self.client.force_login(admin)

        changelist = self.client.get(reverse("admin:core_crop_changelist"))
        change = self.client.get(reverse("admin:core_crop_change", args=[self.wheat.pk]))
        delete = self.client.get(reverse("admin:core_crop_delete", args=[self.wheat.pk]))

        self.assertEqual(changelist.status_code, 200)
        self.assertContains(changelist, "Pszenica")
        self.assertEqual(change.status_code, 200)
        self.assertEqual(delete.status_code, 200)
