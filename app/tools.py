# tools.py
import math
import httpx
from . import config

DEFAULT_RADIUS_METERS = 321869  # ~200 miles

# ---------- Helper functions (NOT tools) ----------

def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Internal helper: haversine distance in miles between two lat/lon points.
    """
    if any(x is None for x in [lat1, lon1, lat2, lon2]):
        return 9999.0

    try:
        R = 3958.8  # Earth radius in miles
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
    Internal helper: Build HTTP headers for RXO APIs using env config.
    """
    headers = {
        "accept": "application/json",
        "user-agent": "FuelFinder/4.0",
        "deviceos": "web",
    }
    if config.RXO_API_KEY:
        headers["x-apikey"] = config.RXO_API_KEY
    if config.RXO_BEARER_TOKEN:
        token = config.RXO_BEARER_TOKEN
        headers["authorization"] = (
            token if token.startswith("Bearer ") else f"Bearer {token}"
        )
    return headers


def _parse_station_data(
    item: dict, user_lat: float, user_lon: float, amenities_requested: bool
) -> dict:
    """
    Internal helper: normalize one station into a compact JSON object.
    Handles priority sorting and "next step" recommendation text.
    """
    # 1. Parse station coordinates & distance
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

    # 2. Real-time capability flag
    loc_cd = item.get("locationCd")
    has_realtime = bool(loc_cd)

    # 3. Basic “features” + next step hint
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
            next_step = "No real-time amenities data for this station."
    else:
        if has_realtime:
            features.append("Real-time amenities available")
            next_step = (
                "Optional: Call get_amenities_details if user asks for specifics."
            )

    return {
        "name": item.get("name"),
        "is_priority": has_realtime,  # used later for sorting
        "distance_miles": dist,
        "location": f"{item.get('city')}, {item.get('state')}",
        "financials": {
            "driver_price": f"${(item.get('customerPrice') or 0):.2f}",
            "savings": f"${(item.get('savings') or 0):.2f}",
        },
        "features": ", ".join(features),
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={station_lat},{station_lon}",
        "NEXT_STEP": next_step,
        "id": item.get("locationId"),
    }


# ---------- ADK Function Tools (these 3 are exposed to the Agent) ----------

def get_coordinates_from_city(city_name: str) -> dict:
    """
    Convert a city name to GPS coordinates.

    Use this when the user mentions a city like "Chicago" instead of giving
    raw latitude/longitude. Returns:
      - latitude (float)
      - longitude (float)
      - display_name (string)
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
    Search for nearby fuel stations around the given GPS point.

    ALWAYS pass the coordinates that should be the search center:
    - If the user says "near me" or "here", use their GPS.
    - If they say a city, first call get_coordinates_from_city().

    Args:
      latitude: center latitude
      longitude: center longitude
      radius: search radius in meters (default ~200 miles)
      amenities_required:
        - True  -> prioritize truck stops with real-time parking/food/showers
        - False -> prioritize pure distance / closest stations

    Returns a SHORT list (max 5) of normalized station dictionaries
    that the LLM can summarize for the user.
    """
    print(
        f"🔎 TOOL CALL: search_amenities ({latitude}, {longitude}) | "
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
            resp = client.get(config.AMENITIES_API, params=params, headers=_build_headers())
            if resp.status_code != 200:
                return [{"error": "External AMENITIES_API unavailable."}]

            data = resp.json()
            items = data.get("data", []) if isinstance(data, dict) else data

            results = [
                _parse_station_data(item, latitude, longitude, amenities_required)
                for item in items
            ]

            if amenities_required:
                # Sort: 1) stations with real-time data first  2) then by distance
                results.sort(key=lambda x: (not x["is_priority"], x["distance_miles"]))
                print("✅ Mode: PRIORITY (truck stops with real-time data first)")
            else:
                # Sort purely by distance
                results.sort(key=lambda x: x["distance_miles"])
                print("✅ Mode: NEAREST (distance first)")

            return results[:5]
    except Exception as e:
        return [{"error": f"search_amenities failed: {str(e)}"}]


def get_amenities_details(location_id: int, location_cd: str | None = None) -> dict:
    """
    Fetch real-time amenities info for a specific station.

    Use this AFTER search_amenities when you want details like:
      - parking total / available / reserved
      - shower availability
      - food text description

    Args:
      location_id: the station ID from search_amenities() results
      location_cd: internal location code required by the external API

    Returns a dict with food_options, parking, and showers data.
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
                config.AMENITIES_INFO_API, params=params, headers=_build_headers()
            )
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
    except Exception:
        return {"error": "Real-time system offline."}
