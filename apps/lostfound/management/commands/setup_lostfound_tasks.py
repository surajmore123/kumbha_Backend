"""Creates the periodic task that retries failed notices. Safe to run again."""

from django.core.management.base import BaseCommand
from django_celery_beat.models import IntervalSchedule, PeriodicTask


class Command(BaseCommand):
    help = "Retry failed Lost & Found notifications every 2 minutes (uses the existing Celery beat)."

    def handle(self, *args, **options):
        interval, _ = IntervalSchedule.objects.get_or_create(every=2, period=IntervalSchedule.MINUTES)
        PeriodicTask.objects.update_or_create(
            name="Retry Lost & Found notifications",
            defaults={"task": "apps.lostfound.tasks.retry_case_notifications", "interval": interval, "enabled": True},
        )
        self.stdout.write(self.style.SUCCESS("Scheduled."))
