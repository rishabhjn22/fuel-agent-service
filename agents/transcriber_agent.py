import whisper
import os

class TranscriberAgent:
    def __init__(self, model_name: str = "tiny"):
        # 'tiny' is fast, 'base' is better accuracy. 
        # If running on CPU, sticking to tiny/base is good.
        self.model = whisper.load_model(model_name)

    def run(self, audio_path: str) -> str:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # transcribing
        result = self.model.transcribe(audio_path)
        return result["text"]