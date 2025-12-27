from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django import template
from django.db.models import DateTimeField, Exists, OuterRef, Value
from django.db.models.functions import Coalesce

from messaging.models import SupportMessage, SupportThread

register = template.Library()


@register.inclusion_tag("admin/_messages_panel.html")
def admin_messages_panel(limit: int = 6):
	"""Render a compact admin-home panel for unread user messages.

	We treat any user message newer than the staff-read timestamp as unread.
	"""
	epoch = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
	cutoff = Coalesce(OuterRef("last_staff_read_at"), Value(epoch, output_field=DateTimeField()))

	unread_exists = Exists(
		SupportMessage.objects.filter(
			thread=OuterRef("pk"),
			from_staff=False,
			created_at__gt=cutoff,
		)
	)

	unread_threads = (
		SupportThread.objects.select_related("user")
		.annotate(_unread_for_staff=unread_exists)
		.filter(_unread_for_staff=True)
		.order_by("-last_message_at", "-updated_at")
	)

	return {
		"unread_count": unread_threads.count(),
		"unread_threads": unread_threads[: max(1, int(limit))],
	}
