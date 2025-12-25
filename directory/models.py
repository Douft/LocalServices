"""Directory models (services and providers)."""

from __future__ import annotations

from django.db import models
from django.utils.text import slugify


class ServiceCategory(models.Model):
	"""A type of service users search for (plumber, mechanic, etc.)."""

	name = models.CharField(max_length=80, unique=True)
	slug = models.SlugField(max_length=100, unique=True, blank=True)
	is_active = models.BooleanField(default=True)
	sort_order = models.PositiveIntegerField(default=100)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["sort_order", "name"]

	def save(self, *args, **kwargs):
		if not self.slug:
			self.slug = slugify(self.name)
		super().save(*args, **kwargs)

	def __str__(self) -> str:
		return self.name


class ServiceProvider(models.Model):
	"""A local business/provider that offers a service category."""

	category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="providers")

	name = models.CharField(max_length=120)
	description = models.TextField(blank=True)

	phone = models.CharField(max_length=30, blank=True)
	email = models.EmailField(blank=True)
	website = models.URLField(blank=True)

	address_line1 = models.CharField(max_length=120, blank=True)
	address_line2 = models.CharField(max_length=120, blank=True)
	city = models.CharField(max_length=80, blank=True)
	state = models.CharField(max_length=80, blank=True)
	postal_code = models.CharField(max_length=20, blank=True)
	country = models.CharField(max_length=80, blank=True, default="CA")

	latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

	is_suggested = models.BooleanField(
		default=False,
		help_text="If enabled, this provider can appear in the 'Suggested' section.",
	)
	suggested_rank = models.PositiveIntegerField(
		default=100,
		help_text="Lower ranks show higher in Suggested results.",
	)
	is_active = models.BooleanField(default=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-is_suggested", "suggested_rank", "name"]
		indexes = [
			models.Index(fields=["category", "postal_code", "is_active"]),
			models.Index(fields=["category", "city", "state", "is_active"]),
			models.Index(fields=["is_suggested", "suggested_rank"]),
		]

	def __str__(self) -> str:
		return self.name


class ProviderBackendChoice(models.TextChoices):
	OSM = "OSM", "OpenStreetMap"
	GOOGLE = "GOOGLE", "Google Places"


class ProviderSettings(models.Model):
	"""Singleton-ish provider configuration.

	This allows admins to change provider backend and API keys without code/.env edits.
	"""

	provider_backend = models.CharField(
		max_length=16,
		choices=ProviderBackendChoice.choices,
		default=ProviderBackendChoice.OSM,
		help_text="Select which provider source powers external results.",
	)
	google_maps_api_key = models.CharField(
		max_length=255,
		blank=True,
		help_text="Optional. If set, overrides GOOGLE_MAPS_API_KEY from environment.",
	)
	google_region = models.CharField(
		max_length=2,
		blank=True,
		default="CA",
		help_text="2-letter region bias for Google (e.g., CA, US).",
	)

	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name_plural = "Provider settings"

	def __str__(self) -> str:
		return "Provider Settings"

	@classmethod
	def get_solo(cls) -> "ProviderSettings":
		obj, _ = cls.objects.get_or_create(pk=1)
		return obj
