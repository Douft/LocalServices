"""Analytics models.

We track two key concepts:
- SearchEvent: what users are requesting (intent)
- UsageEvent: what users actually use/contact (behavior)
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from directory.models import ServiceCategory, ServiceProvider


class SearchEvent(models.Model):
	"""A user searched for a service category (or typed a query)."""

	user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
	service_category = models.ForeignKey(ServiceCategory, null=True, blank=True, on_delete=models.SET_NULL)
	query_text = models.CharField(max_length=120, blank=True)

	# Location snapshot at the time of search
	city = models.CharField(max_length=80, blank=True)
	state = models.CharField(max_length=80, blank=True)
	postal_code = models.CharField(max_length=20, blank=True)
	latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["service_category", "created_at"]),
			models.Index(fields=["postal_code", "created_at"]),
		]

	def __str__(self) -> str:
		if self.service_category:
			return f"Search: {self.service_category.name}"
		return f"Search: {self.query_text or '(blank)'}"


class UsageAction(models.TextChoices):
	VIEW = "view", "Viewed"
	CONTACT = "contact", "Contacted"
	CLICK_WEBSITE = "click_website", "Clicked Website"


class UsageEvent(models.Model):
	"""A user interacted with a provider (used/contacted/clicked)."""

	user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
	service_category = models.ForeignKey(ServiceCategory, null=True, blank=True, on_delete=models.SET_NULL)
	provider = models.ForeignKey(ServiceProvider, null=True, blank=True, on_delete=models.SET_NULL)

	action = models.CharField(max_length=32, choices=UsageAction.choices)

	# Location snapshot
	city = models.CharField(max_length=80, blank=True)
	state = models.CharField(max_length=80, blank=True)
	postal_code = models.CharField(max_length=20, blank=True)
	latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["service_category", "action", "created_at"]),
			models.Index(fields=["provider", "action", "created_at"]),
		]

	def __str__(self) -> str:
		provider_name = self.provider.name if self.provider else "(no provider)"
		return f"Usage: {self.action} {provider_name}"
