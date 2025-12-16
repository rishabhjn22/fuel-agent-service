# app/session_store.py
from typing import Dict, Any
import time

SESSIONS: Dict[str, Dict[str, Any]] = {}

SESSION_TTL = 30 * 60  # 30 minutes


def get_session(user_id: str) -> Dict[str, Any]:
    now = time.time()

    session = SESSIONS.get(user_id)
    if not session:
        session = {
            "last_city": None,
            "last_coordinates": None,
            "last_stations": None,
            "updated_at": now,
        }
        SESSIONS[user_id] = session
        return session

    # expire old session
    if now - session["updated_at"] > SESSION_TTL:
        session.clear()
        session.update(
            {
                "last_city": None,
                "last_coordinates": None,
                "last_stations": None,
                "updated_at": now,
            }
        )

    session["updated_at"] = now
    return session
