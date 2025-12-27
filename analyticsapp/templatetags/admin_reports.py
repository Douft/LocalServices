from __future__ import annotations

from django import template

from analyticsapp.reporting import build_reports_context

register = template.Library()


@register.inclusion_tag("admin/_reports_panel.html")
def admin_reports_panel():
	return build_reports_context(days=30)
