from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import render

from analyticsapp.models import SearchEvent, UsageAction, UsageEvent


@staff_member_required
def reports(request):
	top_requested = (
		SearchEvent.objects.values("service_category__name")
		.annotate(total=Count("id"))
		.order_by("-total")[:10]
	)

	top_used = (
		UsageEvent.objects.filter(action__in=[UsageAction.CONTACT, UsageAction.CLICK_WEBSITE])
		.values("provider__name")
		.annotate(total=Count("id"))
		.order_by("-total")[:10]
	)

	return render(
		request,
		"admin/reports.html",
		{
			"top_requested": top_requested,
			"top_used": top_used,
		},
	)
