# app/voice_handler.py
import os
import tempfile
import asyncio
import subprocess

# Whisper model (lazy load)
_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        print("🔄 Loading Whisper model (tiny)...")
        _whisper_model = whisper.load_model("tiny")
        print("✅ Whisper model loaded")
    return _whisper_model


def _convert_to_wav(input_path: str) -> str:
    """
    Convert any audio to 16kHz mono WAV using ffmpeg.
    Returns path to converted file.
    """
    output_path = input_path.rsplit(".", 1)[0] + "_converted.wav"
    
    cmd = [
        "ffmpeg", "-y",  # Overwrite output
        "-i", input_path,  # Input file
        "-ar", "16000",  # 16kHz sample rate (required by Whisper)
        "-ac", "1",  # Mono
        "-c:a", "pcm_s16le",  # 16-bit PCM
        "-f", "wav",  # Output format
        output_path
    ]
    
    print(f"🔄 Converting audio: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode == 0:
            print(f"✅ Converted to: {output_path} ({os.path.getsize(output_path)} bytes)")
            return output_path
        else:
            print(f"❌ ffmpeg error: {result.stderr.decode()}")
            return None
    except Exception as e:
        print(f"❌ Conversion error: {e}")
        return None


def _probe_audio(file_path: str) -> dict:
    """Get audio file info using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except:
        pass
    return {}


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribe audio using local Whisper model (FREE).
    Automatically converts audio to proper format using ffmpeg.
    """
    print(f"🎤 Received audio: {len(audio_bytes)} bytes")
    
    if len(audio_bytes) < 500:
        print(f"⚠️ Audio too short: {len(audio_bytes)} bytes")
        return ""
    
    # Save original file (use .mp4 since that's what Android records)
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(audio_bytes)
        original_path = tmp.name
    
    print(f"📁 Saved original: {original_path} ({os.path.getsize(original_path)} bytes)")
    
    # Probe the audio
    probe_info = _probe_audio(original_path)
    if probe_info:
        streams = probe_info.get("streams", [])
        if streams:
            codec = streams[0].get("codec_name", "unknown")
            duration = streams[0].get("duration", "unknown")
            print(f"📊 Audio info: codec={codec}, duration={duration}s")
    
    converted_path = None
    
    try:
        # Convert to proper WAV format
        converted_path = _convert_to_wav(original_path)
        
        if not converted_path or not os.path.exists(converted_path):
            print("❌ Audio conversion failed")
            return ""
        
        # Check converted file size
        converted_size = os.path.getsize(converted_path)
        if converted_size < 1000:
            print(f"⚠️ Converted file too small: {converted_size} bytes")
            return ""
        
        model = _get_whisper_model()
        
        # Run transcription
        print("🔄 Running Whisper transcription...")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: model.transcribe(converted_path, language="en", fp16=False)
        )
        
        text = result["text"].strip()
        
        if text:
            print(f"✅ Transcribed: '{text}'")
        else:
            print("⚠️ No speech detected")
            
        return text
        
    except Exception as e:
        print(f"❌ Transcription error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return ""
    finally:
        # Cleanup temp files
        for path in [original_path, converted_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except:
                    pass


async def text_to_speech(text: str) -> bytes:
    """
    Convert text to speech using Edge TTS (FREE).
    """
    try:
        import edge_tts
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            communicate = edge_tts.Communicate(text, "en-US-GuyNeural")
            await communicate.save(tmp_path)
            
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()
            
            print(f"🔊 TTS generated: {len(audio_bytes)} bytes")
            return audio_bytes
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except ImportError:
        print("⚠️ edge-tts not installed")
        raise
    except Exception as e:
        print(f"❌ TTS error: {e}")
        raise
