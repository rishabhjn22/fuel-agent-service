# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from .agent_controller import process_message
from .voice_handler import transcribe_audio, text_to_speech
import base64

app = FastAPI(title="FuelFinder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    user_id: str
    latitude: float
    longitude: float
    text: Optional[str] = None
    audio_base64: Optional[str] = None
    voice_response: bool = False


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Unified chat endpoint - accepts JSON with text or base64 audio.
    """
    input_text = None
    transcription = None
    
    # Handle audio input
    if request.audio_base64:
        print(f"🎤 Received audio ({len(request.audio_base64)} base64 chars)")
        try:
            audio_bytes = base64.b64decode(request.audio_base64)
            print(f"🎤 Decoded: {len(audio_bytes)} bytes")
            
            transcription = await transcribe_audio(audio_bytes, "recording.wav")
            input_text = transcription
            print(f"🎤 Transcribed: {transcription}")
        except Exception as e:
            print(f"❌ Audio processing error: {e}")
            return JSONResponse(content={
                "response": "Sorry, I couldn't process the audio. Please try again.",
                "transcription": None,
                "audio": None,
            })
    
    # Handle text input
    elif request.text:
        input_text = request.text
        print(f"💬 Text: {input_text}")
    
    # No valid input
    if not input_text or not input_text.strip():
        return JSONResponse(content={
            "response": "Sorry, I couldn't understand. Please try again.",
            "transcription": transcription,
            "audio": None,
        })
    
    # Process with agent
    response_text = await process_message(
        request.user_id,
        input_text,
        request.latitude,
        request.longitude,
    )
    print(f"🤖 Response: {response_text}")
    
    result = {
        "response": response_text,
        "transcription": transcription,
        "audio": None,
    }
    
    # Generate voice response if requested
    if request.voice_response:
        try:
            tts_bytes = await text_to_speech(response_text)
            result["audio"] = base64.b64encode(tts_bytes).decode("utf-8")
            print(f"🔊 TTS generated: {len(result['audio'])} chars")
        except Exception as e:
            print(f"❌ TTS error: {e}")
    
    return JSONResponse(content=result)
