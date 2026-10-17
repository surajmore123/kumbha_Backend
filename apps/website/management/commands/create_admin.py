"""Create an admin panel account, or reset its password:

    python manage.py create_admin <username> "<Full name>"

The password is asked for interactively so it never lands in shell history. Use this for the first
admin; after that, admins add each other in the panel (Admins section)."""

import getpass

from django.core.management.base import BaseCommand, CommandError

from apps.website.core import hash_password
from apps.website.models import AdminAccount


class Command(BaseCommand):
    help = "Create an admin panel account (or reset its password)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("name", nargs="?", help="Full name shown in the panel (defaults to the username)")

    def handle(self, *args, username, name, **options):
        password = getpass.getpass("Password (min 8 characters): ")
        if len(password) < 8 or password != getpass.getpass("Repeat password: "):
            raise CommandError("Passwords must match and be at least 8 characters.")
        admin = AdminAccount.objects.filter(username__iexact=username).first()
        if admin:
            admin.password_hash = hash_password(password)
            admin.is_active, admin.failed_logins, admin.locked_until = True, 0, None
            admin.token_version += 1
            if name:
                admin.name = name
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"Password reset for admin '{admin.username}'."))
        else:
            AdminAccount.objects.create(username=username, name=name or username, password_hash=hash_password(password))
            self.stdout.write(self.style.SUCCESS(f"Admin '{username}' created."))
