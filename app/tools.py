# app/tools.py
import math
import time
import httpx
from typing import List
from . import config

DEFAULT_RADIUS_METERS = 321869  # ~200 miles

# -----------------------------------------------------------------------------
# LAST SEARCH RESULTS STORAGE (for follow-up queries)
# -----------------------------------------------------------------------------
_last_call_results: List[dict] | None = None


def get_last_call_results() -> List[dict] | None:
    """Get results from the most recent search_amenities call."""
    return _last_call_results


def clear_last_call_results() -> None:
    """Clear the last call results buffer."""
    global _last_call_results
    _last_call_results = None


# -----------------------------------------------------------------------------
# TOKEN MANAGEMENT (OAuth)
# -----------------------------------------------------------------------------

_access_token: str | None = None
_token_type: str | None = None
_token_expires_at: float | None = None  # UNIX timestamp


def _fetch_new_token() -> tuple[str | None, str | None, float | None]:
    """
    Call the token API to get a new access token.
    Expected response JSON fields:
      - access_token
      - token_type
      - expires_in (seconds)
    """
    if not config.TOKEN_URL:
        raise ValueError("TOKEN_URL is not set; cannot fetch auth token.")

    # Body required by your token endpoint
    body = {
        "client_id": config.TOKEN_CLIENT_ID,
        "client_secret": config.TOKEN_CLIENT_SECRET,
        "scope": config.TOKEN_SCOPE,
        "grant_type": config.TOKEN_GRANT_TYPE,
    }

    # Basic validation so we fail early if env is misconfigured
    if not all([config.TOKEN_CLIENT_ID, config.TOKEN_CLIENT_SECRET, config.TOKEN_SCOPE]):
        raise ValueError(
            "TOKEN_CLIENT_ID / TOKEN_CLIENT_SECRET / TOKEN_SCOPE must all be set in .env"
        )

    headers = {
        "content-type": "application/json",
    }

    # x-api-key is mandatory for your token API
    if not config.TOKEN_X_API_KEY:
        raise ValueError("TOKEN_X_API_KEY is missing in .env but required for token API.")
    headers["x-api-key"] = config.TOKEN_X_API_KEY

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(config.TOKEN_URL, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            access_token = data.get("access_token")
            token_type = data.get("token_type", "Bearer")
            expires_in = data.get("expires_in", 3600)

            if not access_token:
                raise ValueError(f"Token response missing 'access_token': {data}")

            # expire slightly earlier than real expiry (safety margin)
            expires_at = time.time() + int(expires_in) - 60

            print(
                f"✅ New OAuth token fetched (type={token_type}, "
                f"expires_in={expires_in}s)"
            )
            return access_token, token_type, expires_at

    except Exception as e:
        print(f"⚠️ Failed to fetch auth token: {e}")
        return None, None, None


def get_auth_token() -> tuple[str | None, str | None]:
    """
    Return a valid (access_token, token_type), using cached token when not expired.
    """
    global _access_token, _token_type, _token_expires_at

    now = time.time()
    if _access_token and _token_expires_at and now < _token_expires_at:
        return _access_token, _token_type

    access_token, token_type, expires_at = _fetch_new_token()
    if not access_token:
        return None, None

    _access_token = access_token
    _token_type = token_type or "Bearer"
    _token_expires_at = expires_at
    return _access_token, _token_type


# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------

def _calculate_distance(lat1, lon1, lat2, lon2):
    """
    Haversine distance in miles. Returns large number on invalid input.
    """
    if any(x is None for x in [lat1, lon1, lat2, lon2]):
        return 9999.0
    try:
        R = 3958.8
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(R * c, 2)
    except Exception:
        return 9999.0


def _build_headers() -> dict:
    """
    Build headers for AMENITIES / AMENITIES_INFO calls.

    - Uses OAuth token from TOKEN_URL (no RXO_BEARER_TOKEN fallback).
    - Requires RXO_API_KEY for x-apikey.
    """
    headers: dict = {
        "accept": "application/json",
        "content-type": "application/json",
        "user-agent": "FuelFinder/4.0",
        "deviceos": "web",
    }

    if not config.RXO_API_KEY:
        raise ValueError("RXO_API_KEY is missing in .env but required for amenities APIs.")
    headers["x-apikey"] = config.RXO_API_KEY

    access_token, token_type = get_auth_token()
    if not access_token:
        raise ValueError("Failed to get OAuth token; cannot call amenities APIs.")

    headers["authorization"] = f"{token_type or 'Bearer'} {access_token}"
    return headers


def _parse_station_data(
    item: dict, user_lat: float, user_lon: float, amenities_requested: bool
) -> dict:
    """
    Normalize a raw amenities-item into a compact object the agents can use.
    """
    # Coordinates
    station_lat, station_lon = None, None
    geo_str = item.get("locationGeo")
    if geo_str and "," in geo_str:
        try:
            parts = geo_str.split(",")
            station_lat = float(parts[0])
            station_lon = float(parts[1])
        except Exception:
            pass

    dist = _calculate_distance(user_lat, user_lon, station_lat, station_lon)

    # Real-time capability
    loc_cd = item.get("locationCd")
    has_realtime = bool(loc_cd)

    features = []
    next_step = "Basic fuel station."

    if amenities_requested:
        if has_realtime:
            features.append("Real-time Amenities (Parking/Food)")
            next_step = (
                f"**RECOMMENDED**: Call get_amenities_details("
                f"location_id={item.get('locationId')}, location_cd=\"{loc_cd}\")"
            )
        else:
            next_step = "No real-time amenities data available for this station."
    else:
        if has_realtime:
            features.append("Real-time amenities available")
            next_step = "Optional: Call get_amenities_details if user asks for specifics."

    return {
        "name": item.get("name"),
        # critical: pass IDs to higher-level agents
        "location_id": item.get("locationId"),
        "location_cd": loc_cd,
        "is_priority": has_realtime,
        "distance_miles": dist,
        "location": f"{item.get('city')}, {item.get('state')}",
        "financials": {
            "driver_price": f"${(item.get('customerPrice') or 0):.2f}",
            "savings": f"${(item.get('savings') or 0):.2f}",
        },
        "features": ", ".join(features),
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={station_lat},{station_lon}",
        "NEXT_STEP": next_step,
    }


# -----------------------------------------------------------------------------
# PUBLIC TOOLS (used by agents)
# -----------------------------------------------------------------------------

def get_coordinates_from_city(city_name: str) -> dict:
    """
    Convert a city name to latitude/longitude using Nominatim.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city_name, "format": "json", "limit": 1}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                url, params=params, headers={"User-Agent": "FuelFinder/4.0"}
            )
            if resp.status_code == 200 and resp.json():
                data = resp.json()[0]
                return {
                    "latitude": float(data["lat"]),
                    "longitude": float(data["lon"]),
                    "display_name": data["display_name"],
                }
            return {"error": f"City '{city_name}' not found."}
    except Exception as e:
        return {"error": f"Geocoding error: {str(e)}"}


def search_amenities(
    latitude: float,
    longitude: float,
    radius: int = DEFAULT_RADIUS_METERS,
    amenities_required: bool = False,
) -> list[dict]:
    """
    Search nearby stations.

    amenities_required:
      - True  -> prioritize real-time truck stops
      - False -> nearest by distance
    """
    global _last_call_results

    print(
        f"\n🔎 TOOL CALL: search_amenities ({latitude}, {longitude}) | "
        f"Amenities Required: {amenities_required}"
    )

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "radius": radius,
        "amenitiesType": 1,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                config.AMENITIES_API,
                params=params,
                headers=_build_headers(),
            )
            if resp.status_code != 200:
                print("⚠️ AMENITIES_API HTTP", resp.status_code, resp.text)
                return [{"error": "External AMENITIES_API unavailable."}]

            data = resp.json()
            items = data.get("data", []) if isinstance(data, dict) else data

            results = [
                _parse_station_data(item, latitude, longitude, amenities_required)
                for item in items
            ]

            if amenities_required:
                results.sort(key=lambda x: (not x["is_priority"], x["distance_miles"]))
                print("✅ Mode: PRIORITY (real-time truck stops first)")
            else:
                results.sort(key=lambda x: x["distance_miles"])
                print("✅ Mode: NEAREST (distance only)")

            # Return only top 1 station
            final_results = results[:1]

            # Store in module-level buffer for controller fallback
            _last_call_results = final_results
            print(f"💾 Stored {len(final_results)} station(s) in tool buffer")

            return final_results

    except Exception as e:
        print("⚠️ search_amenities exception:", e)
        return [{"error": str(e)}]


def get_amenities_details(location_id: int, location_cd: str | None = None) -> dict:
    """
    Fetch real-time amenities for one station.
    """
    if not location_cd or not str(location_cd).strip():
        return {"status": "Unavailable", "reason": "Missing Code"}

    val_to_send = str(location_cd)
    if len(val_to_send) > 3:
        val_to_send = val_to_send[1:]

    print(f"🔍 Checking Details | Code: {val_to_send}")
    params = {"locationId": val_to_send}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                config.AMENITIES_INFO_API,
                params=params,
                headers=_build_headers(),
            )
            if resp.status_code != 200:
                print("⚠️ AMENITIES_INFO_API HTTP", resp.status_code, resp.text)
                return {"error": "Real-time system offline."}

            data = resp.json().get("data") or {}

            return {
                "location_id": location_id,
                "food_options": data.get("site", "No food info listed."),
                "parking": {
                    "total": data.get("parking", {}).get("total_spaces", "?"),
                    "available": data.get("parking", {}).get("available_spaces", "?"),
                    "reserved_available": data.get("reserve_it", {}).get(
                        "available_spaces", 0
                    ),
                },
                "showers": {
                    "available": data.get("shower", {}).get(
                        "available_showers", "?"
                    )
                },
            }
    except Exception as e:
        print("⚠️ get_amenities_details exception:", e)
        return {"error": "Real-time system offline."}
