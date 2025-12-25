"""Seed starter data for local development.

This command is safe to re-run (it uses get_or_create).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import UserProfile
from directory.models import ProviderBackendChoice, ProviderSettings, ServiceCategory, ServiceProvider
from siteads.models import AdPlacement, AdUnit


class Command(BaseCommand):
    help = "Seed starter categories, demo providers, and ensure a test admin exists."

    def add_arguments(self, parser):
        parser.add_argument("--admin-username", default="admin")
        parser.add_argument("--admin-password", default="secret")

    def handle(self, *args, **options):
        admin_username = options["admin_username"]
        admin_password = options["admin_password"]

        User = get_user_model()
        admin_user, created = User.objects.get_or_create(
            username=admin_username,
            defaults={"is_staff": True, "is_superuser": True, "email": "admin@example.com"},
        )
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.set_password(admin_password)
        admin_user.save()

        UserProfile.objects.get_or_create(user=admin_user)

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created admin '{admin_username}'."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated admin '{admin_username}'."))

        categories = [
            "Plumber",
            "Electrician",
            "Locksmith",
            "Mechanic",
            "HVAC",
            "Handyman",
            "Appliance Repair",
            "Roofing",
            "Landscaping",
            "Cleaning",
            "Moving",
        ]

        # Ensure provider settings row exists.
        provider_settings = ProviderSettings.get_solo()
        if not provider_settings.provider_backend:
            provider_settings.provider_backend = ProviderBackendChoice.OSM
            provider_settings.save()

        category_order = {
            "Plumber": 10,
            "Electrician": 20,
            "Locksmith": 30,
            "Mechanic": 40,
            "HVAC": 50,
            "Handyman": 60,
            "Appliance Repair": 70,
            "Roofing": 80,
            "Landscaping": 90,
            "Cleaning": 100,
            "Moving": 110,
        }

        category_objs = {}
        for name in categories:
            obj, _ = ServiceCategory.objects.get_or_create(name=name)
            obj.sort_order = category_order.get(name, 100)
            obj.is_active = True
            obj.save()
            category_objs[name] = obj

        demo_providers = [
            {
                "category": "Plumber",
                "name": "River City Plumbing",
                "city": "Springfield",
                "state": "IL",
                "postal_code": "62701",
                "phone": "555-0100",
                "is_suggested": True,
                "suggested_rank": 10,
            },
            {
                "category": "Electrician",
                "name": "BrightWire Electric",
                "city": "Springfield",
                "state": "IL",
                "postal_code": "62701",
                "phone": "555-0111",
                "is_suggested": False,
                "suggested_rank": 100,
            },
            {
                "category": "Locksmith",
                "name": "KeyGuard Locksmith",
                "city": "Springfield",
                "state": "IL",
                "postal_code": "62701",
                "phone": "555-0122",
                "is_suggested": True,
                "suggested_rank": 20,
            },
            {
                "category": "Plumber",
                "name": "Southeast MB Plumbing",
                "city": "Steinbach",
                "state": "MB",
                "postal_code": "R0A 0A0",
                "country": "CA",
                "phone": "555-0200",
                "website": "https://example.com/",
                "is_suggested": True,
                "suggested_rank": 15,
            },
            {
                "category": "Electrician",
                "name": "Southeast MB Electric",
                "city": "Steinbach",
                "state": "MB",
                "postal_code": "R0A 0A0",
                "country": "CA",
                "phone": "555-0201",
                "website": "https://example.com/",
                "is_suggested": False,
                "suggested_rank": 110,
            },
            {
                "category": "HVAC",
                "name": "Prairie HVAC Co.",
                "city": "Winnipeg",
                "state": "MB",
                "postal_code": "R3C 0V8",
                "country": "CA",
                "phone": "555-0300",
                "website": "https://example.com/",
                "is_suggested": True,
                "suggested_rank": 12,
            },
            {
                "category": "Handyman",
                "name": "Peg City Handyman",
                "city": "Winnipeg",
                "state": "MB",
                "postal_code": "R3C 0V8",
                "country": "CA",
                "phone": "555-0301",
                "website": "https://example.com/",
                "is_suggested": False,
                "suggested_rank": 120,
            },
            {
                "category": "Appliance Repair",
                "name": "North End Appliance Repair",
                "city": "Winnipeg",
                "state": "MB",
                "postal_code": "R2X 0M1",
                "country": "CA",
                "phone": "555-0310",
                "website": "https://example.com/",
                "is_suggested": True,
                "suggested_rank": 18,
            },
            {
                "category": "Roofing",
                "name": "Red River Roofing",
                "city": "Winnipeg",
                "state": "MB",
                "postal_code": "R3T 2N2",
                "country": "CA",
                "phone": "555-0320",
                "website": "https://example.com/",
                "is_suggested": False,
                "suggested_rank": 130,
            },
            {
                "category": "Landscaping",
                "name": "Prairie Lawn & Snow",
                "city": "Winnipeg",
                "state": "MB",
                "postal_code": "R3Y 0A1",
                "country": "CA",
                "phone": "555-0330",
                "website": "https://example.com/",
                "is_suggested": False,
                "suggested_rank": 140,
            },
            {
                "category": "Cleaning",
                "name": "Downtown Cleaning Co.",
                "city": "Winnipeg",
                "state": "MB",
                "postal_code": "R3B 1A1",
                "country": "CA",
                "phone": "555-0340",
                "website": "https://example.com/",
                "is_suggested": False,
                "suggested_rank": 150,
            },
            {
                "category": "Moving",
                "name": "Manitoba Movers",
                "city": "Winnipeg",
                "state": "MB",
                "postal_code": "R2C 0A1",
                "country": "CA",
                "phone": "555-0350",
                "website": "https://example.com/",
                "is_suggested": True,
                "suggested_rank": 14,
            },
        ]

        for item in demo_providers:
            category = category_objs[item.pop("category")]
            ServiceProvider.objects.get_or_create(category=category, name=item["name"], defaults=item)

        AdUnit.objects.get_or_create(
            placement=AdPlacement.HOME_INLINE_1,
            headline="Sponsored: Local Safety Check",
            defaults={
                "body": "Book a quick home safety inspection (electric + plumbing).",
                "target_url": "https://example.com/",
                "priority": 50,
                "is_enabled": True,
            },
        )
        AdUnit.objects.get_or_create(
            placement=AdPlacement.DASHBOARD_INLINE_1,
            headline="Sponsored: Maintenance Plan",
            defaults={
                "body": "Seasonal HVAC + appliance tune-ups. Simple monthly plan.",
                "target_url": "https://example.com/",
                "priority": 50,
                "is_enabled": True,
            },
        )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
