"""Account deletion, the crop catalog, the field map and the coordinates row."""

import json
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from ..crop_catalog import catalog
from ..models import Crop, Cultivation, ErrorReport, Field
from ..services import geodata

PASSWORD = "StrongPass!2026"


class AccountDeleteTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.user = users.objects.create_user(username="leaving", email="l@example.com", password=PASSWORD)
        self.other = users.objects.create_user(username="staying", password=PASSWORD)
        self.crop = Crop.objects.create(name="Pszenica")
        field = Field.objects.create(
            owner=self.user, name="Pole", area_ha=Decimal("1.00"),
            soil_type=Field.SoilType.LOAMY, location_method=Field.LocationMethod.GPS,
            latitude=Decimal("52.1"), longitude=Decimal("21.0"),
        )
        Cultivation.objects.create(
            field=field, crop=self.crop, season_year=2026, status=Cultivation.Status.ACTIVE,
        )
        ErrorReport.objects.create(
            user=self.user, category=ErrorReport.Category.OTHER,
            description="x", status=ErrorReport.Status.NEW,
        )
        self.other_field = Field.objects.create(
            owner=self.other, name="Pole", area_ha=Decimal("2.00"),
            soil_type=Field.SoilType.SANDY, location_method=Field.LocationMethod.GPS,
            latitude=Decimal("50"), longitude=Decimal("20"),
        )
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.client.force_login(self.user)
        self.url = reverse("core:account_delete")

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response["Location"])

    def test_page_lists_what_is_deleted(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Fields: 1, with their cultivations")
        self.assertContains(response, 'data-confirm-word="DELETE"')

    def test_profile_links_to_deletion(self):
        response = self.client.get(reverse("core:profile"))

        self.assertContains(response, self.url)

    def test_wrong_word_keeps_account(self):
        response = self.client.post(self.url, {"password": PASSWORD, "confirmation": "DELET"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFormError(response.context["form"], "confirmation", "Type DELETE exactly as shown to confirm.")

    def test_wrong_password_keeps_account(self):
        response = self.client.post(self.url, {"password": "wrong", "confirmation": "DELETE"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_get_does_not_delete(self):
        self.client.get(self.url)

        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_deletes_account_and_data_and_logs_out(self):
        response = self.client.post(self.url, {"password": PASSWORD, "confirmation": " delete "})

        self.assertRedirects(response, reverse("core:home"), fetch_redirect_response=False)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Field.objects.filter(owner_id=self.user.pk).exists())
        self.assertFalse(Cultivation.objects.filter(field__owner_id=self.user.pk).exists())
        self.assertFalse(ErrorReport.objects.filter(user_id=self.user.pk).exists())
        # Other users' data and the shared crop catalog stay.
        self.assertTrue(Field.objects.filter(pk=self.other_field.pk).exists())
        self.assertTrue(Crop.objects.filter(pk=self.crop.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_polish_word(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "pl"
        response = self.client.post(self.url, {"password": PASSWORD, "confirmation": "USUŃ"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_ukrainian_word(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "uk"
        response = self.client.post(self.url, {"password": PASSWORD, "confirmation": "ВИДАЛИТИ"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())


class SeedCropsTests(TestCase):
    def test_adds_catalog_once_and_keeps_existing(self):
        Crop.objects.create(name="pszenica", description="własny opis")

        call_command("seed_crops", stdout=StringIO())
        call_command("seed_crops", stdout=StringIO())

        self.assertEqual(Crop.objects.count(), len(catalog()))
        wheat = Crop.objects.get(name__iexact="pszenica")
        self.assertEqual(wheat.description, "własny opis")
        self.assertEqual(Crop.objects.get(name="Słonecznik").description, "Rośliny oleiste")

    def test_catalog_names_are_unique(self):
        names = [name.casefold() for name, _group in catalog()]

        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(len(name) <= 100 for name in names))


class FieldMapTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="mapper", password=PASSWORD)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.client.force_login(self.user)

    def make_field(self, **values):
        data = {
            "owner": self.user, "name": "Pole", "area_ha": Decimal("1.00"),
            "soil_type": Field.SoilType.LOAMY, "location_method": Field.LocationMethod.MAP,
            "latitude": Decimal("53.186288"), "longitude": Decimal("18.035840"),
        }
        data.update(values)
        return Field.objects.create(**data)

    def test_form_has_map_picker_and_coordinates_side_by_side(self):
        response = self.client.get(reverse("core:field_create"))

        self.assertContains(response, 'data-field-map="pick"')
        self.assertContains(response, reverse("core:geo_place"))
        self.assertContains(response, "core/vendor/leaflet/leaflet.js")
        self.assertContains(response, "core/field-map.js")
        html = response.content.decode()
        row = html.index('<div class="field-row">')
        self.assertLess(row, html.index('name="latitude"'))
        self.assertLess(html.index('name="longitude"'), html.index('data-field-map="pick"'))

    def test_map_point_saves_coordinates(self):
        response = self.client.post(reverse("core:field_create"), {
            "name": "Z mapy", "area_ha": "3.5", "soil_type": "LOAMY",
            "location_method": "MAP", "latitude": "53.186288", "longitude": "18.035840",
        })

        self.assertEqual(response.status_code, 302)
        field = Field.objects.get(name="Z mapy")
        self.assertEqual(field.latitude, Decimal("53.186288"))

    def test_detail_shows_coordinates_in_one_row_with_map(self):
        field = self.make_field()

        response = self.client.get(reverse("core:field_detail", args=[field.pk]))

        self.assertContains(response, "53.186288, 18.035840")
        self.assertContains(response, "query=53.186288%2C18.035840")
        self.assertContains(response, 'data-field-map="view"')
        self.assertNotContains(response, "<dt>Latitude</dt>")

    def test_detail_without_coordinates_has_no_map(self):
        field = self.make_field(
            location_method=Field.LocationMethod.ADDRESS, address="Sadyba 11, Niemcz",
            latitude=None, longitude=None,
        )

        response = self.client.get(reverse("core:field_detail", args=[field.pk]))

        self.assertNotContains(response, "data-field-map")
        self.assertNotContains(response, "leaflet.js")

    @override_settings(GEODATA_ENABLED=True)
    def test_place_search_endpoint(self):
        answer = {"results": [{"status": "low_confidence", "match": {
            "miejscowosc": "Niemcz", "gmina": "Osielsko", "lat": 53.186288, "lon": 18.03584,
        }}]}
        with mock.patch.object(geodata, "_fetch", return_value=json.dumps(answer)):
            response = self.client.get(reverse("core:geo_place"), {"q": "Niemcz"})

        self.assertEqual(response.json()["results"], [{
            "latitude": "53.186288", "longitude": "18.035840",
            "label": "Niemcz, Osielsko", "zoom": 14,
        }])

    @override_settings(GEODATA_ENABLED=True)
    def test_place_search_not_found(self):
        answer = {"results": [{"status": "not_found", "match": None}]}
        with mock.patch.object(geodata, "_fetch", return_value=json.dumps(answer)):
            response = self.client.get(reverse("core:geo_place"), {"q": "Nigdzie"})

        self.assertEqual(response.json()["results"], [])

    def test_place_search_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("core:geo_place"), {"q": "Niemcz"})

        self.assertEqual(response.status_code, 403)
