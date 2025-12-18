# main.py
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .agent_controller import process_message

app = FastAPI(title="FuelFinder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    text: str
    latitude: float
    longitude: float
    user_id: str

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/chat")
async def chat(payload: ChatRequest):
    response = await process_message(
        payload.user_id,
        payload.text,
        payload.latitude,
        payload.longitude,
    )
    return {"response": response}
