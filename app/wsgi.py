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
	# Avoid multiple gunicorn workers racing migrations.
	# We use an atomic lock file create on Linux (/tmp).
	lock_path = os.environ.get("STARTUP_TASK_LOCKFILE", "/tmp/local_services_startup.lock")
	lock_fd = None
	try:
		lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
		os.write(lock_fd, str(os.getpid()).encode("utf-8"))
		os.close(lock_fd)
		lock_fd = None
	except FileExistsError:
		return
	except Exception:
		# If we can't create the lock, don't block startup.
		pass
	finally:
		if lock_fd is not None:
			try:
				os.close(lock_fd)
			except Exception:
				pass

	try:
		auto_migrate = os.environ.get("AUTO_MIGRATE_ON_STARTUP", "")
		if _truthy(auto_migrate):
			call_command("migrate", interactive=False, verbosity=1)

		auto_seed = os.environ.get("AUTO_SEED_DEMO_ON_STARTUP", "")
		if _truthy(auto_seed):
			call_command("seed_demo", verbosity=1)
	except Exception:
		# Demo convenience only; never prevent the server from starting.
		pass


application = get_wsgi_application()

# Run demo startup tasks only after Django is fully initialized.
_maybe_run_startup_tasks()
