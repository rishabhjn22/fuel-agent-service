# main.py
import uvicorn
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware

from .agent_controller import process_message

app = FastAPI(title="FuelFinder ADK Agent")

# 1. Allow calls from your mobile / web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat")
async def chat_endpoint(
    text: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    user_id: str = Form(...),
):
    """
    HTTP endpoint that forwards a single chat turn to the ADK agent runner.
    """
    print(f"📩 User {user_id} says: {text}")

    response_text = await process_message(
        user_id=user_id,
        user_text=text,
        latitude=latitude,
        longitude=longitude,
    )

    print(f"🤖 Reply to {user_id}: {response_text}")

    return {"response": response_text}


if __name__ == "__main__":
    # Run local dev server
    print("🚀 Starting Server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
