"""Polish address and cadastral parcel lookups for the field form.

Sources (both free, no registration needed):

* Adresy.app (https://adresy.app) – address points from the national register PRG:
  localities, streets, house numbers, postcodes and coordinates. Without an API
  key the limit is 20 requests per minute per IP; ADRESY_API_KEY raises it.
* ULDK by GUGiK (https://uldk.gugik.gov.pl) – cadastral regions (obręby) and parcels.

Every call has a short timeout and the results are cached. A failure raises
GeoServiceError, so the form can fall back to manual input.
"""

import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

ADRESY_URL = "https://api.adresy.app/api/v1/"
ULDK_URL = "https://uldk.gugik.gov.pl/"
TIMEOUT_SECONDS = 6
CACHE_SECONDS = 24 * 60 * 60
USER_AGENT = "FarmerApp/1.0"

# Full parcel identifier, e.g. 040306_2.0008.100/1 (TERYT unit _ type . region . number).
PARCEL_ID_RE = re.compile(r"^\d{6}_\d\.\d{4}(\.AR_\d+)?\.[0-9A-Za-z/]+$")
PARCEL_NUMBER_RE = re.compile(r"^[0-9]+(/[0-9]+)?[A-Za-z]?$")
SYM_RE = re.compile(r"^\d{7}$")
SYM_UL_RE = re.compile(r"^\d{5}$")
COORD_PLACES = Decimal("0.000001")


class GeoServiceError(Exception):
    """The external service did not answer or answered with something unexpected."""


def _fetch(url, params, *, headers=None):
    key = "geodata:" + hashlib.sha256(
        (url + "?" + urlencode(sorted(params.items()))).encode()
    ).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    request = Request(
        url + "?" + urlencode(params),
        headers={"User-Agent": USER_AGENT, **(headers or {})},
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (fixed https URLs)
            body = response.read().decode("utf-8")
    except (URLError, TimeoutError, OSError, UnicodeDecodeError) as error:
        raise GeoServiceError(str(error)) from error
    cache.set(key, body, CACHE_SECONDS)
    return body


def _adresy(path, params):
    headers = {}
    api_key = getattr(settings, "ADRESY_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key
    body = _fetch(ADRESY_URL + path, params, headers=headers)
    try:
        return json.loads(body)
    except ValueError as error:
        raise GeoServiceError("invalid JSON from adresy.app") from error


def _uldk(request_name, identifier, result, **extra):
    body = _fetch(
        ULDK_URL,
        {"request": request_name, "id": identifier, "result": result, **extra},
    )
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        raise GeoServiceError("empty answer from ULDK")
    status = lines[0].strip()
    if status.startswith("-1"):
        return []  # "-1 brak wyników": nothing found
    if status != "0":
        raise GeoServiceError(f"ULDK error: {status[:100]}")
    return [line.split("|") for line in lines[1:]]


def _coord(value):
    return Decimal(str(value)).quantize(COORD_PLACES, rounding=ROUND_HALF_UP)


# Addresses -------------------------------------------------------------------


def search_localities(query):
    """Localities whose name starts with the query, with their gmina and voivodeship."""
    query = (query or "").strip()
    if len(query) < 2:
        return []
    data = _adresy("miejscowosci", {"q": query[:100]})
    if not isinstance(data, list):
        raise GeoServiceError("unexpected localities answer")
    return [
        {
            "sym": item.get("sym", ""),
            "name": item.get("nazwa", ""),
            "commune": item.get("gmina", ""),
            "county": item.get("powiat", ""),
            "voivodeship": (item.get("wojewodztwo") or "").lower(),
            "label": item.get("label", ""),
        }
        for item in data[:15]
        if SYM_RE.match(str(item.get("sym", "")))
    ]


def search_streets(sym, query=""):
    if not SYM_RE.match(sym or ""):
        return []
    data = _adresy("ulice", {"sym": sym, "q": (query or "").strip()[:100]})
    if not isinstance(data, list):
        raise GeoServiceError("unexpected streets answer")
    return [
        {"sym_ul": item.get("sym_ul", ""), "label": item.get("nazwa_pelna") or item.get("label", "")}
        for item in data[:20]
        if SYM_UL_RE.match(str(item.get("sym_ul", "")))
    ]


STREET_PREFIX_RE = re.compile(r"^(ul|al|pl|os|rondo|skwer|bulw|droga)\.?\s+", re.IGNORECASE)


def find_street(sym, name):
    """Street code (sym_ul) for a street name typed or chosen in a locality, or ""."""
    name = (name or "").strip()
    if not SYM_RE.match(sym or "") or not name:
        return ""
    bare = STREET_PREFIX_RE.sub("", name).strip().lower()
    streets = search_streets(sym, bare)
    exact = [
        street for street in streets
        if street["label"].strip().lower() in (name.lower(), bare)
        or STREET_PREFIX_RE.sub("", street["label"]).strip().lower() == bare
    ]
    return exact[0]["sym_ul"] if len(exact) == 1 else ""


def list_house_numbers(sym, sym_ul=""):
    if not SYM_RE.match(sym or "") or (sym_ul and not SYM_UL_RE.match(sym_ul)):
        return []
    params = {"sym": sym}
    if sym_ul:
        params["sym_ul"] = sym_ul
    data = _adresy("numery", params)
    if not isinstance(data, list):
        raise GeoServiceError("unexpected house numbers answer")

    def sort_key(number):
        digits = re.match(r"\d+", number)
        return (int(digits.group()) if digits else 0, number)

    return sorted((str(n) for n in data), key=sort_key)[:500]


def find_address(sym, sym_ul, number):
    """Exact address point, or None when the address does not exist."""
    number = (number or "").strip()
    if not SYM_RE.match(sym or "") or (sym_ul and not SYM_UL_RE.match(sym_ul)) or not number:
        return None
    params = {"sym": sym, "nr": number[:20]}
    if sym_ul:
        params["sym_ul"] = sym_ul
    data = _adresy("lookup/autofill", params)
    if not isinstance(data, dict):
        raise GeoServiceError("unexpected address answer")
    if not data.get("found"):
        return None
    street = data.get("ulica") or ""
    place = data.get("miejscowosc") or ""
    house = data.get("nr_budynku") or number
    postcode = data.get("kod_pocztowy") or ""
    first = f"ul. {street} {house}" if street else f"{place} {house}"
    text = f"{first}, {postcode} {place}".replace(" ,", ",").strip(", ")
    return {
        "address": text,
        "latitude": _coord(data["lat"]),
        "longitude": _coord(data["lon"]),
        "commune": data.get("gmina") or "",
    }


def geocode_address(text):
    """Coordinates for a free-text address, or None when there is no confident match."""
    text = (text or "").strip()
    if len(text) < 3:
        return None
    data = _adresy("match", {"q": text[:255]})
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        return None
    first = results[0]
    match = first.get("match") or {}
    if first.get("status") != "matched" or match.get("lat") is None:
        return None
    return {"latitude": _coord(match["lat"]), "longitude": _coord(match["lon"])}


# Parcels ---------------------------------------------------------------------


def find_region(name, commune=""):
    """Cadastral region (obręb) id for a locality name, e.g. Niemcz -> 040306_2.0008.

    ULDK searches by the exact region name. When several regions share the name,
    the commune (gmina) chooses between them; without a single match, None.
    """
    name = (name or "").strip()
    if not name:
        return None
    rows = _uldk("GetRegionByNameOrId", name[:100], "id,region,commune,county,voivodeship")
    matches = [row for row in rows if len(row) >= 3]
    if commune:
        matches = [row for row in matches if row[2].strip().lower() == commune.strip().lower()]
    return matches[0][0].strip() if len(matches) == 1 else None


def get_parcel(parcel_id):
    """Parcel data and the centre of its bounding box, or None when it does not exist."""
    parcel_id = (parcel_id or "").strip()
    if not PARCEL_ID_RE.match(parcel_id):
        return None
    rows = _uldk(
        "GetParcelById", parcel_id,
        "id,voivodeship,county,commune,region,parcel,geom_extent", srid="4326",
    )
    if not rows or len(rows[0]) < 7:
        return None
    row = rows[0]
    try:
        x1, y1, x2, y2 = (Decimal(part) for part in row[6].split(","))
    except (ValueError, ArithmeticError) as error:
        raise GeoServiceError("unexpected parcel extent") from error
    return {
        "id": row[0].strip(),
        "voivodeship": row[1],
        "county": row[2],
        "commune": row[3],
        "region": row[4],
        "number": row[5],
        "latitude": _coord((y1 + y2) / 2),
        "longitude": _coord((x1 + x2) / 2),
    }
