"""Ads models.

These are intentionally lightweight and designed for *gentle* ad placements
that don't take over the page.
"""

from django.db import models


class AdPlacement(models.TextChoices):
    HOME_INLINE_1 = "home_inline_1", "Home (Inline)"
    DASHBOARD_INLINE_1 = "dashboard_inline_1", "Dashboard (Inline)"


class AdUnit(models.Model):
    """A small ad unit rendered in a specific placement."""

    placement = models.CharField(max_length=64, choices=AdPlacement.choices)
    headline = models.CharField(max_length=80)
    body = models.CharField(max_length=140, blank=True)
    target_url = models.URLField(blank=True)

    is_enabled = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100, help_text="Lower is shown first.")

    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["placement", "priority", "-created_at"]

    def __str__(self) -> str:
        return f"{self.get_placement_display()}: {self.headline}"
