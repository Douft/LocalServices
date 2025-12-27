from __future__ import annotations

from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from analyticsapp.models import SearchEvent, UsageAction, UsageEvent


@staff_member_required
def reports(request):
	cutoff = timezone.now() - timedelta(days=30)

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

	# Visitor metrics (best-effort): we only reliably know unique signed-in users.
	search_events_all = SearchEvent.objects.all()
	usage_events_all = UsageEvent.objects.all()
	search_events_30 = search_events_all.filter(created_at__gte=cutoff)
	usage_events_30 = usage_events_all.filter(created_at__gte=cutoff)

	unique_search_users_all = search_events_all.exclude(user__isnull=True).values("user_id").distinct().count()
	unique_usage_users_all = usage_events_all.exclude(user__isnull=True).values("user_id").distinct().count()
	unique_search_users_30 = search_events_30.exclude(user__isnull=True).values("user_id").distinct().count()
	unique_usage_users_30 = usage_events_30.exclude(user__isnull=True).values("user_id").distinct().count()

	# Combined unique signed-in users across both event tables.
	user_ids_all = set(search_events_all.exclude(user__isnull=True).values_list("user_id", flat=True).distinct())
	user_ids_all.update(usage_events_all.exclude(user__isnull=True).values_list("user_id", flat=True).distinct())
	unique_users_all = len(user_ids_all)

	user_ids_30 = set(search_events_30.exclude(user__isnull=True).values_list("user_id", flat=True).distinct())
	user_ids_30.update(usage_events_30.exclude(user__isnull=True).values_list("user_id", flat=True).distinct())
	unique_users_30 = len(user_ids_30)

	search_events_count_all = search_events_all.count()
	usage_events_count_all = usage_events_all.count()
	search_events_count_30 = search_events_30.count()
	usage_events_count_30 = usage_events_30.count()

	# Location insights (based on SearchEvent; these reflect user-entered or geo-derived values).
	top_states_all = (
		search_events_all.exclude(state="")
		.values("state")
		.annotate(total=Count("id"))
		.order_by("-total")[:10]
	)
	top_states_30 = (
		search_events_30.exclude(state="")
		.values("state")
		.annotate(total=Count("id"))
		.order_by("-total")[:10]
	)

	top_cities_all = (
		search_events_all.exclude(city="").exclude(state="")
		.values("city", "state")
		.annotate(total=Count("id"))
		.order_by("-total")[:10]
	)
	top_cities_30 = (
		search_events_30.exclude(city="").exclude(state="")
		.values("city", "state")
		.annotate(total=Count("id"))
		.order_by("-total")[:10]
	)

	top_postal_all = (
		search_events_all.exclude(postal_code="")
		.values("postal_code")
		.annotate(total=Count("id"))
		.order_by("-total")[:10]
	)
	top_postal_30 = (
		search_events_30.exclude(postal_code="")
		.values("postal_code")
		.annotate(total=Count("id"))
		.order_by("-total")[:10]
	)

	return render(
		request,
		"admin/reports.html",
		{
			"top_requested": top_requested,
			"top_used": top_used,
			"unique_users_all": unique_users_all,
			"unique_users_30": unique_users_30,
			"unique_search_users_all": unique_search_users_all,
			"unique_usage_users_all": unique_usage_users_all,
			"unique_search_users_30": unique_search_users_30,
			"unique_usage_users_30": unique_usage_users_30,
			"search_events_count_all": search_events_count_all,
			"usage_events_count_all": usage_events_count_all,
			"search_events_count_30": search_events_count_30,
			"usage_events_count_30": usage_events_count_30,
			"top_states_all": top_states_all,
			"top_states_30": top_states_30,
			"top_cities_all": top_cities_all,
			"top_cities_30": top_cities_30,
			"top_postal_all": top_postal_all,
			"top_postal_30": top_postal_30,
		},
	)
