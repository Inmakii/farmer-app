from urllib.parse import urlencode

from django import template
from django.conf import settings
from django.contrib.auth import get_permission_codename
from django.db.models import Sum
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from ..models import Cultivation, ErrorReport, Field

register = template.Library()

# Start page of the admin: models grouped by topic, each with an icon and a short
# explanation, so it is clear what every section is for.
SECTIONS = (
    ("farm", _("Farm"), (
        ("core.Field", "i-map", _("Fields of all farmers with their area, soil and location.")),
        ("core.Cultivation", "i-sprout", _("What grows on which field in each season.")),
        ("core.Crop", "i-wheat", _("Crop types shared by all users.")),
    )),
    ("records", _("Work and harvests"), (
        ("core.FieldWork", "i-shovel", _("Plowing, sowing, fertilizing and other work with costs.")),
        ("core.Spraying", "i-droplets", _("Products used on the cultivations, doses and costs.")),
        ("core.Harvest", "i-package", _("Harvested amounts, revenue and profit.")),
    )),
    ("support", _("Help for users"), (
        ("core.ErrorReport", "i-bug", _("Problems reported by users of the site.")),
    )),
    ("accounts", _("Accounts"), (
        ("auth.User", "i-user", _("User accounts, passwords and administrator rights.")),
        ("auth.Group", "i-key", _("Groups of permissions for staff members.")),
    )),
)


MODEL_INFO = {
    model_key: {"icon": icon, "description": description}
    for _key, _title, entries in SECTIONS
    for model_key, icon, description in entries
}
DEFAULT_MODEL_INFO = {"icon": "i-chart", "description": ""}


@register.simple_tag
def new_error_report_count():
    """Number of error reports nobody has looked at yet."""
    return ErrorReport.objects.filter(status=ErrorReport.Status.NEW).count()


def group_models(app_list, with_counts):
    models = {
        f"{app['app_label']}.{model['object_name']}": model
        for app in app_list
        for model in app["models"]
    }

    def tile(model_key, model, info):
        return {
            "name": model["name"],
            "icon": info["icon"],
            "description": info["description"],
            "count": model["model"]._default_manager.count() if with_counts else None,
            "url": model.get("admin_url"),
            "add_url": model.get("add_url"),
            "is_reports": model_key == "core.ErrorReport",
        }

    sections = []
    for key, title, entries in SECTIONS:
        tiles = [
            tile(model_key, models.pop(model_key), MODEL_INFO[model_key])
            for model_key, _icon, _description in entries
            if model_key in models
        ]
        if tiles:
            sections.append({"key": key, "title": title, "tiles": tiles})
    # Models added later still appear, without an icon of their own.
    if models:
        sections.append({"key": "other", "title": _("Other sections"), "tiles": [
            tile(model_key, model, DEFAULT_MODEL_INFO) for model_key, model in models.items()
        ]})
    return sections


@register.simple_tag
def admin_dashboard(app_list):
    """Group the models the user may see (``app_list``) into the sections above."""
    return group_models(app_list, with_counts=True)


@register.simple_tag
def admin_nav(app_list):
    """The same sections for the side menu, without counting records."""
    return group_models(app_list, with_counts=False)


@register.simple_tag
def admin_model_info(opts):
    """Icon and short explanation of a model, shown in the heading of its pages."""
    return MODEL_INFO.get(f"{opts.app_label}.{opts.object_name}", DEFAULT_MODEL_INFO)


@register.simple_tag(takes_context=True)
def inline_add_url(context, inline_admin_formset, parent):
    """Link to add a new related record already attached to ``parent``, or ``None``."""
    if parent is None or parent.pk is None:
        return None
    formset = inline_admin_formset.formset
    opts = formset.model._meta
    user = context["request"].user
    if not user.has_perm(f"{opts.app_label}.{get_permission_codename('add', opts)}"):
        return None
    try:
        url = reverse(f"admin:{opts.app_label}_{opts.model_name}_add")
    except NoReverseMatch:
        return None
    return f"{url}?{urlencode({formset.fk.name: parent.pk})}"


@register.simple_tag
def admin_farm_stats():
    totals = Field.objects.aggregate(area=Sum("area_ha"))
    return {
        "fields": Field.objects.count(),
        "area": totals["area"] or 0,
        "active_cultivations": Cultivation.objects.filter(
            status=Cultivation.Status.ACTIVE
        ).count(),
    }


@register.simple_tag
def admin_languages():
    """Languages offered by the switcher in the admin header, as (code, name)."""
    return [(code, name) for code, name in settings.LANGUAGES if code in settings.ADMIN_LANGUAGES]
