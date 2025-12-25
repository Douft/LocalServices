from django.contrib import admin

from .models import AdUnit


@admin.register(AdUnit)
class AdUnitAdmin(admin.ModelAdmin):
    list_display = ("headline", "placement", "is_enabled", "priority", "starts_at", "ends_at")
    list_filter = ("placement", "is_enabled")
    search_fields = ("headline", "body", "target_url")
    ordering = ("placement", "priority", "-created_at")
