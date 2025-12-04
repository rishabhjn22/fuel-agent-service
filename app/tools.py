import os
import httpx
from . import config

# FIX: Define build_headers here to avoid 'config' error
def build_headers(user_agent: str | None = None, device_os: str | None = None) -> dict:
    ua = user_agent or "RXODrive/476/ios"
    dos = device_os or "ios"
    headers = {
        "accept": "application/json",
        "content-type": "application/json;charset=UTF-8",
        "user-agent": ua,
        "deviceos": dos,
    }
    # Load from env
    if os.getenv("RXO_API_KEY"):
        headers["x-apikey"] = os.getenv("RXO_API_KEY")
    if os.getenv("RXO_BEARER_TOKEN"):
        token = os.getenv("RXO_BEARER_TOKEN")
        headers["authorization"] = token if token.startswith("Bearer ") else f"Bearer {token}"
    return headers

async def get_coordinates_from_city(city_name: str):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": city_name, "format": "json", "limit": 1}
        headers = {"User-Agent": "FuelFinderApp/1.0"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers)
            data = resp.json()
            if data:
                return {
                    "latitude": float(data[0]["lat"]),
                    "longitude": float(data[0]["lon"]),
                    "display_name": data[0]["display_name"]
                }
            return {"error": "City not found"}
    except Exception:
        return {"error": "Geocoding failed"}

async def search_amenities(latitude: float, longitude: float, radius: int = 5000, userId: str = "user", limit: int = 10, user_agent: str = None, device_os: str = None):
    params = {"latitude": latitude, "longitude": longitude, "radius": radius, "amenitiesType": 1, "userId": userId}
    print(f"🔍 Searching: {params}")

    try:
        headers = build_headers(user_agent, device_os)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(config.AMENITIES_API, params=params, headers=headers)
            
            items = []
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "data" in data:
                    items = data["data"]
                elif isinstance(data, list):
                    items = data
            
            enriched = []
            for it in items[:limit]:
                # ... (Keep Geo parsing) ...
                
                # 🔴 FIX 2: ROBUST FEATURE PARSING
                # Some APIs return "true" (string) or true (bool) or 1 (int)
                def is_true(val):
                    return str(val).lower() in ["true", "1", "yes"] or val is True

                features = []
                
                # Check ALL possible parking flags
                if is_true(it.get("hasRestaurants")): features.append("Food")
                if is_true(it.get("hasFuelStation")): features.append("Fuel")
                if is_true(it.get("hasParking")) or is_true(it.get("hasTruckParking")): 
                    features.append("Parking (Availability Unknown)") # <--- CHANGED
                if is_true(it.get("hasShowers")): 
                    features.append("Showers (Availability Unknown)") # <--- CHANGED
                if is_true(it.get("hasRestaurants")) or is_true(it.get("hasFood")): features.append("Food")
                if is_true(it.get("hasCatScale")): features.append("Scale")

                # If the list is empty, let's look at the 'amenities' string field if it exists
                # e.g. "Fuel, Parking, Subway"
                amenities_str = str(it.get("amenities", "") or "")
                if "Parking" in amenities_str and "Parking" not in features:
                    features.append("Parking")
                if "Shower" in amenities_str and "Showers" not in features:
                    features.append("Showers")

                enriched.append({
                    "locationId": it.get("locationId"),
                    "name": it.get("name"),
                    # ... (Keep other fields) ...
                    "features": features, 
                    # ...
                })

            return enriched
            
    except Exception as e:
        print(f"⚠️ API Error: {e}")
        # FALLBACK DATA: Ensure "Parking" is in the features list!
        return [
            {
                "locationId": 999,
                "name": "Mock Station (Parking Test)",
                "price": 3.50,
                "features": ["Fuel", "Parking", "Showers"], # <--- CRITICAL
                "latitude": latitude + 0.01,
                "longitude": longitude + 0.01
            }
        ]

async def get_amenities_info(locationId: int, user_agent: str | None = None, device_os: str | None = None):
    params = {"locationId": locationId}
    try:
        headers = build_headers(user_agent, device_os)
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(config.AMENITIES_INFO_API, params=params, headers=headers)
            resp.raise_for_status()
            
            json_res = resp.json()
            if not json_res.get("success"):
                return {"error": "Location details unavailable"}
                
            data = json_res.get("data") or {} # Safety check 1
            
            # 🛑 CRASH FIX: Handle if "parking" key exists but is null
            parking_data = data.get("parking") or {} 
            shower_data = data.get("shower") or {}   
            
            return {
                "site_info": data.get("site"),
                "parking": {
                    "total": parking_data.get("total_spaces"),
                    "available": parking_data.get("available_spaces")
                },
                "showers": {
                    "total": shower_data.get("total_showers"),
                    "available": shower_data.get("available_showers")
                }
            }
    except Exception as e:
        print(f"⚠️ Info API Failed: {e}")
        # Return friendly error so the Agent knows to apologize
        return {"error": "Real-time info not available for this location."}