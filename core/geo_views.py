"""JSON hints for the field form: localities, streets and house numbers.

The browser only talks to this site (the Content Security Policy allows no other
hosts); these views ask the external services through core.services.geodata.
Only signed-in users can use them, with a per-user limit of requests.
"""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import JsonResponse
from django.views import View

from .services import geodata

HINT_REQUESTS_PER_MINUTE = 60


class GeoHintView(LoginRequiredMixin, View):
    raise_exception = True  # 403 JSON-friendly answer instead of a login redirect

    def lookup(self, params):
        raise NotImplementedError

    def get(self, request):
        if not settings.GEODATA_ENABLED:
            return JsonResponse({"results": [], "available": False})
        key = f"geohint:{request.user.pk}"
        cache.add(key, 0, 60)
        if cache.incr(key) > HINT_REQUESTS_PER_MINUTE:
            return JsonResponse({"results": [], "available": True, "limited": True}, status=429)
        try:
            results = self.lookup(request.GET)
        except geodata.GeoServiceError:
            return JsonResponse({"results": [], "available": False}, status=503)
        response = JsonResponse({"results": results, "available": True})
        response["Cache-Control"] = "private, max-age=300"
        return response


class LocalityHintView(GeoHintView):
    def lookup(self, params):
        return geodata.search_localities(params.get("q", ""))


class StreetHintView(GeoHintView):
    def lookup(self, params):
        return geodata.search_streets(params.get("sym", ""), params.get("q", ""))


class HouseNumberHintView(GeoHintView):
    def lookup(self, params):
        return geodata.list_house_numbers(params.get("sym", ""), params.get("sym_ul", ""))
