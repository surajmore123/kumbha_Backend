"""Creates the periodic retry and tidy-up. Safe to run again."""

from django.core.management.base import BaseCommand
from django_celery_beat.models import IntervalSchedule, PeriodicTask


class Command(BaseCommand):
    help = "Retry emergency notifications every minute (uses the existing Celery beat)."

    def handle(self, *args, **options):
        interval, _ = IntervalSchedule.objects.get_or_create(every=1, period=IntervalSchedule.MINUTES)
        PeriodicTask.objects.update_or_create(
            name="Sweep emergency SOS",
            defaults={"task": "apps.emergency.tasks.sweep_emergencies", "interval": interval, "enabled": True},
        )
        self.stdout.write(self.style.SUCCESS("Scheduled."))
