from __future__ import annotations

import json
import hashlib
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable, Optional

import urllib.error

from django.conf import settings
from django.core.cache import cache

from directory.models import ProviderBackendChoice, ProviderSettings, ServiceCategory


@dataclass(frozen=True)
class ProviderResult:
    name: str
    category: str
    phone: str = ""
    website: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source: str = ""


class ProviderBackendError(Exception):
    pass


class ProviderBackend:
    source_label: str = ""

    def search(
        self,
        *,
        category: Optional[ServiceCategory],
        query_text: str,
        city: str,
        state: str,
        postal_code: str,
        country: str,
        radius_km: int,
    ) -> list[ProviderResult]:
        raise NotImplementedError


def get_provider_backend() -> ProviderBackend:
    backend = ""
    try:
        backend = (ProviderSettings.get_solo().provider_backend or "").upper()
    except Exception:
        backend = ""

    if not backend:
        backend = getattr(settings, "PROVIDER_BACKEND", ProviderBackendChoice.OSM).upper()

    if backend == "OSM":
        return OSMBackend()
    if backend == "GOOGLE":
        return GooglePlacesBackend()
    raise ProviderBackendError(f"Unknown PROVIDER_BACKEND={backend!r}")


class OSMBackend(ProviderBackend):
    source_label = "OpenStreetMap"
    """Free-ish OpenStreetMap backend.

    Uses Nominatim for geocoding and Overpass for POI search.

    Notes:
    - Respect rate limits.
    - Provide a real User-Agent and contact email in settings.
    - Show attribution (handled in template).
    """

    DEFAULT_RADIUS_KM = 15

    def _cache_key(self, *, prefix: str, payload: dict) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"{prefix}:{digest}"

    def _headers(self) -> dict[str, str]:
        user_agent = getattr(settings, "OSM_USER_AGENT", "local-services-local-dev")
        return {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

    def _http_get_json(self, url: str, *, timeout: int = 20) -> object:
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                return json.loads(raw)
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 502, 503, 504) and attempt == 0:
                    time.sleep(0.6)
                    continue
                raise
            except urllib.error.URLError as e:
                last_err = e
                if attempt == 0:
                    time.sleep(0.6)
                    continue
                raise

        if last_err:
            raise last_err
        raise ProviderBackendError("External provider request failed.")

    def _http_post_form_json(self, url: str, form: dict[str, str], *, timeout: int = 30) -> object:
        data = urllib.parse.urlencode(form).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                return json.loads(raw)
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 502, 503, 504) and attempt == 0:
                    time.sleep(0.8)
                    continue
                raise
            except urllib.error.URLError as e:
                last_err = e
                if attempt == 0:
                    time.sleep(0.8)
                    continue
                raise

        if last_err:
            raise last_err
        raise ProviderBackendError("External provider request failed.")

    def _geocode_postal_via_overpass(self, *, postal_code: str, country: str) -> tuple[Optional[float], Optional[float], str]:
        """Fallback geocode using Overpass when Nominatim can't resolve a postal code.

        For Canada, postal codes are often present on individual OSM objects via
        addr:postcode even if Nominatim doesn't index the code as a place.
        """

        cc = (country or "").strip().upper()
        if cc != "CA":
            return None, None, ""

        pc = self._normalize_postal_code(postal_code, country=country)
        if not pc:
            return None, None, ""

        raw = pc.replace(" ", "")
        if len(raw) != 6:
            return None, None, ""
        # Match both "A1A 1A1" and "A1A1A1".
        regex = f"^{raw[:3]} ?{raw[3:]}$"

        overpass_url = getattr(settings, "OSM_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
        query = (
            "[out:json][timeout:25];"
            "area[\"ISO3166-1\"=\"CA\"][admin_level=2]->.ca;"
            "("
            f"node(area.ca)[\"addr:postcode\"~\"{regex}\"];"
            f"way(area.ca)[\"addr:postcode\"~\"{regex}\"];"
            f"relation(area.ca)[\"addr:postcode\"~\"{regex}\"];"
            ");"
            "out center 1;"
        )

        payload = self._http_post_form_json(overpass_url, {"data": query})
        elements = payload.get("elements") if isinstance(payload, dict) else None
        if not isinstance(elements, list) or not elements:
            return None, None, ""

        el = elements[0]
        if not isinstance(el, dict):
            return None, None, ""

        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            center = el.get("center")
            if isinstance(center, dict):
                lat = center.get("lat")
                lon = center.get("lon")

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return None, None, ""

        return lat_f, lon_f, f"{pc}, Canada"

    def _normalize_postal_code(self, postal_code: str, *, country: str) -> str:
        pc = (postal_code or "").strip()
        if not pc:
            return ""

        # Basic normalization for Canadian postal codes.
        if (country or "").upper() == "CA":
            raw = pc.replace(" ", "").upper()
            # Expected: A1A1A1
            if len(raw) == 6:
                return raw[:3] + " " + raw[3:]
            return raw

        return pc

    def _infer_ca_province_from_postal(self, postal_code: str) -> str:
        raw = (postal_code or "").strip().replace(" ", "").upper()
        if not raw:
            return ""
        first = raw[0]
        mapping = {
            "A": "Newfoundland and Labrador",
            "B": "Nova Scotia",
            "C": "Prince Edward Island",
            "E": "New Brunswick",
            "G": "Quebec",
            "H": "Quebec",
            "J": "Quebec",
            "K": "Ontario",
            "L": "Ontario",
            "M": "Ontario",
            "N": "Ontario",
            "P": "Ontario",
            "R": "Manitoba",
            "S": "Saskatchewan",
            "T": "Alberta",
            "V": "British Columbia",
            "X": "Northwest Territories",
            "Y": "Yukon",
        }
        return mapping.get(first, "")

    def _infer_ca_province_abbrev_from_postal(self, postal_code: str) -> str:
        full = self._infer_ca_province_from_postal(postal_code)
        mapping = {
            "Newfoundland and Labrador": "NL",
            "Nova Scotia": "NS",
            "Prince Edward Island": "PE",
            "New Brunswick": "NB",
            "Quebec": "QC",
            "Ontario": "ON",
            "Manitoba": "MB",
            "Saskatchewan": "SK",
            "Alberta": "AB",
            "British Columbia": "BC",
            "Northwest Territories": "NT",
            "Nunavut": "NU",
            "Yukon": "YT",
        }
        return mapping.get(full, "")

    def _normalize_ca_province(self, state: str) -> str:
        s = (state or "").strip()
        if not s:
            return ""
        sl = s.lower()
        # Common abbreviations and names.
        table = {
            "manitoba": "MB",
            "mb": "MB",
            "ontario": "ON",
            "on": "ON",
            "quebec": "QC",
            "qc": "QC",
            "british columbia": "BC",
            "bc": "BC",
            "alberta": "AB",
            "ab": "AB",
            "saskatchewan": "SK",
            "sk": "SK",
            "new brunswick": "NB",
            "nb": "NB",
            "nova scotia": "NS",
            "ns": "NS",
            "newfoundland and labrador": "NL",
            "nl": "NL",
            "prince edward island": "PE",
            "pe": "PE",
            "northwest territories": "NT",
            "nt": "NT",
            "nunavut": "NU",
            "nu": "NU",
            "yukon": "YT",
            "yt": "YT",
        }
        return table.get(sl, s)

    def _country_display_name(self, country: str) -> str:
        cc = (country or "").strip().upper()
        if cc == "CA":
            return "Canada"
        if cc == "US":
            return "United States"
        return cc

    def _ca_expected_province_full(self, state: str) -> str:
        """Map a Canadian province abbreviation to its full name when possible."""

        ab = self._normalize_ca_province(state)
        mapping = {
            "MB": "Manitoba",
            "ON": "Ontario",
            "QC": "Quebec",
            "BC": "British Columbia",
            "AB": "Alberta",
            "SK": "Saskatchewan",
            "NB": "New Brunswick",
            "NS": "Nova Scotia",
            "NL": "Newfoundland and Labrador",
            "PE": "Prince Edward Island",
            "NT": "Northwest Territories",
            "NU": "Nunavut",
            "YT": "Yukon",
        }
        return mapping.get(ab, state)

    def _pick_best_nominatim_result(
        self,
        payload: object,
        *,
        country: str,
        state: str,
    ) -> tuple[Optional[float], Optional[float], str]:
        if not isinstance(payload, list) or not payload:
            return None, None, ""

        cc = (country or "").strip().lower()
        st = (state or "").strip()

        expected_prov_full = ""
        expected_prov_abbrev = ""
        if cc == "ca" and st:
            expected_prov_abbrev = self._normalize_ca_province(st)
            expected_prov_full = self._ca_expected_province_full(expected_prov_abbrev)

        candidates: list[dict] = [p for p in payload if isinstance(p, dict)]
        for item in candidates:
            address = item.get("address") if isinstance(item.get("address"), dict) else {}

            if cc:
                addr_cc = str(address.get("country_code") or "").strip().lower()
                if not addr_cc or addr_cc != cc:
                    continue

            if cc == "ca" and (expected_prov_full or expected_prov_abbrev):
                addr_state = str(address.get("state") or address.get("province") or "").strip()
                if addr_state:
                    addr_state_norm = self._normalize_ca_province(addr_state)
                    if expected_prov_abbrev and addr_state_norm == expected_prov_abbrev:
                        pass
                    elif expected_prov_full and addr_state.lower() == expected_prov_full.lower():
                        pass
                    else:
                        continue

            try:
                lat = float(item.get("lat"))
                lon = float(item.get("lon"))
            except (TypeError, ValueError):
                continue

            display_name = str(item.get("display_name") or "")
            return lat, lon, display_name

        # If nothing matched constraints, fail closed.
        return None, None, ""

    def _geocode(self, *, city: str, state: str, postal_code: str, country: str) -> tuple[Optional[float], Optional[float], str]:
        nominatim_url = getattr(
            settings,
            "OSM_NOMINATIM_URL",
            "https://nominatim.openstreetmap.org/search",
        )

        cc = (country or "").strip().lower()

        postal_code = self._normalize_postal_code(postal_code, country=country)
        city = (city or "").strip()
        state = (state or "").strip()

        params = {
            "format": "jsonv2",
            "limit": "5",
            "addressdetails": "1",
        }
        if len(cc) == 2:
            params["countrycodes"] = cc

        # Prefer a constrained free-text query for postal codes.
        # (Structured "postalcode=" lookups are unreliable across providers/regions.)
        parts: list[str] = []
        if postal_code:
            parts.append(postal_code)
            if not state and (country or "").upper() == "CA":
                state = self._infer_ca_province_abbrev_from_postal(postal_code) or self._infer_ca_province_from_postal(postal_code)
            elif (country or "").upper() == "CA":
                state = self._normalize_ca_province(state)
        if city:
            parts.append(city)
        if state:
            parts.append(state)
        if country:
            parts.append(self._country_display_name(country))

        q = ", ".join([p for p in parts if p]).strip()
        if not q:
            return None, None, ""
        params["q"] = q
        contact_email = getattr(settings, "OSM_CONTACT_EMAIL", "")
        if contact_email:
            params["email"] = contact_email

        url = f"{nominatim_url}?{urllib.parse.urlencode(params)}"
        payload = self._http_get_json(url)
        lat, lon, display_name = self._pick_best_nominatim_result(payload, country=country, state=state)
        if lat is None or lon is None:
            # Fallback: sometimes adding the full province name helps more than the abbreviation.
            if postal_code and (country or "").upper() == "CA":
                prov_full = self._infer_ca_province_from_postal(postal_code)
                if prov_full and prov_full not in q:
                    params["q"] = f"{postal_code}, {prov_full}, {self._country_display_name(country)}"
                    url = f"{nominatim_url}?{urllib.parse.urlencode(params)}"
                    payload = self._http_get_json(url)
                    lat, lon, display_name = self._pick_best_nominatim_result(payload, country=country, state=prov_full)

            if lat is None or lon is None:
                # Final fallback: use Overpass to locate any object with the postal code.
                if postal_code and (country or "").upper() == "CA" and not city:
                    lat, lon, display = self._geocode_postal_via_overpass(postal_code=postal_code, country=country)
                    if lat is not None and lon is not None:
                        return lat, lon, display

                return None, None, ""

        return lat, lon, display_name

    def _build_overpass_query(
        self,
        *,
        lat: float,
        lon: float,
        radius_m: int,
        tag_groups: Iterable[Iterable[tuple[str, str]]],
    ):
        parts: list[str] = []
        for group in tag_groups:
            tag_filters = "".join([f"[\"{k}\"=\"{v}\"]" for k, v in group])
            parts.append(f"node(around:{radius_m},{lat},{lon}){tag_filters};")
            parts.append(f"way(around:{radius_m},{lat},{lon}){tag_filters};")
            parts.append(f"relation(around:{radius_m},{lat},{lon}){tag_filters};")

        body = "".join(parts)
        return f"[out:json][timeout:25];({body});out center 120;"

    def _category_to_osm_tag_groups(self, category: Optional[ServiceCategory]) -> list[list[tuple[str, str]]]:
        if not category:
            return []
        slug = (category.slug or "").lower()
        name = (category.name or "").lower()

        key = slug or name
        mapping: dict[str, list[list[tuple[str, str]]]] = {
            "plumber": [[("craft", "plumber")]],
            "electrician": [[("craft", "electrician")]],
            "locksmith": [[("craft", "locksmith")]],
            # Mechanics/auto shops are tagged in multiple ways; use OR groups.
            "mechanic": [
                [("shop", "car_repair")],
                [("amenity", "car_repair")],
                [("craft", "car_repair")],
                [("service", "vehicle_repair")],
            ],
            "hvac": [[("craft", "hvac")]],
            "handyman": [[("craft", "handyman")]],
            "appliance-repair": [[("craft", "appliance_repair")]],
            "appliance-repair-1": [[("craft", "appliance_repair")]],
            "appliance-repair-2": [[("craft", "appliance_repair")]],
        }

        # Fallback heuristics
        if "plumb" in key:
            return [[("craft", "plumber")]]
        if "electric" in key:
            return [[("craft", "electrician")]]
        if "lock" in key:
            return [[("craft", "locksmith")]]
        if "mechan" in key or "auto" in key:
            return [
                [("shop", "car_repair")],
                [("amenity", "car_repair")],
                [("craft", "car_repair")],
                [("service", "vehicle_repair")],
            ]
        if "hvac" in key:
            return [[("craft", "hvac")]]

        return mapping.get(key, [])

    def _format_address(self, tags: dict) -> tuple[str, str, str, str, str]:
        house = tags.get("addr:housenumber") or ""
        street = tags.get("addr:street") or ""
        city = tags.get("addr:city") or ""
        state = tags.get("addr:province") or tags.get("addr:state") or ""
        postal_code = tags.get("addr:postcode") or ""

        line1 = " ".join([p for p in [house, street] if p]).strip()
        address = ", ".join([p for p in [line1, city, state, postal_code] if p]).strip(", ")
        return address, city, state, postal_code, ""

    def search(
        self,
        *,
        category: Optional[ServiceCategory],
        query_text: str,
        city: str,
        state: str,
        postal_code: str,
        country: str,
        radius_km: int,
    ) -> list[ProviderResult]:
        tag_groups = self._category_to_osm_tag_groups(category)
        if not tag_groups:
            return []

        radius_km = radius_km or getattr(settings, "OSM_DEFAULT_RADIUS_KM", self.DEFAULT_RADIUS_KM)
        radius_m = int(radius_km) * 1000

        # NOTE: Keep versioned to avoid stale cached wrong locations.
        # Use a hashed key to avoid cache backends (e.g., memcached) rejecting characters.
        cache_key = self._cache_key(
            prefix="osm:v4:providers",
            payload={
                "category": (category.slug if category else "all"),
                "query_text": query_text,
                "city": city,
                "state": state,
                "postal_code": postal_code,
                "country": country,
                "radius_km": int(radius_km),
            },
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        lat, lon, _display = self._geocode(city=city, state=state, postal_code=postal_code, country=country)
        if lat is None or lon is None:
            cache.set(cache_key, [], timeout=60 * 10)
            loc_hint = "city + province" if (country or "").strip().upper() == "CA" else "city/state"
            raise ProviderBackendError(
                f"Couldn't locate that location for external results. Please add {loc_hint} (or allow device location)."
            )

        overpass_url = getattr(
            settings,
            "OSM_OVERPASS_URL",
            "https://overpass-api.de/api/interpreter",
        )

        query = self._build_overpass_query(lat=lat, lon=lon, radius_m=radius_m, tag_groups=tag_groups)
        try:
            payload = self._http_post_form_json(overpass_url, {"data": query})
        except urllib.error.HTTPError as e:
            if getattr(e, "code", None) in (429, 502, 503, 504):
                raise ProviderBackendError("External provider is temporarily busy. Please try again.")
            raise
        except urllib.error.URLError:
            raise ProviderBackendError("External provider is temporarily unavailable.")

        results: list[ProviderResult] = []
        elements = payload.get("elements") if isinstance(payload, dict) else None
        if not isinstance(elements, list):
            cache.set(cache_key, [], timeout=60 * 10)
            return []

        for el in elements[:50]:
            if not isinstance(el, dict):
                continue
            tags_dict = el.get("tags")
            if not isinstance(tags_dict, dict):
                continue

            name = str(tags_dict.get("name") or "").strip()
            if not name:
                continue

            if query_text:
                if query_text.lower() not in name.lower():
                    continue

            phone = str(tags_dict.get("phone") or tags_dict.get("contact:phone") or "").strip()
            website = str(tags_dict.get("website") or tags_dict.get("contact:website") or "").strip()

            address, addr_city, addr_state, addr_postal, _ = self._format_address(tags_dict)

            el_lat = el.get("lat")
            el_lon = el.get("lon")
            if el_lat is None or el_lon is None:
                center = el.get("center")
                if isinstance(center, dict):
                    el_lat = center.get("lat")
                    el_lon = center.get("lon")

            try:
                el_lat_f = float(el_lat) if el_lat is not None else None
                el_lon_f = float(el_lon) if el_lon is not None else None
            except (TypeError, ValueError):
                el_lat_f = None
                el_lon_f = None

            results.append(
                ProviderResult(
                    name=name,
                    category=category.name if category else "",
                    phone=phone,
                    website=website,
                    address=address,
                    city=addr_city,
                    state=addr_state,
                    postal_code=addr_postal,
                    country=country,
                    latitude=el_lat_f,
                    longitude=el_lon_f,
                    source="OSM",
                )
            )

        cache.set(cache_key, results, timeout=60 * 10)
        return results


class GooglePlacesBackend(ProviderBackend):
    """Google Places backend.

    Uses Places Text Search.

    Notes:
    - This is a paid API (pay-as-you-go, with a monthly credit that may change).
    - We do not persist Google results in the DB; we only display them.
    - We avoid Place Details calls by default to keep cost down.
    """

    source_label = "Google Places"

    TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

    def _category_to_expected_types(self, category: Optional[ServiceCategory]) -> set[str]:
        if not category:
            return set()
        slug = (category.slug or "").lower()
        name = (category.name or "").lower()
        key = slug or name

        mapping: dict[str, set[str]] = {
            "plumber": {"plumber"},
            "electrician": {"electrician"},
            "locksmith": {"locksmith"},
            "mechanic": {"car_repair"},
        }

        if "plumb" in key:
            return {"plumber"}
        if "electric" in key:
            return {"electrician"}
        if "lock" in key:
            return {"locksmith"}
        if "mechan" in key or "auto" in key:
            return {"car_repair"}

        return mapping.get(key, set())

    def _is_service_business(self, item: dict, *, expected_types: set[str]) -> bool:
        """Best-effort filter to avoid non-business / irrelevant results."""

        business_status = str(item.get("business_status") or "").strip()
        if business_status and business_status != "OPERATIONAL":
            return False

        raw_types = item.get("types")
        types: list[str] = []
        if isinstance(raw_types, list):
            types = [str(t) for t in raw_types if isinstance(t, (str,))]

        # Exclude common non-business / geocode artifacts.
        blocked = {
            "locality",
            "postal_code",
            "route",
            "political",
            "administrative_area_level_1",
            "administrative_area_level_2",
            "country",
            "point_of_interest",
        }
        if any(t in blocked for t in types):
            return False

        if expected_types:
            return any(t in expected_types for t in types)

        return True

    def _http_get_json(self, url: str, *, timeout: int = 20) -> object:
        req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw)

    def _build_query(self, *, category: Optional[ServiceCategory], query_text: str, location_text: str) -> str:
        parts: list[str] = []
        if category:
            parts.append(category.name)
        if query_text:
            parts.append(query_text)
        if location_text:
            parts.append(f"near {location_text}")
        return " ".join([p.strip() for p in parts if p.strip()]).strip()

    def search(
        self,
        *,
        category: Optional[ServiceCategory],
        query_text: str,
        city: str,
        state: str,
        postal_code: str,
        country: str,
        radius_km: int,
    ) -> list[ProviderResult]:
        api_key = ""
        region_override = ""
        try:
            provider_settings = ProviderSettings.get_solo()
            api_key = (provider_settings.google_maps_api_key or "").strip()
            region_override = (provider_settings.google_region or "").strip()
        except Exception:
            api_key = ""
            region_override = ""

        if not api_key:
            api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
        if not api_key:
            raise ProviderBackendError("GOOGLE_MAPS_API_KEY is not set")

        if not category:
            return []

        location_parts: list[str] = []
        if postal_code:
            location_parts.append(postal_code)
        if city:
            location_parts.append(city)
        if state:
            location_parts.append(state)
        if country:
            location_parts.append(country)
        location_text = ", ".join([p for p in location_parts if p]).strip()

        query = self._build_query(category=category, query_text=query_text, location_text=location_text)
        if not query:
            return []

        cache_key = f"google:textsearch:{category.slug}:{query_text}:{city}:{state}:{postal_code}:{country}".lower()
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        region = (region_override or country or "").strip().lower()
        if len(region) != 2:
            region = "ca"

        params = {
            "query": query,
            "key": api_key,
            "region": region,
            "language": "en",
        }
        url = f"{self.TEXTSEARCH_URL}?{urllib.parse.urlencode(params)}"
        payload = self._http_get_json(url)

        if not isinstance(payload, dict):
            raise ProviderBackendError("Google Places response was not valid JSON")

        status = str(payload.get("status") or "")
        if status in {"ZERO_RESULTS"}:
            cache.set(cache_key, [], timeout=60 * 10)
            return []
        if status not in {"OK"}:
            message = str(payload.get("error_message") or "").strip()
            if message:
                raise ProviderBackendError(f"Google Places error: {status} — {message}")
            raise ProviderBackendError(f"Google Places error: {status}")

        results_list = payload.get("results")
        if not isinstance(results_list, list):
            cache.set(cache_key, [], timeout=60 * 10)
            return []

        results: list[ProviderResult] = []
        expected_types = self._category_to_expected_types(category)
        for item in results_list[:20]:
            if not isinstance(item, dict):
                continue

            if not self._is_service_business(item, expected_types=expected_types):
                continue

            name = str(item.get("name") or "").strip()
            if not name:
                continue
            address = str(item.get("formatted_address") or "").strip()

            lat = None
            lon = None
            geometry = item.get("geometry")
            if isinstance(geometry, dict):
                loc = geometry.get("location")
                if isinstance(loc, dict):
                    try:
                        raw_lat = loc.get("lat")
                        raw_lng = loc.get("lng")

                        if isinstance(raw_lat, (int, float, str)):
                            lat = float(raw_lat)
                        if isinstance(raw_lng, (int, float, str)):
                            lon = float(raw_lng)
                    except (TypeError, ValueError):
                        lat = None
                        lon = None

            results.append(
                ProviderResult(
                    name=name,
                    category=category.name,
                    address=address,
                    city=city,
                    state=state,
                    postal_code=postal_code,
                    country=country,
                    latitude=lat,
                    longitude=lon,
                    source="Google",
                )
            )

        cache.set(cache_key, results, timeout=60 * 10)
        return results
