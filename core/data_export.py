"""All personal data of one user as a JSON-ready dictionary (GDPR art. 15 and 20:
right of access and data portability). Used by core.views.DataExportView.

The password hash is never exported. Attachment files are listed by name; the
files themselves can be downloaded from the report page.
"""

from django.conf import settings
from django.utils import timezone

from .models import ErrorReport, Field, UserActivity

EXPORT_FORMAT_VERSION = 1


def _row(obj, skip=()):
    """Plain field values of a model instance; choice fields also get a readable label."""
    data = {}
    for field in obj._meta.concrete_fields:
        if field.name in skip or field.is_relation:
            continue
        data[field.name] = getattr(obj, field.attname)
        if field.choices:
            data[f"{field.name}_label"] = str(getattr(obj, f"get_{field.name}_display")())
    return data


def _cultivation(cultivation):
    data = _row(cultivation)
    data["crop"] = cultivation.crop.name
    data["works"] = [_row(work) for work in cultivation.works.all()]
    data["sprayings"] = [_row(spraying) for spraying in cultivation.sprayings.all()]
    data["harvests"] = [_row(harvest) for harvest in cultivation.harvests.all()]
    return data


def _field(field):
    data = _row(field)
    data["cultivations"] = [_cultivation(c) for c in field.cultivations.all()]
    return data


def _report(report):
    data = _row(report)
    data["attachments"] = [
        _row(attachment, skip=("file",)) for attachment in report.attachments.all()
    ]
    return data


def export_user_data(user):
    acceptance = getattr(user, "privacy_acceptance", None)
    fields = (
        Field.objects.filter(owner=user)
        .prefetch_related(
            "cultivations__crop", "cultivations__works",
            "cultivations__sprayings", "cultivations__harvests",
        )
        .order_by("name")
    )
    reports = ErrorReport.objects.filter(user=user).prefetch_related("attachments")
    activity = UserActivity.objects.filter(user=user) | UserActivity.objects.filter(
        user__isnull=True, username=user.get_username()  # login attempts with this login
    )
    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": timezone.now(),
        "application": "Farmer App",
        "account": {
            "id": user.pk,
            "username": user.get_username(),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "date_joined": user.date_joined,
            "last_login": user.last_login,
        },
        "privacy_policy": {
            "accepted_version": acceptance.policy_version if acceptance else None,
            "accepted_at": acceptance.accepted_at if acceptance else None,
            "current_version": settings.PRIVACY_POLICY_VERSION,
        },
        "fields": [_field(field) for field in fields],
        "error_reports": [_report(report) for report in reports],
        "activity": {
            "kept_for_days": settings.ACTIVITY_RETENTION_DAYS,
            "entries": [
                _row(entry, skip=("id",)) for entry in activity.order_by("-created_at", "-pk")
            ],
        },
    }

