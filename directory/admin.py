from django.contrib import admin

from .admin_forms import ProviderSettingsAdminForm
from .models import ProviderSettings, ServiceCategory, ServiceProvider


@admin.action(description="Mark selected categories as active")
def mark_categories_active(modeladmin, request, queryset):
	queryset.update(is_active=True)


@admin.action(description="Mark selected categories as inactive")
def mark_categories_inactive(modeladmin, request, queryset):
	queryset.update(is_active=False)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
	list_display = ("name", "slug", "is_active", "sort_order", "created_at", "updated_at")
	list_filter = ("is_active", "created_at", "updated_at")
	search_fields = ("name", "slug")
	list_editable = ("is_active", "sort_order")
	prepopulated_fields = {"slug": ("name",)}
	date_hierarchy = "created_at"
	actions = (mark_categories_active, mark_categories_inactive)
	ordering = ("sort_order", "name")


@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
	list_display = (
		"name",
		"category",
		"city",
		"state",
		"postal_code",
		"is_suggested",
		"suggested_rank",
		"is_active",
	)
	list_filter = ("category", "is_suggested", "is_active", "state")
	search_fields = ("name", "city", "state", "postal_code", "phone", "website")
	ordering = ("-is_suggested", "suggested_rank", "name")


@admin.register(ProviderSettings)
class ProviderSettingsAdmin(admin.ModelAdmin):
	form = ProviderSettingsAdminForm
	list_display = ("provider_backend", "google_region", "updated_at")
	fields = ("provider_backend", "google_maps_api_key", "google_region")

	def has_add_permission(self, request):
		# Enforce singleton row.
		return not ProviderSettings.objects.exists()
