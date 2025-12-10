# app/main.py
import uvicorn
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware

from .agent_controller import process_message

app = FastAPI(title="FuelFinder ADK Agent")

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
    response_text = await process_message(user_id, text, latitude, longitude)
    return {"response": response_text}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
