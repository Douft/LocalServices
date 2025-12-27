"""Forms for dashboard search and profile updates."""

from django import forms
from django.db.utils import OperationalError, ProgrammingError

from .models import ServiceCategory


class LocationForm(forms.Form):
    city = forms.CharField(max_length=80, required=False)
    state = forms.CharField(max_length=80, required=False, label="Province/State")
    postal_code = forms.CharField(max_length=20, required=False, label="Postal code")

    radius_km = forms.ChoiceField(
        required=False,
        label="Radius",
        choices=[
            ("10", "10 km"),
            ("25", "25 km"),
            ("50", "50 km"),
            ("100", "100 km"),
            ("500", "500 km"),
        ],
        initial="50",
    )

    # Optional: populated by browser geolocation (public search).
    latitude = forms.CharField(required=False, widget=forms.HiddenInput())
    longitude = forms.CharField(required=False, widget=forms.HiddenInput())


class ServiceSearchForm(forms.Form):
    service_category = forms.ModelChoiceField(
        queryset=ServiceCategory.objects.none(),
        required=False,
        empty_label="All services",
    )
    query = forms.CharField(
        max_length=120,
        required=False,
        label="Search",
        widget=forms.TextInput(
            attrs={
                "placeholder": "plumber, mechanic, locksmith…",
                "autocomplete": "off",
                "autocapitalize": "off",
                "autocorrect": "off",
                "spellcheck": "false",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            # Important: building a QuerySet doesn't hit the DB.
            # We force a tiny evaluation to confirm the table exists.
            qs = ServiceCategory.objects.filter(is_active=True)
            list(qs.values_list("id", flat=True)[:1])
            self.fields["service_category"].queryset = qs
        except (OperationalError, ProgrammingError):
            # Database not migrated yet.
            self.fields["service_category"].queryset = ServiceCategory.objects.none()
