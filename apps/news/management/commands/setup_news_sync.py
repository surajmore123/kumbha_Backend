"""Creates the periodic task for feed syncing. Safe to run again."""

from django.core.management.base import BaseCommand
from django_celery_beat.models import IntervalSchedule, PeriodicTask


class Command(BaseCommand):
    help = "Schedule the news feed sync every 6 hours (uses the existing Celery beat)."

    def handle(self, *args, **options):
        interval, _ = IntervalSchedule.objects.get_or_create(every=6, period=IntervalSchedule.HOURS)
        PeriodicTask.objects.update_or_create(
            name="Sync Kumbh news feeds",
            defaults={"task": "apps.news.tasks.sync_news_sources", "interval": interval, "enabled": True},
        )
        self.stdout.write(self.style.SUCCESS("Scheduled. Only sources marked active are fetched."))
