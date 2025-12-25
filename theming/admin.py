from django.contrib import admin

from .forms import ThemeSettingsAdminForm
from .models import ThemeSettings


@admin.register(ThemeSettings)
class ThemeSettingsAdmin(admin.ModelAdmin):
	form = ThemeSettingsAdminForm
	list_display = (
		"color_scheme",
		"dark_mode",
		"glass_effect",
		"background_gradients",
		"compact_layout",
		"snow_effect",
		"updated_at",
	)
	fields = ("color_scheme", "dark_mode", "glass_effect", "background_gradients", "compact_layout", "snow_effect")

	def has_add_permission(self, request):
		# Enforce singleton row.
		return not ThemeSettings.objects.exists()

	class Media:
		css = {
			"all": ("theming/admin_theme.css",)
		}
