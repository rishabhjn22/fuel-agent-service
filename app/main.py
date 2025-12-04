import os
import uuid
import shutil
import uvicorn
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from typing import Optional

from agents.transcriber_agent import TranscriberAgent
from .agent_controller import process_user_query

app = FastAPI(title="FuelFinder Gemini Agent")

# 1. CORS (Allow Mobile Access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. MOUNT STATIC AUDIO FOLDER
AUDIO_DIR = "/tmp/gen_ai_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=AUDIO_DIR), name="static")

# 3. WHISPER SETUP
# We add fp16=False inside the agent class, ensuring no warnings
transcriber = TranscriberAgent(model_name="tiny")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/agent-query")
async def agent_query(
    latitude: float = Form(...),
    longitude: float = Form(...),
    userId: str = Form(...),
    radius: int = Form(200),
    audio: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
):
    query_text = text
    temp_path = None
    
    # 1. Transcribe Audio
    if audio:
        try:
            suffix = os.path.splitext(audio.filename)[1] or ".wav"
            temp_name = f"{uuid.uuid4().hex}{suffix}"
            temp_path = os.path.join(AUDIO_DIR, temp_name)
            
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(audio.file, f)
            
            # Transcribe (The agent class should handle fp16=False)
            query_text = transcriber.run(temp_path)
            print(f"🎤 User said: {query_text}")
            
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "Transcription failed", "detail": str(e)})
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    if not query_text or query_text.strip() == "":
        return JSONResponse(status_code=400, content={"error": "No audio or text provided"})

    # 2. Run Agent
    try:
        result = await process_user_query(query_text, latitude, longitude, userId, radius)
        result["user_query"] = query_text
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": "Agent failed", "detail": str(e)})

if __name__ == "__main__":
    # HOST 0.0.0.0 IS CRITICAL FOR MOBILE ACCESS
    uvicorn.run(app, host="0.0.0.0", port=8000)