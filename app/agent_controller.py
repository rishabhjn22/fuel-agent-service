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
    text = text.lower()
    return any(
        k in text
        for k in [
            "parking",
            "park",
            "shower",
            "showers",
            "food",
            "amenities",
        ]
    )


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
    ✅ Correct conversational flow
    ✅ Stores last stations
    ✅ Handles follow-ups WITHOUT Gemini
    """

    session_id = await _ensure_session(user_id)
    memory = get_session(user_id)

    # ------------------------------------------------------------------
    # 🔁 FOLLOW-UP: parking / shower / food (NO LLM CALL)
    # ------------------------------------------------------------------
    if _is_amenities_followup(user_text):
        stations = memory.get("last_stations")

        if not stations:
            return "I need to find a fuel station first before checking amenities."

        # Default to nearest / best station
        station = stations[0]

        if not station.get("location_cd"):
            return (
                f"Parking and shower information is not available for "
                f"**{station['name']}**."
            )

        details = tools.get_amenities_details(
            location_id=station["location_id"],
            location_cd=station["location_cd"],
        )

        parking = details.get("parking", {})
        showers = details.get("showers", {})

        return (
            f"Here are the amenities for **{station['name']}**:\n"
            f"• Parking available: {parking.get('available', '?')}\n"
            f"• Showers available: {showers.get('available', '?')}\n"
            f"{station['maps_url']}"
        )

    # ------------------------------------------------------------------
    # 🧠 NORMAL FLOW (CALL GEMINI ONLY WHEN NEEDED)
    # ------------------------------------------------------------------
    prompt_text = (
        f"User GPS: ({latitude}, {longitude})\n"
        f"User Query: {user_text}\n"
        "IMPORTANT:\n"
        "- If you list fuel stations, return them clearly.\n"
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
        if event.is_final_response():
            if event.content and event.content.parts:
                final_text = event.content.parts[0].text

        # 👇 THIS IS CRITICAL
        # Capture search results directly from tools
        if event.name == "search_amenities" and event.output:
            stations_found = event.output

    # ------------------------------------------------------------------
    # 💾 STORE LAST STATIONS FOR FOLLOW-UPS
    # ------------------------------------------------------------------
    if stations_found:
        memory["last_stations"] = stations_found

    return final_text or "Sorry, I couldn’t find an answer this time."
