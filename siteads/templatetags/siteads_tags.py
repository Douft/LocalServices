"""Template tags for gentle ad placements."""

from __future__ import annotations

from django import template
from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Q
from django.utils import timezone

from siteads.models import AdUnit

register = template.Library()


@register.inclusion_tag("siteads/ad_unit.html")
def ad_unit(placement: str):
    """Render the top eligible ad for a placement.

    Returns None when no ads are enabled/eligible.
    """

    try:
        now = timezone.now()
        unit = (
            AdUnit.objects.filter(placement=placement, is_enabled=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
            .order_by("priority", "-created_at")
            .first()
        )
        return {"ad": unit}
    except (OperationalError, ProgrammingError):
        # Database not migrated yet.
        return {"ad": None}
