"""
Send due event reminders without Celery (local development).

    python manage.py run_reminder_dispatcher            # every 60 s until Ctrl+C
    python manage.py run_reminder_dispatcher --once     # one pass

In Docker/production the Celery beat task does this every minute; don't
run both against the same database.
"""

import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.events.reminders import dispatch_due_reminders


class Command(BaseCommand):
    help = "Send due event reminders (use where Celery/Redis isn't running)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=60)

    def handle(self, *args, **options):
        interval = max(10, options["interval"])
        while True:
            close_old_connections()
            summary = dispatch_due_reminders()
            self.stdout.write(f"{time.strftime('%H:%M:%S')} reminders: {summary}")
            if options["once"]:
                return
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                return
