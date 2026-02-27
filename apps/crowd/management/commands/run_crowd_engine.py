from django.core.management.base import BaseCommand
from apps.crowd.services.crowd_engine import generate_snapshots


class Command(BaseCommand):
    help = "Runs crowd snapshot calculation"

    def handle(self, *args, **kwargs):
        generate_snapshots()
        self.stdout.write(self.style.SUCCESS("Crowd snapshot generated"))