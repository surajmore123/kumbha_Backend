"""
Check push notifications end to end.

    python manage.py send_test_notification --phone 9876543210
    python manage.py send_test_notification --phone 9876543210 --type event
    python manage.py send_test_notification --all --dry-run

--dry-run asks FCM to validate the credentials and tokens without
delivering anything (and without deactivating tokens).
"""

from django.core.management.base import BaseCommand, CommandError

from apps.authentication.models import FCMDevice, User
from utils.push_notifications import (
    CHANNEL_ALERTS,
    CHANNEL_EVENTS,
    send_to_tokens,
)


class Command(BaseCommand):
    help = "Send a test push to one user's devices (or validate all tokens)."

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--phone")
        target.add_argument("--all", action="store_true")
        parser.add_argument("--type", choices=["event", "crowd"], default="event")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        devices = FCMDevice.objects.filter(is_active=True)
        if options["phone"]:
            try:
                user = User.objects.get(phone_number=options["phone"])
            except User.DoesNotExist as exc:
                raise CommandError("No user with that phone number.") from exc
            devices = devices.filter(user=user)
        tokens = list(devices.values_list("token", flat=True))
        if not tokens:
            raise CommandError("No active devices registered for that target.")

        if options["type"] == "event":
            title, body = "Event reminder (test)", "This is a test event reminder from KumbhaPath."
            data = {"type": "event_reminder", "route": "/shahiEvents"}
            channel = CHANNEL_EVENTS
        else:
            title, body = "Crowd alert (test)", "This is a test crowd alert from KumbhaPath."
            data = {"type": "crowd_alert", "route": "/liveCroud"}
            channel = CHANNEL_ALERTS

        result = send_to_tokens(
            tokens, title, body, data=data, channel_id=channel, dry_run=options["dry_run"],
        )
        prefix = "[dry run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}{len(tokens)} device(s): {result}"))
