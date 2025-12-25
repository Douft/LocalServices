"""Theming models.

This lets admins adjust the look/feel without changing templates.
We keep it simple (no new color system yet).
"""

from __future__ import annotations

from django.db import models


class ThemeSettings(models.Model):
	"""Singleton-ish theme settings.

	We only store one row and treat it as the global site theme.
	"""

	class ColorScheme(models.TextChoices):
		MIDNIGHT = "midnight", "Midnight"
		FROST = "frost", "Frost"
		SUNSET = "sunset", "Sunset"
		FOREST = "forest", "Forest"

	color_scheme = models.CharField(
		max_length=32,
		choices=ColorScheme.choices,
		default=ColorScheme.MIDNIGHT,
		help_text="Choose the site color template.",
	)

	dark_mode = models.BooleanField(default=True)
	glass_effect = models.BooleanField(default=True)
	background_gradients = models.BooleanField(
		default=True,
		help_text="If disabled, removes the decorative background gradients.",
	)
	compact_layout = models.BooleanField(
		default=False,
		help_text="If enabled, reduces padding for a denser layout.",
	)
	snow_effect = models.BooleanField(
		default=False,
		help_text="If enabled, shows a subtle falling-snow effect.",
	)

	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name_plural = "Theme settings"

	def __str__(self) -> str:
		return "Theme Settings"

	@classmethod
	def get_solo(cls) -> "ThemeSettings":
		obj, _ = cls.objects.get_or_create(pk=1)
		return obj
