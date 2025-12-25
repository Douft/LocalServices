from __future__ import annotations

from .models import ThemeSettings


def theme_settings(request):
	"""Expose global theme settings to templates."""

	return {"theme_settings": ThemeSettings.get_solo()}
