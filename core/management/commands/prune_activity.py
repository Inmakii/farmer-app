from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import UserActivity


class Command(BaseCommand):
    help = "Remove user activity older than ACTIVITY_RETENTION_DAYS (default 30 days)."

    def handle(self, *args, **options):
        days = settings.ACTIVITY_RETENTION_DAYS
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = UserActivity.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"User activity: removed {deleted} entries older than {days} days.")
