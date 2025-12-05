# tools.py
import httpx
import math
import config

DEFAULT_RADIUS_METERS = 321869 

# --- HELPER FUNCTIONS ---
def _calculate_distance(lat1, lon1, lat2, lon2):
    if any(x is None for x in [lat1, lon1, lat2, lon2]): return 9999.0
    try:
        R = 3958.8 
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) * math.sin(dlon / 2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(R * c, 2)
    except: return 9999.0

def _build_headers() -> dict:
    headers = {
        "accept": "application/json",
        "user-agent": "FuelFinder/4.0",
        "deviceos": "web",
    }
    if config.RXO_API_KEY: headers["x-apikey"] = config.RXO_API_KEY
    if config.RXO_BEARER_TOKEN: token = config.RXO_BEARER_TOKEN; headers["authorization"] = token if token.startswith("Bearer ") else f"Bearer {token}"
    return headers

def _parse_station_data(item: dict, user_lat: float, user_lon: float, amenities_requested: bool) -> dict:
    """
    Parses station data. 
    Crucial: Determines if this station is a 'Priority' match based on user intent.
    """
    # 1. Location & Distance
    station_lat, station_lon = None, None
    geo_str = item.get("locationGeo")
    if geo_str and "," in geo_str:
        try: parts = geo_str.split(","); station_lat, station_lon = float(parts[0]), float(parts[1])
        except: pass
    
    dist = _calculate_distance(user_lat, user_lon, station_lat, station_lon)
    
    # 2. Identify Real-time Capability (Code Presence)
    loc_cd = item.get("locationCd")
    has_realtime = bool(loc_cd)

    # 3. Logic: Should we hint to check details?
    features = []
    next_step = "Basic Fuel Station."
    
    # If the user explicitly asked for amenities (parking/food), ONLY hint if we have real-time data.
    if amenities_requested:
        if has_realtime:
            features.append("Real-time Amenities (Parking/Food)")
            next_step = f"**RECOMMENDED**: Call get_amenities_details(location_id={item.get('locationId')}, location_cd=\"{loc_cd}\")"
        else:
            next_step = "No real-time data available for this station."
    else:
        # If user didn't ask, we don't nag them about details unless it's a huge deal.
        if has_realtime:
            features.append("Real-time Amenities Available")
            next_step = "Optional: Call get_amenities_details if user asks for specifics."

    return {
        "name": item.get("name"),
        "is_priority": has_realtime, # Tag for sorting later
        "distance_miles": dist,
        "location": f"{item.get('city')}, {item.get('state')}",
        "financials": {
            "driver_price": f"${item.get('customerPrice') or 0:.2f}",
            "savings": f"${item.get('savings') or 0:.2f}"
        },
        "features": ", ".join(features),
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={station_lat},{station_lon}",
        "NEXT_STEP": next_step,
        "id": item.get("locationId")
    }

# --- PUBLIC TOOLS ---

def get_coordinates_from_city(city_name: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city_name, "format": "json", "limit": 1}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params, headers={"User-Agent": "FuelFinder/4.0"})
            if resp.status_code == 200 and resp.json():
                data = resp.json()[0]
                return {"latitude": float(data["lat"]), "longitude": float(data["lon"]), "display_name": data["display_name"]}
            return {"error": f"City '{city_name}' not found."}
    except Exception as e: return {"error": f"Geocoding error: {str(e)}"}

def search_amenities(latitude: float, longitude: float, radius: int = DEFAULT_RADIUS_METERS, amenities_required: bool = False):
    """
    Searches for fuel stations.
    
    Args:
        amenities_required (bool): 
            - IF TRUE: Sorts stations with Real-Time Info (Parking/Food) to the TOP.
            - IF FALSE: Sorts purely by Distance (Closest first).
    """
    print(f"\n🔎 TOOL CALL: search_amenities ({latitude}, {longitude}) | Amenities Required: {amenities_required}")
    params = {"latitude": latitude, "longitude": longitude, "radius": radius, "amenitiesType": 1}
    
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(config.AMENITIES_API, params=params, headers=_build_headers())
            if resp.status_code != 200: return {"error": "External API unavailable."}
            data = resp.json(); items = data.get("data", []) if isinstance(data, dict) else data
            
            # Parse all items
            results = [_parse_station_data(item, latitude, longitude, amenities_required) for item in items]
            
            # --- THE TOGGLE LOGIC ---
            if amenities_required:
                # Sort first by Priority (True > False), THEN by Distance
                # 'not x' is used because False < True in Python sort
                results.sort(key=lambda x: (not x["is_priority"], x["distance_miles"]))
                print("✅ Mode: PRIORITY (Truck Stops First)")
            else:
                # Sort purely by distance
                results.sort(key=lambda x: x["distance_miles"])
                print("✅ Mode: NEAREST (Distance First)")
            
            return results[:5]

    except Exception as e: return {"error": str(e)}

def get_amenities_details(location_id: int, location_cd: str = None):
    if not location_cd or not str(location_cd).strip():
        return {"status": "Unavailable", "reason": "Missing Code"}

    val_to_send = str(location_cd)
    if len(val_to_send) > 3: val_to_send = val_to_send[1:]

    print(f"🔍 Checking Details | Code: {val_to_send}")
    params = {"locationId": val_to_send}
    
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(config.AMENITIES_INFO_API, params=params, headers=_build_headers())
            data = resp.json().get("data") or {}
            
            return {
                "location_id": location_id,
                "food_options": data.get("site", "No food info listed."),
                "parking": {
                    "total": data.get("parking", {}).get("total_spaces", "?"),
                    "available": data.get("parking", {}).get("available_spaces", "?"),
                    "reserved_available": data.get("reserve_it", {}).get("available_spaces", 0)
                },
                "showers": {
                    "available": data.get("shower", {}).get("available_showers", "?")
                }
            }
    except Exception as e: return {"error": "Real-time system offline."}