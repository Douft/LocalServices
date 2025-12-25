from django.contrib import admin

from .models import SearchEvent, UsageEvent


@admin.register(SearchEvent)
class SearchEventAdmin(admin.ModelAdmin):
	list_display = ("created_at", "user", "service_category", "query_text", "postal_code", "city", "state")
	list_filter = ("service_category", "state")
	search_fields = ("query_text", "postal_code", "city", "state")
	date_hierarchy = "created_at"
	readonly_fields = [f.name for f in SearchEvent._meta.fields]


@admin.register(UsageEvent)
class UsageEventAdmin(admin.ModelAdmin):
	list_display = ("created_at", "action", "user", "service_category", "provider", "postal_code", "city", "state")
	list_filter = ("action", "service_category", "state")
	search_fields = ("provider__name", "postal_code", "city", "state")
	date_hierarchy = "created_at"
	readonly_fields = [f.name for f in UsageEvent._meta.fields]
