from __future__ import annotations

from django import forms

from .models import ProviderSettings


class ProviderSettingsAdminForm(forms.ModelForm):
	google_maps_api_key = forms.CharField(
		required=False,
		widget=forms.PasswordInput(render_value=True),
		help_text="Stored in the database. Treat it like a secret.",
	)

	class Meta:
		model = ProviderSettings
		fields = ("provider_backend", "google_maps_api_key", "google_region")
