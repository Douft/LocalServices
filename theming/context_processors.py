from __future__ import annotations

from django.db.utils import OperationalError, ProgrammingError

from .models import ThemeSettings


def theme_settings(request):
	"""Expose global theme settings to templates."""
	try:
		return {"theme_settings": ThemeSettings.get_solo()}
	except (OperationalError, ProgrammingError):
		# Database not migrated yet (common on first deploy).
		return {"theme_settings": ThemeSettings()}
