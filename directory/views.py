"""Public-facing views for the service directory."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import UserProfile
from analyticsapp.models import SearchEvent, UsageAction, UsageEvent

from .forms import LocationForm, ServiceSearchForm
from .models import ServiceProvider
from .provider_backends import ProviderBackendError, get_provider_backend


def home(request):
	"""Landing page.

	For now this is intentionally minimal so you can run locally.
	We'll evolve it into location-based service discovery + ads + SEO.
	"""

	return render(
		request,
		"home.html",
		{
			"search_form": ServiceSearchForm(),
			"location_form": LocationForm(),
		},
	)


def public_search(request):
	"""Public (no-login) search.

	Anonymous users can search by category + query and optionally narrow by
	postal code or city/province.
	"""

	def _reverse_geocode_osm(*, lat: float, lon: float) -> tuple[str, str, str]:
		"""Best-effort reverse geocode via OSM Nominatim.

		Returns (city, state, postal_code).
		"""
		import json
		import urllib.parse
		import urllib.request

		from django.conf import settings

		reverse_url = getattr(settings, "OSM_NOMINATIM_REVERSE_URL", "https://nominatim.openstreetmap.org/reverse")
		params = {
			"format": "jsonv2",
			"lat": str(lat),
			"lon": str(lon),
		}
		contact_email = getattr(settings, "OSM_CONTACT_EMAIL", "")
		if contact_email:
			params["email"] = contact_email

		user_agent = getattr(settings, "OSM_USER_AGENT", "local-services-local-dev")
		url = f"{reverse_url}?{urllib.parse.urlencode(params)}"
		req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"}, method="GET")
		with urllib.request.urlopen(req, timeout=20) as resp:
			raw = resp.read().decode("utf-8")
		payload = json.loads(raw)
		address = payload.get("address") if isinstance(payload, dict) else None
		if not isinstance(address, dict):
			return "", "", ""

		city = str(address.get("city") or address.get("town") or address.get("village") or "").strip()
		state = str(address.get("state") or address.get("province") or "").strip()
		postal_code = str(address.get("postcode") or "").strip()
		return city, state, postal_code

	profile = None
	if request.user.is_authenticated:
		profile, _ = UserProfile.objects.get_or_create(user=request.user)

	location_initial = {}
	if profile:
		location_initial = {
			"city": profile.city,
			"state": profile.state,
			"postal_code": profile.postal_code,
		}

	search_form = ServiceSearchForm(request.GET or None)
	location_form = LocationForm(request.GET or None, initial=location_initial)

	providers = ServiceProvider.objects.filter(is_active=True)
	selected_category = None
	query_text = ""
	city = ""
	state = ""
	postal_code = ""

	external_providers = []
	external_error = ""
	external_source = ""

	# Determine the effective filter values.
	if search_form.is_valid():
		selected_category = search_form.cleaned_data.get("service_category")
		query_text = (search_form.cleaned_data.get("query") or "").strip()

	if location_form.is_valid():
		city = (location_form.cleaned_data.get("city") or "").strip()
		state = (location_form.cleaned_data.get("state") or "").strip()
		postal_code = (location_form.cleaned_data.get("postal_code") or "").strip()
		raw_lat = (location_form.cleaned_data.get("latitude") or "").strip()
		raw_lon = (location_form.cleaned_data.get("longitude") or "").strip()

		# If we have coordinates but no textual location, try to reverse geocode.
		if raw_lat and raw_lon and (not postal_code and not (city and state)):
			try:
				lat = float(raw_lat)
				lon = float(raw_lon)
				geo_city, geo_state, geo_postal = _reverse_geocode_osm(lat=lat, lon=lon)
				city = city or geo_city
				state = state or geo_state
				postal_code = postal_code or geo_postal
			except Exception:
				pass

	# Default to the logged-in user's saved location (even when no GET was provided).
	if not request.GET and profile:
		if not postal_code and profile.postal_code:
			postal_code = profile.postal_code
		if not (city and state) and profile.city and profile.state:
			city, state = profile.city, profile.state

	# Apply filters.
	if selected_category:
		providers = providers.filter(category=selected_category)

	if postal_code:
		providers = providers.filter(postal_code=postal_code)
	elif city and state:
		providers = providers.filter(city__iexact=city, state__iexact=state)

	if query_text:
		providers = providers.filter(name__icontains=query_text)

	# Log searches when the user actually submits/loads query params (including geolocation auto-submit).
	if request.GET:
		SearchEvent.objects.create(
			user=request.user if request.user.is_authenticated else None,
			service_category=selected_category,
			query_text=query_text,
			city=city,
			state=state,
			postal_code=postal_code,
		)

		# External search is only meaningful when we have both category and a location.
		if selected_category and (postal_code or (city and state)):
			try:
				backend = get_provider_backend()
				external_source = getattr(backend, "source_label", "")
				external_providers = backend.search(
					category=selected_category,
					query_text=query_text,
					city=city,
					state=state,
					postal_code=postal_code,
					country="CA",
					radius_km=15,
				)
			except ProviderBackendError as e:
				external_error = str(e)
			except Exception:
				external_error = "External provider search is temporarily unavailable."

	suggested = providers.filter(is_suggested=True).order_by("suggested_rank", "name")[:6]
	regular = providers.filter(is_suggested=False).order_by("name")[:30]

	return render(
		request,
		"directory/public_search.html",
		{
			"location_form": location_form,
			"search_form": search_form,
			"suggested_providers": suggested,
			"providers": regular,
			"external_providers": external_providers,
			"external_error": external_error,
			"external_source": external_source,
		},
	)


@login_required
def dashboard(request):
	"""User dashboard.

	Loads local providers based on the user's saved location.
	Also records SearchEvent ("requested" services) when searches happen.
	"""

	profile, _ = UserProfile.objects.get_or_create(user=request.user)

	if request.method == "POST" and request.POST.get("action") == "update_location":
		location_form = LocationForm(request.POST)
		if location_form.is_valid():
			profile.city = location_form.cleaned_data.get("city", "")
			profile.state = location_form.cleaned_data.get("state", "")
			profile.postal_code = location_form.cleaned_data.get("postal_code", "")
			profile.save()
	else:
		location_form = LocationForm(
			initial={"city": profile.city, "state": profile.state, "postal_code": profile.postal_code}
		)

	search_form = ServiceSearchForm(request.GET or None)

	providers = ServiceProvider.objects.filter(is_active=True)
	selected_category = None
	query_text = ""
	external_providers = []
	external_error = ""
	external_source = ""

	if search_form.is_valid():
		selected_category = search_form.cleaned_data.get("service_category")
		query_text = (search_form.cleaned_data.get("query") or "").strip()

		if selected_category:
			providers = providers.filter(category=selected_category)

		# Simple location match: prefer ZIP; else city/state.
		if profile.postal_code:
			providers = providers.filter(postal_code=profile.postal_code)
		elif profile.city and profile.state:
			providers = providers.filter(city__iexact=profile.city, state__iexact=profile.state)

		if query_text:
			providers = providers.filter(name__icontains=query_text)

		# Log the search (requested services)
		SearchEvent.objects.create(
			user=request.user,
			service_category=selected_category,
			query_text=query_text,
			city=profile.city,
			state=profile.state,
			postal_code=profile.postal_code,
			latitude=profile.latitude,
			longitude=profile.longitude,
		)

		# External search (free-first via OSM). Only run when the user is actively searching.
		if request.GET and selected_category and (profile.postal_code or (profile.city and profile.state)):
			try:
				backend = get_provider_backend()
				external_source = getattr(backend, "source_label", "")
				external_providers = backend.search(
					category=selected_category,
					query_text=query_text,
					city=profile.city,
					state=profile.state,
					postal_code=profile.postal_code,
					country=profile.country or "CA",
					radius_km=profile.default_radius_km,
				)
			except ProviderBackendError as e:
				external_error = str(e)
			except Exception:
				external_error = "External provider search is temporarily unavailable."

	suggested = providers.filter(is_suggested=True).order_by("suggested_rank", "name")[:6]
	regular = providers.filter(is_suggested=False).order_by("name")[:30]

	return render(
		request,
		"directory/dashboard.html",
		{
			"location_form": location_form,
			"search_form": search_form,
			"suggested_providers": suggested,
			"providers": regular,
			"external_providers": external_providers,
			"external_error": external_error,
			"external_source": external_source,
		},
	)


@login_required
def contact_provider(request, provider_id: int):
	"""Log a 'contact' usage event for a provider.

	This does not place a call or send an email; it just records that the
	user intends to contact the provider.
	"""

	if request.method != "POST":
		raise Http404()

	provider = get_object_or_404(ServiceProvider, pk=provider_id, is_active=True)
	profile, _ = UserProfile.objects.get_or_create(user=request.user)

	UsageEvent.objects.create(
		user=request.user,
		service_category=provider.category,
		provider=provider,
		action=UsageAction.CONTACT,
		city=profile.city,
		state=profile.state,
		postal_code=profile.postal_code,
		latitude=profile.latitude,
		longitude=profile.longitude,
	)

	messages.success(request, f"Logged contact for {provider.name}.")
	return redirect("dashboard")


@login_required
def provider_out(request, provider_id: int):
	"""Outbound click tracker.

	Logs a click and then redirects to the provider website.
	"""

	provider = get_object_or_404(ServiceProvider, pk=provider_id, is_active=True)
	if not provider.website:
		raise Http404()

	profile, _ = UserProfile.objects.get_or_create(user=request.user)
	UsageEvent.objects.create(
		user=request.user,
		service_category=provider.category,
		provider=provider,
		action=UsageAction.CLICK_WEBSITE,
		city=profile.city,
		state=profile.state,
		postal_code=profile.postal_code,
		latitude=profile.latitude,
		longitude=profile.longitude,
	)

	return redirect(provider.website)
