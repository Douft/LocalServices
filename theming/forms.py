from __future__ import annotations

from django import forms

from .models import ThemeSettings


class ThemeSettingsAdminForm(forms.ModelForm):
	class Meta:
		model = ThemeSettings
		fields = (
			"color_scheme",
			"glass_effect",
			"background_gradients",
			"compact_layout",
			"snow_effect",
			"rain_effect",
		)
		widgets = {
			"color_scheme": forms.RadioSelect,
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["color_scheme"].label = "Color templates"
		self.fields["color_scheme"].help_text = "Pick one template (only one can be active)."
