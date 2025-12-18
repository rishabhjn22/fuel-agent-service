# app/agent_controller.py

from typing import Dict, Any
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import root_agent
from . import tools
from .session_store import get_session

APP_NAME = "app"

_session_service = InMemorySessionService()

_runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)

_known_sessions: Dict[str, str] = {}


def _is_amenities_followup(text: str) -> bool:
    """
    Check if this is a follow-up question about amenities for the current station.
    Returns True for: "Is parking available?", "What about food?", "Showers?"
    Returns False for: "Find fuel with parking", "Search for truck stops"
    """
    text = text.lower()
    
    amenity_keywords = ["parking", "park", "shower", "showers", "food", "amenities", "amenity"]
    has_amenity_keyword = any(k in text for k in amenity_keywords)
    
    if not has_amenity_keyword:
        return False
    
    # If user wants to FIND/SEARCH for NEW stations, not a follow-up
    # Check for action words that indicate a new search
    search_words = ["find", "search", "look", "get", "show", "where", "which", "locate"]
    has_search_word = any(w in text for w in search_words)
    
    if has_search_word:
        return False  # This is a new search request, not a follow-up
    
    # It's a follow-up about amenities for current station
    # e.g., "Is parking available?", "What about showers?", "Any food?"
    return True


async def _ensure_session(user_id: str) -> str:
    if user_id in _known_sessions:
        return _known_sessions[user_id]

    session = await _session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=user_id,  # stable per user
    )
    _known_sessions[user_id] = session.id
    return session.id


async def process_message(
    user_id: str,
    user_text: str,
    latitude: float,
    longitude: float,
) -> str:
    """
    Process user message with conversational context.
    """

    session_id = await _ensure_session(user_id)
    memory = get_session(user_id)

    print(f"🧠 MEMORY for user: {user_id}")
    print(f"   last_stations: {memory.get('last_stations') is not None}")

    # ------------------------------------------------------------------
    # 🔁 FOLLOW-UP: parking / shower / food for CURRENT station
    # ------------------------------------------------------------------
    if _is_amenities_followup(user_text):
        stations = memory.get("last_stations")

        if not stations:
            return "Search for a fuel station first."

        # Always use the station from the previous search (maintain context)
        station = stations[0]

        # Check if this station supports real-time amenities
        if not station.get("location_cd"):
            return f"{station['name']} does not have amenities info available."

        # Fetch amenities for the SAME station user was shown
        details = tools.get_amenities_details(
            location_id=station["location_id"],
            location_cd=station["location_cd"],
        )

        # Build response based on what user asked
        text_lower = user_text.lower()
        station_name = station['name']
        
        if "food" in text_lower:
            food_info = details.get("food_options", "No food info")
            return f"**{station_name}**\nFood: {food_info}"
        
        if "shower" in text_lower:
            showers = details.get("showers", {}).get("available", "?")
            return f"**{station_name}**\nShowers: {showers} available"
        
        if "parking" in text_lower or "park" in text_lower:
            parking = details.get("parking", {})
            return f"**{station_name}**\nParking: {parking.get('available', '?')} spots available"
        
        # Generic amenities response
        parking = details.get("parking", {})
        showers = details.get("showers", {})
        food = details.get("food_options", "N/A")

        return (
            f"**{station_name}**\n"
            f"Parking: {parking.get('available', '?')} spots\n"
            f"Showers: {showers.get('available', '?')}\n"
            f"Food: {food}"
        )

    # ------------------------------------------------------------------
    # 🧠 NORMAL FLOW (CALL GEMINI)
    # ------------------------------------------------------------------

    # Clear tool buffer before calling (ensures fresh capture)
    tools.clear_last_call_results()

    prompt_text = (
        f"User GPS: ({latitude}, {longitude})\n"
        f"User Query: {user_text}\n"
        "IMPORTANT:\n"
        "- Return only ONE fuel station (the best match).\n"
        "- Do NOT ask follow-up questions unless required.\n"
    )

    content = types.Content(
        role="user",
        parts=[types.Part(text=prompt_text)],
    )

    events = _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    )

    final_text = ""
    stations_found = None

    async for event in events:
        # Capture tool results from function response parts
        if event.content and event.content.parts:
            for part in event.content.parts:
                # Check for function_response in the part (ADK tool result)
                if hasattr(part, "function_response") and part.function_response:
                    fn_response = part.function_response
                    # Get the response data
                    response_data = None
                    if hasattr(fn_response, "response"):
                        response_data = fn_response.response
                    elif isinstance(fn_response, dict):
                        response_data = fn_response.get("response")

                    # Check if this is station data from search_amenities
                    if isinstance(response_data, list) and response_data:
                        first_item = response_data[0]
                        if isinstance(first_item, dict) and "name" in first_item and "location_id" in first_item:
                            stations_found = response_data
                            print(f"✅ Captured {len(stations_found)} stations from event")

        if event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        final_text = part.text
                        break

    # ------------------------------------------------------------------
    # 💾 STORE LAST STATIONS FOR FOLLOW-UPS
    # ------------------------------------------------------------------
    # Try event-captured stations first, fall back to tool buffer
    if not stations_found:
        fallback_results = tools.get_last_call_results()
        if fallback_results:
            stations_found = fallback_results
            print(f"🔄 Using fallback: captured {len(stations_found)} stations from tool buffer")

    if stations_found:
        memory["last_stations"] = stations_found
        print(f"💾 Stored {len(stations_found)} stations in session memory for user {user_id}")

    return final_text or "Sorry, I couldn't find an answer this time."
