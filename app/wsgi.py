"""
WSGI config for app project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')


def _truthy(value: str) -> bool:
	return value.strip().lower() in {"1", "true", "yes", "on"}


def _maybe_run_startup_tasks() -> None:
	"""Optional startup tasks for demo deployments.

	NOTE: Running migrations at import time is not recommended for real production.
	For a demo deploy (single service), it prevents "no such table" errors when the
	platform doesn't run `manage.py migrate` as part of the start command.
	"""
	auto_migrate = os.environ.get("AUTO_MIGRATE_ON_STARTUP", "")
	if _truthy(auto_migrate):
		call_command("migrate", interactive=False, verbosity=1)

	auto_seed = os.environ.get("AUTO_SEED_DEMO_ON_STARTUP", "")
	if _truthy(auto_seed):
		call_command("seed_demo", verbosity=1)


_maybe_run_startup_tasks()

application = get_wsgi_application()
