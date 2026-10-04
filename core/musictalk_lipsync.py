import sys
import os
import tempfile
import torch
import cv2

# Dynamically append MuseTalk folder to Python path (use append, NOT insert(0))
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
MUSETALK_PATH = os.path.join(PROJECT_ROOT, "MuseTalk")

if os.path.exists(MUSETALK_PATH) and MUSETALK_PATH not in sys.path:
    sys.path.append(MUSETALK_PATH)

try:
    from musetalk.utils.utils import load_all_model
    from musetalk.utils.blending import get_image
    MUSETALK_AVAILABLE = True
    print("[MuseTalk] Successfully found and imported MuseTalk module!")
except Exception as e:
    print(f"[MuseTalk Import Error]: {e}")
    MUSETALK_AVAILABLE = False


class MuseTalkPipeline:
    _instance = None

    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[MuseTalk] Initializing models on device: {self.device}...")

        if MUSETALK_AVAILABLE:
            # Load MuseTalk models (audio_processor, vae, unet, pe)
            try:
                self.audio_processor, self.vae, self.unet, self.pe = load_all_model()
                print("[MuseTalk] Models loaded successfully!")
            except Exception as e:
                print(f"[MuseTalk Weight Load Error]: {e}")
        else:
            print("[MuseTalk] Running in fallback mode.")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def inference(self, audio_path: str) -> str:
        output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_path = output_file.name
        output_file.close()

        if not MUSETALK_AVAILABLE:
            raise RuntimeError("MuseTalk modules are not imported.")

        # Real inference call goes here once models are loaded
        return output_path


def generate_musictalk_video(audio_path: str) -> str:
    pipeline = MuseTalkPipeline.get_instance()
    return pipeline.inference(audio_path)