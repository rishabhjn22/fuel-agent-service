# app/agent_controller.py
from typing import Dict

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import root_agent

APP_NAME = "app"  # must match package/folder name

_session_service = InMemorySessionService()
_runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=_session_service)

_known_sessions: Dict[str, str] = {}


async def _ensure_session(user_id: str) -> str:
    """
    Ensure a session exists for this user; create one if needed.
    """
    if user_id in _known_sessions:
        return _known_sessions[user_id]

    session = await _session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=user_id,
    )
    _known_sessions[user_id] = session.id
    print(f"🆕 Created ADK session for user {user_id}: {session.id}")
    return session.id


async def process_message(
    user_id: str, user_text: str, latitude: float, longitude: float
) -> str:
    """
    FastAPI entry point: send one user message into the ADK runner, get text back.
    """
    session_id = await _ensure_session(user_id)

    prompt_text = (
        f"User GPS: ({latitude}, {longitude})\n"
        f"User Query: {user_text}\n"
        "If the user says 'near me' or 'here', treat the GPS above as the search center.\n"
    )

    content = types.Content(role="user", parts=[types.Part(text=prompt_text)])

    events = _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    )

    final_text = ""

    async for event in events:
        if event.is_final_response():
            if event.content and event.content.parts:
                part = event.content.parts[0]
                if getattr(part, "text", None):
                    final_text = part.text

    if not final_text:
        final_text = "Sorry, I couldn't generate a response this time."

    return final_text
