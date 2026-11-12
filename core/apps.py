from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    name = 'core'
    # Shown in the admin breadcrumbs instead of "Core".
    verbose_name = _("Farm")
