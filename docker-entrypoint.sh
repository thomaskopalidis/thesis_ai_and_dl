#!/bin/bash

echo "=== Physics Tutor Startup ==="

# ── 1. Verify Wav2Lip checkpoint ──────────────────────────────────────────────
WAV2LIP_CKPT="${WAV2LIP_CHECKPOINT:-/app/physics_tutor/Wav2Lip/checkpoints/wav2lip_gan.pth}"
if [ -f "$WAV2LIP_CKPT" ]; then
    echo "[Wav2Lip] Checkpoint OK: $WAV2LIP_CKPT"
else
    echo "[Wav2Lip] WARNING: checkpoint not found at $WAV2LIP_CKPT"
    echo "[Wav2Lip] Wav2Lip lipsync will be disabled until checkpoint is provided."
fi

# ── 2. Start Ollama server ────────────────────────────────────────────────────
OLLAMA_MODELS_DIR="${OLLAMA_MODELS:-/models/ollama}"
mkdir -p "$OLLAMA_MODELS_DIR"
echo "[Ollama] Starting server (models dir: $OLLAMA_MODELS_DIR)..."
OLLAMA_MODELS="$OLLAMA_MODELS_DIR" ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!

# Wait up to 30s for Ollama to be ready
for i in $(seq 1 15); do
    if curl -sf http://localhost:11434/api/version > /dev/null 2>&1; then
        echo "[Ollama] Server ready (${i}s)."
        break
    fi
    sleep 2
done

if ! curl -sf http://localhost:11434/api/version > /dev/null 2>&1; then
    echo "[Ollama] WARNING: server not responding. Check /tmp/ollama.log"
    cat /tmp/ollama.log | tail -5
fi

# ── 3. Pull Ollama model if not present ──────────────────────────────────────
MODEL="${OLLAMA_MODEL:-qwen2.5:14b-instruct-q4_K_M}"
echo "[Ollama] Checking model: $MODEL"
if OLLAMA_MODELS="$OLLAMA_MODELS_DIR" ollama list 2>/dev/null | grep -q "${MODEL%%:*}"; then
    echo "[Ollama] Model already available."
else
    echo "[Ollama] Pulling $MODEL in background (first run only)..."
    OLLAMA_MODELS="$OLLAMA_MODELS_DIR" ollama pull "$MODEL" > /tmp/pull.log 2>&1 &
    echo "[Ollama] Pull started (PID $!). Monitor: tail -f /tmp/pull.log"
    echo "[Ollama] App will start now — LLM responses available once pull completes."
fi

# ── 4. Start app ──────────────────────────────────────────────────────────────
echo "[App] Starting physics tutor on port 8000..."
cd /app/physics_tutor
exec python3 app.py
