"""Create/update a demo admin user.

Intended for demo deployments where you don't have shell access.
Do NOT enable in real production.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import UserProfile


class Command(BaseCommand):
    help = "Ensure a demo superuser exists (default: admin/secret)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--password", default="secret")
        parser.add_argument("--email", default="admin@example.com")

    def handle(self, *args, **options):
        username: str = options["username"]
        password: str = options["password"]
        email: str = options["email"]

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )

        # Always enforce admin flags + password for a predictable demo.
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        # Optional profile (used by location defaults).
        UserProfile.objects.get_or_create(user=user)

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created demo admin '{username}'."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated demo admin '{username}'."))
