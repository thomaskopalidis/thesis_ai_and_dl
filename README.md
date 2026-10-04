# Real-Time AI Physics Tutor

An end-to-end, real-time AI-powered physics tutoring system with voice input, LLM-driven responses, text-to-speech, and lip-synced avatar video output. Built as an MSc Thesis project.

---

## Architecture Overview

```
Browser (mic / text)
        │
        ▼  WebSocket  (/ws/chat)
┌───────────────────────────────────────────────────┐
│                   FastAPI Backend                 │
│                                                   │
│  STT (Whisper)  →  LLM (Ollama)  →  TTS (Edge)   │
│                                        │          │
│                              ┌─────────┴────────┐ │
│                              │  Lip-Sync Engine │ │
│                              │  Wav2Lip (fast)  │ │
│                              │  MuseTalk        │ │
│                              │  SadTalker       │ │
│                              └──────────────────┘ │
└───────────────────────────────────────────────────┘
        │
        ▼  video_chunk / audio_chunk (base64, WebSocket)
Browser (avatar video + chat transcript)
```

### Pipeline per sentence

1. **STT** — user audio (WebM) → ffmpeg → WAV 16 kHz → faster-whisper → transcript
2. **RAG** — transcript → ChromaDB vector search → relevant physics KB passages
3. **LLM** — transcript + context → Ollama (streaming) → token stream
4. **TTS** — sentence boundary → edge-tts → raw WAV bytes
5. **Lip-Sync** — WAV → Wav2Lip / MuseTalk / SadTalker → MP4 bytes → browser
6. **Playback** — browser queues and plays MP4 clips sequentially in circular avatar

---

## Technology Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Real-time transport | WebSocket (native browser API) |
| Speech-to-Text | faster-whisper (OpenAI Whisper, local) |
| Audio conversion | FFmpeg |
| LLM | Ollama — `qwen2.5:7b` (local) |
| Text-to-Speech | Microsoft Edge TTS (`edge-tts`) |
| RAG | ChromaDB + SentenceTransformers (`all-MiniLM-L6-v2`) |
| Lip-sync (option A) | **Wav2Lip** (fast, ~0.5–1s/sentence) |
| Lip-sync (option B) | MuseTalk |
| Lip-sync (option C) | SadTalker |
| Frontend | Vanilla JS + HTML/CSS (no framework) |
| Deployment | Kubernetes (NVIDIA A100 MIG) |

---

## Project Structure

```
Thesis_ai_and_dl/
├── app.py                        # FastAPI app, WebSocket handler, pipeline orchestration
├── config.py                     # Centralised config (env vars + defaults)
├── requirements.txt
├── k8s-physics-tutor.yaml        # Kubernetes deployment for university GPU cluster
│
├── core/
│   ├── stt.py                    # faster-whisper STT wrapper
│   ├── llm.py                    # Ollama streaming LLM wrapper + ConversationHistory
│   ├── tts.py                    # edge-tts async TTS wrapper
│   ├── rag.py                    # ChromaDB RAG retrieval
│   ├── wav2lip_lipsync.py        # Wav2Lip subprocess wrapper (default engine)
│   ├── musictalk_lipsync.py      # MuseTalk singleton pipeline
│   └── sadtalker_lipsync.py      # SadTalker subprocess wrapper
│
├── frontend/
│   ├── index.html                # Single-page UI
│   ├── main.js                   # WebSocket client, audio/video queuing & playback
│   └── assets/
│       └── teacher_avatar.jpg    # Avatar still image
│
├── Knowledge_base/
│   └── physics_kb.txt            # Physics knowledge base for RAG
│
├── Wav2Lip/                      # Cloned Wav2Lip repo
│   └── checkpoints/
│       └── wav2lip_gan.pth       # Wav2Lip GAN checkpoint (33MB)
├── MuseTalk/                     # Cloned MuseTalk repo
└── SadTalker/                    # Cloned SadTalker repo
```

---

## Local Setup & Installation

### Prerequisites

- Python 3.9+
- CUDA-capable GPU (recommended; CPU fallback available)
- [Ollama](https://ollama.com) installed and running locally
- FFmpeg on system PATH

### 1 — Clone the repository

```bash
git clone <your-repo-url>
cd Thesis_ai_and_dl
```

### 2 — Create and activate a virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate
```

### 3 — Install Python dependencies

```bash
pip install fastapi "uvicorn[standard]" edge-tts faster-whisper \
    chromadb sentence-transformers requests pillow \
    "opencv-python-headless==4.10.0.84" "numpy<2" scipy tqdm
```

### 4 — Pull the LLM with Ollama

```bash
# Make sure Ollama is running: ollama serve
ollama pull qwen2.5:7b
```

### 5 — Install Wav2Lip (recommended lip-sync engine)

```bash
git clone https://github.com/Rudrabha/Wav2Lip Wav2Lip
# Download checkpoint:
cd Wav2Lip/checkpoints
curl -L -o wav2lip_gan.pth "https://huggingface.co/numz/wav2lip_studio/resolve/main/Wav2lip/wav2lip_gan.pth"
cd ../..
```

#### Optional: MuseTalk

```bash
git clone https://github.com/TMElyralab/MuseTalk MuseTalk
# Download checkpoints per the MuseTalk README into MuseTalk/models/
```

#### Optional: SadTalker

```bash
git clone https://github.com/OpenTalker/SadTalker SadTalker
# Download .pth checkpoints into SadTalker/checkpoints/
```

### 6 — Configure environment variables (optional)

Create a `.env` file:

```dotenv
WHISPER_MODEL=base          # tiny | base | small | medium | large
WHISPER_DEVICE=cuda         # cuda | cpu
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
TTS_VOICE=en-US-JennyNeural
AVATAR_IMAGE_PATH=frontend/assets/teacher_avatar.jpg
```

### 7 — Run the server

```bash
python app.py
```

Open [http://localhost:8000/app](http://localhost:8000/app) in a browser.

---

## Deployment on University GPU Cluster (SSH + Kubernetes)

The university provides access to an **NVIDIA DGX A100** server via SSH and Kubernetes.
The cluster uses **MIG partitions** (each slice = A100 20GB GPU).

### Prerequisites

- VPN connection to the university network
- SSH credentials (same as VPN)

### Step 1 — Connect to the cluster head node

```bash
ssh uniwai11@10.255.11.254
# Password: (your university password)
```

### Step 2 — Upload your project files

From your local machine, use `scp` or Python `paramiko` to upload the project to the server:

```bash
scp -r app.py config.py core/ frontend/ Knowledge_base/ k8s-physics-tutor.yaml \
    uniwai11@10.255.11.254:/home/uniwai11/physics_tutor/
```

> On Windows with SSL issues, use Python paramiko (see below).

### Step 3 — Deploy to Kubernetes

SSH into the server and apply the deployment:

```bash
kubectl apply -f /home/uniwai11/physics_tutor/k8s-physics-tutor.yaml
```

This creates:
- A **Deployment** (`physics-tutor`) using `pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime`
- A **NodePort Service** on port `30800`
- Requests 1× `nvidia.com/mig-3g.20gb` (20GB A100 MIG slice)

### Step 4 — Copy project files into the running pod

```bash
POD=$(kubectl get pods -l app=physics-tutor -o jsonpath="{.items[0].metadata.name}")

kubectl exec $POD -- mkdir -p /workspace/physics_tutor/core \
    /workspace/physics_tutor/frontend/assets \
    /workspace/physics_tutor/Knowledge_base

kubectl cp app.py $POD:/workspace/physics_tutor/app.py
kubectl cp config.py $POD:/workspace/physics_tutor/config.py
kubectl cp core/llm.py $POD:/workspace/physics_tutor/core/llm.py
kubectl cp core/tts.py $POD:/workspace/physics_tutor/core/tts.py
kubectl cp core/stt.py $POD:/workspace/physics_tutor/core/stt.py
kubectl cp core/rag.py $POD:/workspace/physics_tutor/core/rag.py
kubectl cp core/wav2lip_lipsync.py $POD:/workspace/physics_tutor/core/wav2lip_lipsync.py
kubectl cp frontend/index.html $POD:/workspace/physics_tutor/frontend/index.html
kubectl cp frontend/main.js $POD:/workspace/physics_tutor/frontend/main.js
kubectl cp frontend/assets/teacher_avatar.jpg $POD:/workspace/physics_tutor/frontend/assets/teacher_avatar.jpg
kubectl cp Knowledge_base/physics_kb.txt $POD:/workspace/physics_tutor/Knowledge_base/physics_kb.txt
kubectl exec $POD -- touch /workspace/physics_tutor/core/__init__.py
```

### Step 5 — Install Ollama inside the pod

Since the pod has no `curl`/`wget`, use Python to download the Ollama binary:

```bash
kubectl exec $POD -- python3 -c "
import urllib.request, tarfile, os, stat
url = 'https://github.com/ollama/ollama/releases/download/v0.5.13/ollama-linux-amd64.tgz'
os.makedirs('/tmp/ollama_bin', exist_ok=True)
urllib.request.urlretrieve(url, '/tmp/ollama.tgz')
with tarfile.open('/tmp/ollama.tgz', 'r:gz') as tar:
    tar.extractall('/tmp/ollama_bin')
print('Done')
"

# Start Ollama server and pull model
kubectl exec $POD -- bash -c "
export OLLAMA_MODELS=/tmp/ollama_models
export HOME=/tmp
/tmp/ollama_bin/bin/ollama serve &>/tmp/ollama.log &
sleep 8
/tmp/ollama_bin/bin/ollama pull qwen2.5:7b
echo 'Ollama ready'
"
```

### Step 6 — Access the app via SSH port forwarding

On your **local machine**, run:

```bash
ssh -L 8080:172.29.152.186:8000 -N uniwai11@10.255.11.254
```

> Replace `172.29.152.186` with the current pod IP:
> ```bash
> kubectl get pod $POD -o wide
> ```

Then open in your browser: **http://localhost:8080/app**

### Step 7 — Monitor the app

```bash
# View live logs
kubectl logs -l app=physics-tutor -f

# Check pod status
kubectl get pods -o wide

# Delete and redeploy
kubectl delete deployment physics-tutor
kubectl apply -f k8s-physics-tutor.yaml
```

---

## NumPy Compatibility Patches

SadTalker uses deprecated NumPy APIs. The following files were patched:

**`SadTalker/src/face3d/util/my_awing_arch.py` line 18:**
```python
# Before:
preds = preds.astype(np.float, copy=False)
# After:
preds = preds.astype(float, copy=False)
```

**`SadTalker/src/face3d/util/preprocess.py` line 101:**
```python
# Before:
trans_params = np.array([w0, h0, s, t[0], t[1]])
# After:
trans_params = np.array([w0, h0, s, float(t[0]), float(t[1])])
```

**`venv/lib/site-packages/basicsr/data/degradations.py` line 8:**
```python
# Before:
from torchvision.transforms.functional_tensor import rgb_to_grayscale
# After:
from torchvision.transforms.functional import rgb_to_grayscale
```

---

## How to Use

| Action | How |
|---|---|
| Text question | Type in the input box and press **Send** or **Enter** |
| Voice question | Hold **Hold to Speak**, release when done |
| Enable avatar video | Toggle **Avatar mode** switch |
| Switch lip-sync engine | Select **Wav2Lip**, **MuseTalk**, or **SadTalker** from the dropdown |
| Clear conversation | Click **Clear history** |

The avatar dropdown is disabled when Avatar mode is off; enable Avatar mode first, then pick the engine.

---

## Development Process

### Phase 1 — Core voice pipeline
- FastAPI WebSocket endpoint + faster-whisper STT + Ollama LLM + edge-tts TTS

### Phase 2 — Real-time sentence streaming
- Sentence-boundary detection on LLM token stream (punctuation + 80-char cap)
- Each sentence independently TTS-encoded and dispatched without waiting for full response

### Phase 3 — Wav2Lip lip-sync
- First lip-sync engine: fast (~0.5–1s/sentence), subprocess-based
- Checkpoint: `wav2lip_gan.pth` (33MB)

### Phase 4 — MuseTalk integration
- Higher quality, diffusion-based lip sync
- Singleton pattern for weight caching across sentences

### Phase 5 — SadTalker integration
- 3DMM-based talking head with head motion
- NumPy 1.x compatibility patches applied to SadTalker source

### Phase 6 — RAG with ChromaDB
- Physics knowledge base indexed at startup with `all-MiniLM-L6-v2` embeddings
- Top-3 passages retrieved per query and injected into LLM system prompt

### Phase 7 — Conversation history & summarisation
- `ConversationHistory` class with sliding window of 10 exchanges
- Auto-summarisation when history exceeds 20 messages (uses LLM to compress)

### Phase 8 — Kubernetes deployment (university A100 cluster)
- Deployed to DGX002 node with 16× MIG 3g.20gb partitions (A100 20GB each)
- No root access — all installation done via `pip install --user` and Python `urllib`
- Port forwarding via SSH for browser access

---

## Timing Benchmarks

### Local (GTX 1650, 4GB VRAM)

| Stage | Typical latency |
|---|---|
| STT (Whisper base) | ~0.5 s |
| LLM first token (qwen2.5:7b) | ~2–5 s |
| TTS per sentence | ~1 s |
| Wav2Lip per sentence | ~0.5–1 s |
| SadTalker per sentence | ~8–15 s |

### University Cluster (A100 20GB MIG)

| Stage | Typical latency |
|---|---|
| STT (Whisper base) | ~0.1 s |
| LLM first token (qwen2.5:7b) | ~0.3–0.5 s |
| TTS per sentence | ~0.5 s |
| Wav2Lip per sentence | ~0.3–0.5 s |

---

## License

This project was developed for academic research purposes as part of an MSc thesis. Third-party components (Wav2Lip, MuseTalk, SadTalker, Whisper, Ollama) are subject to their own licenses.
