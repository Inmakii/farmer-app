from django.conf import settings
from django.urls import reverse
from django.utils import translation


class AdminLanguageMiddleware:
    """Show the admin only in the languages it supports.

    The site can be used in Ukrainian, but the admin panel is kept in Polish or
    English. Any other language chosen on the site falls back to the default
    language inside the admin. Must run after ``LocaleMiddleware``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path.startswith(reverse("admin:index"))
            and translation.get_language() not in settings.ADMIN_LANGUAGES
        ):
            translation.activate(settings.LANGUAGE_CODE)
            request.LANGUAGE_CODE = settings.LANGUAGE_CODE
        return self.get_response(request)
