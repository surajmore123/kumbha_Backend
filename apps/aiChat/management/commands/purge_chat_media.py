"""
Retention for generated chat files.

    python manage.py purge_chat_media --days 30 [--dry-run]

Deletes generated voice replies (chat/<user>/voice/) and document extracts
(chat/<user>/extracts/) older than --days, and removes the matching
extract references from message metadata. Uploaded originals referenced by
chat history are left alone.
"""

from datetime import timedelta

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.aiChat.models import ChatMessage
from apps.aiChat.services.history_service import INTERNAL_KEY

_GENERATED_FOLDERS = ("voice", "extracts")


class Command(BaseCommand):
    help = "Delete generated voice replies and document extracts older than N days."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=max(1, options["days"]))
        dry_run = options["dry_run"]
        removed = 0

        try:
            users, _ = default_storage.listdir("chat")
        except (FileNotFoundError, NotImplementedError, OSError):
            users = []
        for user_folder in users:
            for folder in _GENERATED_FOLDERS:
                path = f"chat/{user_folder}/{folder}"
                try:
                    _, files = default_storage.listdir(path)
                except (FileNotFoundError, NotImplementedError, OSError):
                    continue
                for name in files:
                    key = f"{path}/{name}"
                    try:
                        modified = default_storage.get_modified_time(key)
                    except (NotImplementedError, OSError):
                        continue
                    if modified < cutoff:
                        removed += 1
                        if not dry_run:
                            default_storage.delete(key)

        cleared = 0
        stale = ChatMessage.objects.filter(
            created_at__lt=cutoff, metadata__has_key=INTERNAL_KEY,
        )
        for message in stale.iterator():
            internal = dict(message.metadata.get(INTERNAL_KEY) or {})
            if internal.pop("extract_key", None):
                cleared += 1
                if not dry_run:
                    message.metadata[INTERNAL_KEY] = internal
                    message.save(update_fields=["metadata"])

        prefix = "[dry run] would remove" if dry_run else "Removed"
        self.stdout.write(self.style.SUCCESS(
            f"{prefix} {removed} file(s); cleared {cleared} extract reference(s)."
        ))
