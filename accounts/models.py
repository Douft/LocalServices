"""Account-related models.

We keep Django's default User model (good enough for now) and store
location + preferences in a separate profile table.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
	"""Stores per-user profile info (primarily location for matching)."""

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")

	city = models.CharField(max_length=80, blank=True)
	state = models.CharField(max_length=80, blank=True)
	postal_code = models.CharField(max_length=20, blank=True)
	country = models.CharField(max_length=80, blank=True, default="CA")

	latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

	default_radius_km = models.PositiveIntegerField(
		default=50,
		help_text="Default search radius (used when we have lat/lng).",
	)
	allow_geolocation = models.BooleanField(
		default=True,
		help_text="If enabled, the UI can ask for browser location to improve results.",
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"Profile: {self.user.username}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile_for_new_user(sender, instance, created, **kwargs):
	if created:
		UserProfile.objects.create(user=instance)
