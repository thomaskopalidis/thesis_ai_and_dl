FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# ── System packages ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    wget \
    build-essential \
    cmake \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# ── Ollama binary ─────────────────────────────────────────────────────────────
RUN curl -fsSL https://github.com/ollama/ollama/releases/download/v0.6.5/ollama-linux-amd64 \
    -o /usr/local/bin/ollama && chmod +x /usr/local/bin/ollama

# ── Python: core app deps ─────────────────────────────────────────────────────
RUN pip install --no-cache-dir \
    fastapi "uvicorn[standard]" websockets \
    edge-tts \
    faster-whisper \
    chromadb sentence-transformers \
    requests pillow python-dotenv \
    "numpy<2" scipy tqdm \
    librosa numba resampy soundfile \
    "opencv-python-headless==4.10.0.84" \
    ollama

# ── Python: Chatterbox TTS (optional) ────────────────────────────────────────
RUN pip install --no-cache-dir chatterbox-tts || echo "[WARN] chatterbox-tts not available"

# ── Python: Wav2Lip deps ──────────────────────────────────────────────────────
RUN pip install --no-cache-dir \
    face_alignment \
    imageio imageio-ffmpeg \
    pydub

# ── App code (includes Wav2Lip/ subdir with checkpoint) ──────────────────────
WORKDIR /app/physics_tutor
# Copy everything except venv, __pycache__, etc. (see .dockerignore)
COPY . .

# Patch Wav2Lip audio.py for new librosa API (sr= keyword)
RUN sed -i \
    's/librosa\.filters\.mel(hp\.sample_rate,/librosa.filters.mel(sr=hp.sample_rate,/g' \
    /app/physics_tutor/Wav2Lip/audio.py && \
    sed -i 's/, hp\.n_fft,/, n_fft=hp.n_fft,/g' \
    /app/physics_tutor/Wav2Lip/audio.py && \
    echo "Wav2Lip audio.py patched"

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# ── Environment ───────────────────────────────────────────────────────────────
ENV PYTHONPATH="/app/physics_tutor:/app/physics_tutor/Wav2Lip:${PYTHONPATH}"
ENV WAV2LIP_DIR="/app/physics_tutor/Wav2Lip"
ENV WAV2LIP_CHECKPOINT="/app/physics_tutor/Wav2Lip/checkpoints/wav2lip_gan.pth"
ENV OLLAMA_URL="http://localhost:11434"
ENV OLLAMA_MODEL="qwen2.5:14b-instruct-q4_K_M"
ENV OLLAMA_MODELS="/models/ollama"
ENV AVATAR_IMAGE_PATH="/app/physics_tutor/frontend/assets/teacher_avatar.jpg"
ENV WHISPER_DEVICE="cuda"
ENV WHISPER_MODEL="small"

EXPOSE 8000
ENTRYPOINT ["/docker-entrypoint.sh"]
