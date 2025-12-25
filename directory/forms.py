"""Forms for dashboard search and profile updates."""

from django import forms

from .models import ServiceCategory


class LocationForm(forms.Form):
    city = forms.CharField(max_length=80, required=False)
    state = forms.CharField(max_length=80, required=False, label="Province/State")
    postal_code = forms.CharField(max_length=20, required=False, label="Postal code")

    # Optional: populated by browser geolocation (public search).
    latitude = forms.CharField(required=False, widget=forms.HiddenInput())
    longitude = forms.CharField(required=False, widget=forms.HiddenInput())


class ServiceSearchForm(forms.Form):
    service_category = forms.ModelChoiceField(
        queryset=ServiceCategory.objects.filter(is_active=True),
        required=False,
        empty_label="All services",
    )
    query = forms.CharField(
        max_length=120,
        required=False,
        label="Search",
        widget=forms.TextInput(attrs={"placeholder": "plumber, mechanic, locksmith…"}),
    )
