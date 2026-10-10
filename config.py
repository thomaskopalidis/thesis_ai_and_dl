import os
from pathlib import Path

# Αυτόματος εντοπισμός και φόρτωση του .env αρχείου αν υπάρχει η βιβλιοθήκη python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

# Server Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
DOMAIN = os.getenv("DOMAIN", "physics")

# STT (Whisper) Settings — auto-detect device if not specified.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")


def _auto_whisper_device() -> str:
    """Return 'cuda' only if a CUDA-enabled torch build is available and sees a device."""
    try:
        import torch  # local import to avoid loading torch at module import if unused
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


WHISPER_DEVICE = os.getenv("WHISPER_DEVICE") or _auto_whisper_device()
# LLM (Ollama) Settings
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# TTS Settings
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-JennyNeural")


# Execution & SSH Server Settings
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "LOCAL") # LOCAL ή REMOTE_SSH
REMOTE_GPU_URL = os.getenv("REMOTE_GPU_URL", "http://localhost:8001")

# Paths — single source of truth for all modules.
# Keep the folder name consistent with what exists on disk (Knowledge_base)
# so this works identically on Windows and Linux (cluster).
BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_DIR = BASE_DIR / "Knowledge_base"
KNOWLEDGE_BASE_FILE = KNOWLEDGE_BASE_DIR / "physics_kb.txt"
CHROMA_DB_DIR = BASE_DIR / "chroma_db"
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "physics_kb")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", 3))
RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Avatar (SadTalker) Settings
AVATAR_IMAGE_PATH = os.getenv("AVATAR_IMAGE_PATH", str(BASE_DIR / "frontend" / "assets" / "teacher_avatar.jpg"))


# Wav2Lip (lip-sync) settings
WAV2LIP_DIR = os.getenv("WAV2LIP_DIR", str(BASE_DIR / "Wav2Lip"))
WAV2LIP_CHECKPOINT = os.getenv("WAV2LIP_CHECKPOINT", str(BASE_DIR / "Wav2Lip" / "checkpoints" / "wav2lip_gan.pth"))
