"""Address and parcel lookups (core.services.geodata), hint views and the field form.

The external services are never called: core.services.geodata._fetch is replaced.
"""

import json
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from ..forms import FieldForm
from ..services import geodata

LOCALITIES = [
    {"sym": "0093562", "nazwa": "Niemcz", "gmina": "Osielsko", "powiat": "bydgoski",
     "wojewodztwo": "KUJAWSKO-POMORSKIE", "label": "Niemcz (Osielsko, kujawsko-pomorskie)"},
]
ADDRESS_FOUND = {
    "found": True, "miejscowosc": "Niemcz", "ulica": "Sadyba", "nr_budynku": "11",
    "kod_pocztowy": "86-032", "gmina": "Osielsko", "lat": 53.181703, "lon": 18.021439,
}
REGION_ANSWER = "0\n040306_2.0008|Niemcz|Osielsko|powiat bydgoski|kujawsko-pomorskie\n"
PARCEL_ANSWER = (
    "0\n040306_2.0008.100/1|kujawsko-pomorskie|powiat bydgoski|Osielsko|Niemcz|100/1|"
    "18.0486198,53.1822498,18.0488512,53.1825087\n"
)
NOT_FOUND = "-1 brak wyników\n"


def fake_fetch(answers):
    """_fetch replacement: picks the answer by URL path or ULDK request name."""
    def fetch(url, params, headers=None):
        key = params.get("request") or url.rsplit("/v1/", 1)[-1]
        answer = answers[key]
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            answer = answer(params)
        return answer if isinstance(answer, str) else json.dumps(answer)
    return fetch


class GeodataServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_search_localities_maps_fields(self):
        with mock.patch.object(geodata, "_fetch", fake_fetch({"miejscowosci": LOCALITIES})):
            result = geodata.search_localities("Niemcz")

        self.assertEqual(result[0]["sym"], "0093562")
        self.assertEqual(result[0]["commune"], "Osielsko")
        self.assertEqual(result[0]["voivodeship"], "kujawsko-pomorskie")

    def test_short_query_does_not_call_the_service(self):
        with mock.patch.object(geodata, "_fetch") as fetch:
            self.assertEqual(geodata.search_localities("N"), [])
        fetch.assert_not_called()

    def test_find_address_formats_address_and_coordinates(self):
        with mock.patch.object(geodata, "_fetch", fake_fetch({"lookup/autofill": ADDRESS_FOUND})):
            found = geodata.find_address("0093562", "53264", "11")

        self.assertEqual(found["address"], "ul. Sadyba 11, 86-032 Niemcz")
        self.assertEqual(found["latitude"], Decimal("53.181703"))
        self.assertEqual(found["longitude"], Decimal("18.021439"))

    def test_find_address_rejects_bad_codes_without_calling(self):
        with mock.patch.object(geodata, "_fetch") as fetch:
            self.assertIsNone(geodata.find_address("abc", "", "1"))
        fetch.assert_not_called()

    def test_find_region_filters_by_commune(self):
        answer = REGION_ANSWER + "123456_1.0001|Niemcz|Inna|powiat x|y\n"
        with mock.patch.object(geodata, "_fetch", fake_fetch({"GetRegionByNameOrId": answer})):
            self.assertEqual(geodata.find_region("Niemcz", "Osielsko"), "040306_2.0008")
            self.assertIsNone(geodata.find_region("Niemcz"))  # two regions, no commune

    def test_get_parcel_returns_centre_of_extent(self):
        with mock.patch.object(geodata, "_fetch", fake_fetch({"GetParcelById": PARCEL_ANSWER})):
            parcel = geodata.get_parcel("040306_2.0008.100/1")

        self.assertEqual(parcel["id"], "040306_2.0008.100/1")
        self.assertEqual(parcel["latitude"], Decimal("53.182379"))
        self.assertEqual(parcel["longitude"], Decimal("18.048736"))

    def test_missing_parcel_is_none(self):
        with mock.patch.object(geodata, "_fetch", fake_fetch({"GetParcelById": NOT_FOUND})):
            self.assertIsNone(geodata.get_parcel("040306_2.0008.50"))

    def test_uldk_error_raises_service_error(self):
        with mock.patch.object(geodata, "_fetch", fake_fetch({"GetParcelById": "Błąd serwera"})):
            with self.assertRaises(geodata.GeoServiceError):
                geodata.get_parcel("040306_2.0008.100/1")


@override_settings(GEODATA_ENABLED=True)
class GeoHintViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="hints", password="StrongPass!2026")

    def test_anonymous_user_is_refused(self):
        response = self.client.get(reverse("core:geo_localities"), {"q": "Niemcz"})

        self.assertEqual(response.status_code, 403)

    def test_localities_hint(self):
        self.client.force_login(self.user)
        with mock.patch.object(geodata, "_fetch", fake_fetch({"miejscowosci": LOCALITIES})):
            response = self.client.get(reverse("core:geo_localities"), {"q": "Niemcz"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["name"], "Niemcz")

    def test_service_failure_answers_503(self):
        self.client.force_login(self.user)
        error = geodata.GeoServiceError("down")
        with mock.patch.object(geodata, "_fetch", fake_fetch({"miejscowosci": error})):
            response = self.client.get(reverse("core:geo_localities"), {"q": "Niemcz"})

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["available"])

    def test_requests_are_limited_per_user(self):
        self.client.force_login(self.user)
        with mock.patch("core.geo_views.HINT_REQUESTS_PER_MINUTE", 2), \
                mock.patch.object(geodata, "_fetch", fake_fetch({"miejscowosci": LOCALITIES})):
            codes = [
                self.client.get(reverse("core:geo_localities"), {"q": "Niemcz"}).status_code
                for _ in range(3)
            ]

        self.assertEqual(codes, [200, 200, 429])

    @override_settings(GEODATA_ENABLED=False)
    def test_disabled_service_returns_no_hints(self):
        self.client.force_login(self.user)
        with mock.patch.object(geodata, "_fetch") as fetch:
            response = self.client.get(reverse("core:geo_localities"), {"q": "Niemcz"})

        fetch.assert_not_called()
        self.assertEqual(response.json(), {"results": [], "available": False})


BASE = {"name": "Pole", "area_ha": "2.00", "soil_type": "LOAMY", "description": ""}


@override_settings(GEODATA_ENABLED=True)
class FieldFormLookupTests(TestCase):
    def setUp(self):
        cache.clear()

    def form(self, answers, **data):
        with mock.patch.object(geodata, "_fetch", fake_fetch(answers)):
            form = FieldForm(data={**BASE, **data})
            form.is_valid()
        return form

    def test_address_from_locality_street_and_number(self):
        form = self.form(
            {"lookup/autofill": ADDRESS_FOUND}, location_method="ADDRESS",
            locality_sym="0093562", locality_name="Niemcz", street_sym="53264", house_number="11",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["address"], "ul. Sadyba 11, 86-032 Niemcz")
        self.assertEqual(form.cleaned_data["latitude"], Decimal("53.181703"))

    def test_unknown_house_number_gives_one_clear_error(self):
        form = self.form(
            {"lookup/autofill": {"found": False}}, location_method="ADDRESS",
            locality_sym="0093562", locality_name="Niemcz", house_number="999",
        )

        self.assertEqual(list(form.errors), ["house_number"])

    def test_address_service_down_keeps_typed_address(self):
        form = self.form(
            {"lookup/autofill": geodata.GeoServiceError("down")}, location_method="ADDRESS",
            locality_sym="0093562", house_number="11", address="Niemcz, Sadyba 11",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["address"], "Niemcz, Sadyba 11")

    def test_parcel_from_locality_and_number(self):
        form = self.form(
            {"GetRegionByNameOrId": REGION_ANSWER, "GetParcelById": PARCEL_ANSWER},
            location_method="PARCEL", locality_name="Niemcz", locality_commune="Osielsko",
            parcel_number="100/1",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["parcel_identifier"], "040306_2.0008.100/1")
        self.assertEqual(form.cleaned_data["longitude"], Decimal("18.048736"))

    def test_missing_parcel_gives_one_clear_error(self):
        form = self.form(
            {"GetRegionByNameOrId": REGION_ANSWER, "GetParcelById": NOT_FOUND},
            location_method="PARCEL", locality_name="Niemcz", locality_commune="Osielsko",
            parcel_number="50",
        )

        self.assertEqual(list(form.errors), ["parcel_number"])

    def test_typed_full_parcel_id_is_checked(self):
        form = self.form(
            {"GetParcelById": NOT_FOUND}, location_method="PARCEL",
            parcel_identifier="040306_2.0008.50",
        )

        self.assertEqual(list(form.errors), ["parcel_identifier"])

    def test_free_form_parcel_id_is_kept_without_lookup(self):
        with mock.patch.object(geodata, "_fetch") as fetch:
            form = FieldForm(data={**BASE, "location_method": "PARCEL", "parcel_identifier": "OLD-1"})
            self.assertTrue(form.is_valid(), form.errors)
        fetch.assert_not_called()

    def test_coordinates_typed_by_user_are_not_replaced(self):
        form = self.form(
            {"lookup/autofill": ADDRESS_FOUND}, location_method="ADDRESS",
            locality_sym="0093562", locality_name="Niemcz", house_number="11",
            latitude="50.000000", longitude="20.000000",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["latitude"], Decimal("50.000000"))

    def test_typed_street_without_code_is_found_by_name(self):
        # Regression: the street code was lost in the browser; the server finds it by name.
        streets = [{"sym_ul": "16681", "nazwa_pelna": "ul. Pod Wierzbami", "label": "ul. Pod Wierzbami"}]

        def autofill(params):
            return ADDRESS_FOUND if params.get("sym_ul") == "16681" else {"found": False}

        form = self.form(
            {"ulice": streets, "lookup/autofill": autofill}, location_method="ADDRESS",
            locality_sym="0093562", locality_name="Niemcz",
            street="ul. Pod Wierzbami", street_sym="", house_number="11",
        )

        self.assertTrue(form.is_valid(), form.errors)
