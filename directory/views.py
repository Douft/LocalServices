"""Public-facing views for the service directory."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Value
from django.db.models.functions import Replace, Upper
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from accounts.models import UserProfile
from analyticsapp.models import SearchEvent, UsageAction, UsageEvent

from .forms import LocationForm, ServiceSearchForm
from .models import ServiceCategory, ServiceProvider
from .provider_backends import ProviderBackendError, get_provider_backend


def _has_analytics_consent(request) -> bool:
	"""Return True when user consented to analytics tracking.

	We use a simple cookie set by the front-end consent banner.
	"""
	val = str(request.COOKIES.get("ls_analytics_consent") or "").strip().lower()
	return val in {"1", "true", "yes", "y", "accept", "accepted"}


def _infer_category_from_query(query_text: str) -> tuple[ServiceCategory | None, bool]:
	"""Infer category from a free-text query.

	Returns (category, consume_query). When consume_query is True, the query text
	was interpreted as the category itself (e.g. "plumbing"), so applying a
	name-contains filter would wrongly hide results.
	"""

	qt = (query_text or "").strip()
	if not qt:
		return None, False

	qs = ServiceCategory.objects.filter(is_active=True)

	exact = qs.filter(name__iexact=qt).first()
	if exact:
		return exact, True

	ql = qt.lower()
	keyword_to_slug: list[tuple[str, str]] = [
		("plumb", "plumber"),
		("electric", "electrician"),
		("lock", "locksmith"),
		("mechan", "mechanic"),
		("auto", "mechanic"),
		("hvac", "hvac"),
		("heat", "hvac"),
		("cool", "hvac"),
		("handy", "handyman"),
		("appliance", "appliance-repair"),
		("roof", "roofing"),
		("landscap", "landscaping"),
		("clean", "cleaning"),
		("move", "moving"),
	]
	for key, slug in keyword_to_slug:
		if key in ql:
			cat = qs.filter(slug__iexact=slug).first() or qs.filter(name__iexact=slug.replace("-", " ")).first()
			if cat:
				return cat, True

	# If there's a single obvious match, infer it.
	contains = list(qs.filter(name__icontains=qt).order_by("sort_order", "name")[:2])
	if len(contains) == 1:
		return contains[0], False

	return None, False


def _apply_location_filters(*, providers, postal_code: str, city: str, state: str):
	pc = (postal_code or "").strip()
	if pc:
		pc_norm = pc.replace(" ", "").upper()
		if pc_norm:
			# Match regardless of spaces/case in DB (e.g. "R5G1J8" vs "R5G 1J8").
			providers = providers.annotate(_pc_norm=Upper(Replace("postal_code", Value(" "), Value(""))))
			providers = providers.filter(_pc_norm=pc_norm)
		else:
			providers = providers.filter(postal_code__iexact=pc)
		return providers

	ci = (city or "").strip()
	st = (state or "").strip()
	if ci and st:
		providers = providers.filter(city__iexact=ci, state__iexact=st)
	return providers


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
	radius_km = 100

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
		raw_radius = (location_form.cleaned_data.get("radius_km") or "").strip()
		try:
			radius_km = int(raw_radius or 100)
		except Exception:
			radius_km = 100
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
	had_query = bool(query_text)
	if not selected_category and query_text:
		inferred, consume_query = _infer_category_from_query(query_text)
		if inferred:
			selected_category = inferred
			if consume_query:
				query_text = ""

	if selected_category:
		providers = providers.filter(category=selected_category)

	providers = _apply_location_filters(providers=providers, postal_code=postal_code, city=city, state=state)

	if query_text:
		providers = providers.filter(
			Q(name__icontains=query_text)
			| Q(description__icontains=query_text)
			| Q(category__name__icontains=query_text)
		)

	# Log searches when the user actually submits/loads query params (including geolocation auto-submit).
	if request.GET and _has_analytics_consent(request):
		SearchEvent.objects.create(
			user=request.user if request.user.is_authenticated else None,
			service_category=selected_category,
			query_text=query_text,
			city=city,
			state=state,
			postal_code=postal_code,
		)

		# External search is only meaningful when we have both a category and a location.
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
					radius_km=radius_km,
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


@require_GET
def live_search(request):
	"""Live (AJAX) search results for local providers.

	This endpoint intentionally does NOT log SearchEvent and does not call external
	provider backends (to avoid excessive requests while typing).
	"""

	search_form = ServiceSearchForm(request.GET)
	location_form = LocationForm(request.GET)

	providers = ServiceProvider.objects.filter(is_active=True)
	selected_category = None
	query_text = ""
	city = ""
	state = ""
	postal_code = ""
	radius_km = 100

	if search_form.is_valid():
		selected_category = search_form.cleaned_data.get("service_category")
		query_text = (search_form.cleaned_data.get("query") or "").strip()

	if location_form.is_valid():
		city = (location_form.cleaned_data.get("city") or "").strip()
		state = (location_form.cleaned_data.get("state") or "").strip()
		postal_code = (location_form.cleaned_data.get("postal_code") or "").strip()
		raw_radius = (location_form.cleaned_data.get("radius_km") or "").strip()
		try:
			radius_km = int(raw_radius or 100)
		except Exception:
			radius_km = 100

	had_query = bool(query_text)
	category_explicit = bool(request.GET.get("service_category"))
	if not selected_category and query_text:
		inferred, consume_query = _infer_category_from_query(query_text)
		if inferred:
			selected_category = inferred
			if consume_query:
				query_text = ""

	if selected_category:
		providers = providers.filter(category=selected_category)

	providers = _apply_location_filters(providers=providers, postal_code=postal_code, city=city, state=state)

	if query_text:
		providers = providers.filter(
			Q(name__icontains=query_text)
			| Q(description__icontains=query_text)
			| Q(category__name__icontains=query_text)
		)

	providers = providers.order_by("name")[:12]

	external_providers = []
	external_error = ""
	external_source = ""

	# Optional external results for live search: only when user is actively typing
	# or explicitly selected a category, and location is present.
	if selected_category and (postal_code or (city and state)) and (had_query or category_explicit):
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
				radius_km=radius_km,
			)
		except ProviderBackendError as e:
			external_error = str(e)
		except Exception:
			external_error = "External provider search is temporarily unavailable."

	return render(
		request,
		"directory/_live_results.html",
		{
			"providers": providers,
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

		# Simple location match: prefer postal code; else city/state.
		providers = _apply_location_filters(
			providers=providers,
			postal_code=profile.postal_code,
			city=profile.city,
			state=profile.state,
		)

		if not selected_category and query_text:
			inferred, consume_query = _infer_category_from_query(query_text)
			if inferred:
				selected_category = inferred
				providers = providers.filter(category=selected_category)
				if consume_query:
					query_text = ""

		if query_text:
			providers = providers.filter(
				Q(name__icontains=query_text)
				| Q(description__icontains=query_text)
				| Q(category__name__icontains=query_text)
			)

		# Log the search (requested services) only when user consented.
		if _has_analytics_consent(request):
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

	if _has_analytics_consent(request):
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
	if _has_analytics_consent(request):
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
