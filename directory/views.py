"""Public-facing views for the service directory."""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from functools import lru_cache

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce, Replace, Trim, Upper
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.views.decorators.http import require_GET

from accounts.models import UserProfile
from analyticsapp.models import SearchEvent, UsageAction, UsageEvent

from .forms import LocationForm, ServiceSearchForm
from .models import ServiceCategory, ServiceProvider
from .provider_backends import ProviderBackendError, get_provider_backend


def _haversine_km(*, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	"""Great-circle distance in kilometers."""
	R = 6371.0
	phi1 = math.radians(lat1)
	phi2 = math.radians(lat2)
	dphi = math.radians(lat2 - lat1)
	dlambda = math.radians(lon2 - lon1)
	a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
	c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
	return R * c


def _sort_local_by_distance(*, providers: list[ServiceProvider], user_lat: float | None, user_lon: float | None) -> list[ServiceProvider]:
	if user_lat is None or user_lon is None:
		return providers

	def key(p: ServiceProvider):
		try:
			if p.latitude is None or p.longitude is None:
				return (1, float("inf"), (p.name or "").lower())
			return (
				0,
				_haversine_km(lat1=user_lat, lon1=user_lon, lat2=float(p.latitude), lon2=float(p.longitude)),
				(p.name or "").lower(),
			)
		except Exception:
			return (1, float("inf"), (p.name or "").lower())

	return sorted(providers, key=key)


def _sort_external_by_distance(*, providers: list, user_lat: float | None, user_lon: float | None) -> list:
	if user_lat is None or user_lon is None:
		return providers

	def key(p):
		try:
			lat = getattr(p, "latitude", None)
			lon = getattr(p, "longitude", None)
			if lat is None or lon is None:
				return (1, float("inf"), (getattr(p, "name", "") or "").lower())
			return (
				0,
				_haversine_km(lat1=user_lat, lon1=user_lon, lat2=float(lat), lon2=float(lon)),
				(getattr(p, "name", "") or "").lower(),
			)
		except Exception:
			return (1, float("inf"), (getattr(p, "name", "") or "").lower())

	return sorted(providers, key=key)


def _nominatim_reverse_url() -> str:
	"""Build a Nominatim reverse endpoint URL from settings.

	We keep this derived so deployments that override OSM_NOMINATIM_URL still work.
	"""
	base = getattr(settings, "OSM_NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
	try:
		parts = urllib.parse.urlsplit(str(base))
		# Replace the path with /reverse
		return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/reverse", "", ""))
	except Exception:
		return "https://nominatim.openstreetmap.org/reverse"


@lru_cache(maxsize=256)
def _reverse_geocode_osm(*, lat: float, lon: float) -> tuple[str, str, str]:
	"""Best-effort reverse geocode lat/lon -> (city, state, postal_code).

	Returns empty strings when unavailable.
	"""
	# Nominatim prefers reasonably-rounded coordinates.
	lat_r = round(float(lat), 5)
	lon_r = round(float(lon), 5)
	params = {
		"format": "jsonv2",
		"lat": str(lat_r),
		"lon": str(lon_r),
		"addressdetails": "1",
	}
	url = _nominatim_reverse_url() + "?" + urllib.parse.urlencode(params)

	headers = {
		"Accept": "application/json",
		"User-Agent": getattr(settings, "OSM_USER_AGENT", "local-services") or "local-services",
	}
	req = urllib.request.Request(url, headers=headers, method="GET")
	with urllib.request.urlopen(req, timeout=4) as resp:
		payload = json.loads(resp.read().decode("utf-8") or "{}")

	addr = payload.get("address") or {}
	city = (
		addr.get("city")
		or addr.get("town")
		or addr.get("village")
		or addr.get("hamlet")
		or addr.get("suburb")
		or ""
	)
	state = addr.get("state") or addr.get("province") or addr.get("region") or ""
	postal = addr.get("postcode") or ""
	return str(city).strip(), str(state).strip(), str(postal).strip()


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


def _apply_location_filters(*, providers, postal_code: str, city: str, state: str, prefer_city_state: bool = False):
	pc = (postal_code or "").strip()
	ci = (city or "").strip()
	st = (state or "").strip()

	# When location is auto-derived from coordinates, prefer city/state over postal.
	# Postal codes are frequently missing or format-mismatched in locally-entered DB rows.
	if prefer_city_state and ci and st:
		return providers.filter(city__iexact=ci, state__iexact=st)

	if pc:
		original = providers
		pc_norm = pc.replace(" ", "").upper()
		if pc_norm:
			# Match regardless of spaces/case in DB (e.g. "R5G1J8" vs "R5G 1J8").
			filtered = providers.annotate(_pc_norm=Upper(Replace(F("postal_code"), Value(" "), Value(""))))
			filtered = filtered.filter(_pc_norm=pc_norm)
		else:
			filtered = providers.filter(postal_code__iexact=pc)

		# If postal was derived and yields nothing, fall back to city/state
		# WITHOUT resetting other filters (category/query/etc.).
		if prefer_city_state and ci and st and not filtered.exists():
			return original.filter(city__iexact=ci, state__iexact=st)
		return filtered

	if ci and st:
		return providers.filter(city__iexact=ci, state__iexact=st)
	return providers


def _apply_quality_filters(providers):
	"""Only show listings that are actually actionable.

	We require a name + phone. Website/address are optional.
	"""
	providers = providers.annotate(
		_name_trim=Trim(Coalesce("name", Value(""))),
		_phone_trim=Trim(Coalesce("phone", Value(""))),
	)
	return providers.exclude(_name_trim="").exclude(_phone_trim="")


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

	# When the form is bound (i.e., request.GET present), Django does not apply
	# field initial values. For optional ChoiceFields this can make the first
	# option appear selected (e.g., 10km) even though our intended default is 50km.
	# We normalize incoming GET to include sensible defaults for rendering.
	get_data = request.GET.copy() if request.GET else None
	if get_data is not None:
		if not (get_data.get("radius_km") or "").strip():
			get_data["radius_km"] = "50"
		# If the user is authenticated and didn't provide a location, default to profile.
		if profile:
			if not (get_data.get("postal_code") or "").strip() and (profile.postal_code or "").strip():
				get_data["postal_code"] = (profile.postal_code or "").strip()
			if not (get_data.get("city") or "").strip() and (profile.city or "").strip():
				get_data["city"] = (profile.city or "").strip()
			if not (get_data.get("state") or "").strip() and (profile.state or "").strip():
				get_data["state"] = (profile.state or "").strip()

	search_form = ServiceSearchForm(get_data or None)
	location_form = LocationForm(get_data or None, initial=location_initial)

	providers = ServiceProvider.objects.filter(is_active=True)
	selected_category = None
	query_text = ""
	city = ""
	state = ""
	postal_code = ""
	radius_km = 50
	prefer_city_state = False
	user_lat: float | None = None
	user_lon: float | None = None

	external_providers = []
	external_error = ""
	external_source = ""

	# Determine the effective filter values.
	if search_form.is_valid():
		selected_category = search_form.cleaned_data.get("service_category")
		query_text = (search_form.cleaned_data.get("query") or "").strip()

	rebind_location_form = False
	if location_form.is_valid():
		city = (location_form.cleaned_data.get("city") or "").strip()
		state = (location_form.cleaned_data.get("state") or "").strip()
		postal_code = (location_form.cleaned_data.get("postal_code") or "").strip()
		raw_radius = (location_form.cleaned_data.get("radius_km") or "").strip()
		try:
			radius_km = int(raw_radius or 50)
		except Exception:
			radius_km = 50
		raw_lat = (location_form.cleaned_data.get("latitude") or "").strip()
		raw_lon = (location_form.cleaned_data.get("longitude") or "").strip()
		if raw_lat and raw_lon:
			try:
				user_lat = float(raw_lat)
				user_lon = float(raw_lon)
			except Exception:
				user_lat = None
				user_lon = None
		user_provided_postal = bool((request.GET.get("postal_code") or "").strip())
		user_provided_city_state = bool((request.GET.get("city") or "").strip() and (request.GET.get("state") or "").strip())
		prefer_city_state = bool(raw_lat and raw_lon and not user_provided_postal and not user_provided_city_state)

		# If we have coordinates but no textual location, try to reverse geocode.
		if raw_lat and raw_lon and (not postal_code and not (city and state)):
			try:
				lat = float(raw_lat)
				lon = float(raw_lon)
				geo_city, geo_state, geo_postal = _reverse_geocode_osm(lat=lat, lon=lon)
				city = city or geo_city
				state = state or geo_state
				postal_code = postal_code or geo_postal
				# Update bound form data so the UI shows the inferred location.
				if get_data is not None:
					if city and not (get_data.get("city") or "").strip():
						get_data["city"] = city
						rebind_location_form = True
					if state and not (get_data.get("state") or "").strip():
						get_data["state"] = state
						rebind_location_form = True
					if postal_code and not (get_data.get("postal_code") or "").strip():
						get_data["postal_code"] = postal_code
						rebind_location_form = True
			except Exception:
				pass

	if rebind_location_form and get_data is not None:
		location_form = LocationForm(get_data, initial=location_initial)

	# Default to the logged-in user's saved location (even when no GET was provided).
	if not request.GET and profile:
		if not postal_code and profile.postal_code:
			postal_code = profile.postal_code
		if not (city and state) and profile.city and profile.state:
			city, state = profile.city, profile.state
	# Also default to profile when GET is present but no location was specified.
	if request.GET and profile:
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

	providers = _apply_location_filters(
		providers=providers,
		postal_code=postal_code,
		city=city,
		state=state,
		prefer_city_state=prefer_city_state,
	)

	if query_text:
		providers = providers.filter(
			Q(name__icontains=query_text)
			| Q(description__icontains=query_text)
			| Q(category__name__icontains=query_text)
		)

	providers = _apply_quality_filters(providers)

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

	# Enforce actionable results for external providers too.
	external_providers = [
		p for p in external_providers if (getattr(p, "name", "") or "").strip() and (getattr(p, "phone", "") or "").strip()
	]
	external_providers = _sort_external_by_distance(providers=external_providers, user_lat=user_lat, user_lon=user_lon)

	# Sponsored services always take priority; within each group, show closer results first when possible.
	suggested_qs = providers.filter(is_suggested=True).order_by("suggested_rank", "name")[:50]
	regular_qs = providers.filter(is_suggested=False).order_by("name")[:200]

	suggested_list = list(suggested_qs)
	regular_list = list(regular_qs)

	if user_lat is not None and user_lon is not None:
		# Suggested keeps suggested_rank as the primary sort key.
		suggested_list = sorted(
			suggested_list,
			key=lambda p: (
				p.suggested_rank,
				0 if (p.latitude is not None and p.longitude is not None) else 1,
				_haversine_km(lat1=user_lat, lon1=user_lon, lat2=float(p.latitude), lon2=float(p.longitude))
				if (p.latitude is not None and p.longitude is not None)
				else float("inf"),
				(p.name or "").lower(),
			),
		)
		regular_list = _sort_local_by_distance(providers=regular_list, user_lat=user_lat, user_lon=user_lon)

	suggested = suggested_list[:6]
	regular = regular_list[:30]

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

	get_data = request.GET.copy()
	if not (get_data.get("radius_km") or "").strip():
		get_data["radius_km"] = "50"
	search_form = ServiceSearchForm(get_data)
	location_form = LocationForm(get_data)

	providers = ServiceProvider.objects.filter(is_active=True)
	selected_category = None
	query_text = ""
	city = ""
	state = ""
	postal_code = ""
	radius_km = 50
	prefer_city_state = False
	user_lat: float | None = None
	user_lon: float | None = None

	if search_form.is_valid():
		selected_category = search_form.cleaned_data.get("service_category")
		query_text = (search_form.cleaned_data.get("query") or "").strip()

	if location_form.is_valid():
		city = (location_form.cleaned_data.get("city") or "").strip()
		state = (location_form.cleaned_data.get("state") or "").strip()
		postal_code = (location_form.cleaned_data.get("postal_code") or "").strip()
		raw_lat = (location_form.cleaned_data.get("latitude") or "").strip()
		raw_lon = (location_form.cleaned_data.get("longitude") or "").strip()
		if raw_lat and raw_lon:
			try:
				user_lat = float(raw_lat)
				user_lon = float(raw_lon)
			except Exception:
				user_lat = None
				user_lon = None
		user_provided_postal = bool((request.GET.get("postal_code") or "").strip())
		user_provided_city_state = bool((request.GET.get("city") or "").strip() and (request.GET.get("state") or "").strip())
		prefer_city_state = bool(raw_lat and raw_lon and not user_provided_postal and not user_provided_city_state)
		raw_radius = (location_form.cleaned_data.get("radius_km") or "").strip()
		try:
			radius_km = int(raw_radius or 50)
		except Exception:
			radius_km = 50

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

	providers = _apply_location_filters(
		providers=providers,
		postal_code=postal_code,
		city=city,
		state=state,
		prefer_city_state=prefer_city_state,
	)

	if query_text:
		providers = providers.filter(
			Q(name__icontains=query_text)
			| Q(description__icontains=query_text)
			| Q(category__name__icontains=query_text)
		)

	providers = _apply_quality_filters(providers)

	# Sponsored services always take priority; then closer results.
	suggested_qs = providers.filter(is_suggested=True).order_by("suggested_rank", "name")[:50]
	regular_qs = providers.filter(is_suggested=False).order_by("name")[:200]
	suggested_list = list(suggested_qs)
	regular_list = list(regular_qs)

	if user_lat is not None and user_lon is not None:
		suggested_list = sorted(
			suggested_list,
			key=lambda p: (
				p.suggested_rank,
				0 if (p.latitude is not None and p.longitude is not None) else 1,
				_haversine_km(lat1=user_lat, lon1=user_lon, lat2=float(p.latitude), lon2=float(p.longitude))
				if (p.latitude is not None and p.longitude is not None)
				else float("inf"),
				(p.name or "").lower(),
			),
		)
		regular_list = _sort_local_by_distance(providers=regular_list, user_lat=user_lat, user_lon=user_lon)

	suggested_providers = suggested_list[:6]
	providers = regular_list[:30]

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

	external_providers = [
		p for p in external_providers if (getattr(p, "name", "") or "").strip() and (getattr(p, "phone", "") or "").strip()
	]
	external_providers = _sort_external_by_distance(providers=external_providers, user_lat=user_lat, user_lon=user_lon)

	return render(
		request,
		"directory/_live_results.html",
		{
			"suggested_providers": suggested_providers,
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

		providers = _apply_quality_filters(providers)

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

		external_providers = [
			p for p in external_providers if (getattr(p, "name", "") or "").strip() and (getattr(p, "phone", "") or "").strip()
		]

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
