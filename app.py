import sys, os
# Ensure user-installed packages (/tmp/.local) are visible on the K8s pod where
# pip --user is written there. Harmless on Windows (path simply does not exist).
if sys.platform.startswith("linux"):
    _user_site = "/tmp/.local/lib/python3.10/site-packages"
    if _user_site not in sys.path and os.path.isdir(_user_site):
        sys.path.insert(0, _user_site)

import base64
import json
import time
import tempfile
import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config

# Modules built in previous steps
from core.llm import stream_llm_response, ConversationHistory, list_ollama_models
from core.tts import text_to_speech_stream
from core.stt import transcribe_audio
from core.rag import retrieve

def _load_tts_engines():
    engines = {"edge": text_to_speech_stream}
    try:
        from core.chatterbox_tts import chatterbox_tts_stream
        engines["chatterbox"] = chatterbox_tts_stream
        print("[TTS] chatterbox loaded")
    except Exception as e:
        print(f"[TTS] chatterbox unavailable: {e}")
    return engines

_TTS_ENGINES = _load_tts_engines()
_DEFAULT_TTS = "edge"
print(f"[TTS] Available: {list(_TTS_ENGINES.keys())} | Default: {_DEFAULT_TTS}")

# Lip-sync engines — loaded lazily so missing optional engines don't crash startup
def _load_engines():
    engines = {}
    try:
        from core.wav2lip_lipsync import generate_wav2lip_video
        engines["wav2lip"] = generate_wav2lip_video
    except Exception as e:
        print(f"[ENGINE] wav2lip unavailable: {e}")
    try:
        from core.musictalk_lipsync import generate_musictalk_video
        engines["musetalk"] = generate_musictalk_video
    except Exception as e:
        print(f"[ENGINE] musetalk unavailable: {e}")
    try:
        from core.sadtalker_lipsync import generate_sadtalker_video
        engines["sadtalker"] = generate_sadtalker_video
    except Exception as e:
        print(f"[ENGINE] sadtalker unavailable: {e}")
    return engines

_ENGINES = _load_engines()
_DEFAULT_ENGINE = next(iter(_ENGINES), "wav2lip")
print(f"[ENGINE] Available: {list(_ENGINES.keys())} | Default: {_DEFAULT_ENGINE}")

app = FastAPI(title="Real-Time Physics Tutor Voice Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/models")
async def get_models():
    """Return list of available Ollama models plus cloud options."""
    models = list_ollama_models()
    import os
    cloud_provider = os.getenv("CLOUD_LLM_PROVIDER", "")
    cloud_key = os.getenv("CLOUD_LLM_API_KEY", "")
    cloud_model = os.getenv("CLOUD_LLM_MODEL", "gpt-4o-mini")
    if cloud_key:
        label = f"cloud:{cloud_provider or 'openai'}:{cloud_model}"
        models.append(label)
    return {"models": models, "default": config.OLLAMA_MODEL}


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Websocket connection established")

    audio_buffer = bytearray()
    lipsync_engine = _DEFAULT_ENGINE
    tts_engine = _DEFAULT_TTS
    llm_model = config.OLLAMA_MODEL
    avatar_mode = False
    history = ConversationHistory()

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            input_type = payload.get("type")

            # 0. ENGINE SELECTION
            if input_type == "set_engine":
                engine = payload.get("engine", "wav2lip")
                lipsync_engine = engine if engine in _ENGINES else _DEFAULT_ENGINE
                print(f"Lipsync engine set to: {lipsync_engine}")
                await websocket.send_json({"type": "engine_ack", "engine": lipsync_engine})

            # 0b. TTS SELECTION
            elif input_type == "set_tts":
                tts = payload.get("tts", "edge")
                tts_engine = tts if tts in _TTS_ENGINES else _DEFAULT_TTS
                print(f"TTS engine set to: {tts_engine}")
                await websocket.send_json({"type": "tts_ack", "tts": tts_engine})

            # 0c. LLM MODEL SELECTION
            elif input_type == "set_model":
                llm_model = payload.get("model", config.OLLAMA_MODEL)
                print(f"LLM model set to: {llm_model}")
                await websocket.send_json({"type": "model_ack", "model": llm_model})

            # 0d. AVATAR MODE TOGGLE (skip lipsync when off → audio-only)
            elif input_type == "set_mode":
                avatar_mode = bool(payload.get("avatar", False))
                print(f"Avatar mode set to: {avatar_mode}")
                await websocket.send_json({"type": "mode_ack", "avatar": avatar_mode})

            # CLEAR HISTORY
            elif input_type == "clear_history":
                history.clear()
                print("[HISTORY] Cleared by user.")
                await websocket.send_json({"type": "history_cleared"})

            # 1. TEXT INPUT
            elif input_type == "text":
                user_message = payload.get("data")
                print(f"User (text): {user_message}")
                rag_context = retrieve(user_message)
                await process_and_stream_response(user_message, websocket, lipsync_engine, history, rag_context, tts_engine, llm_model, avatar_mode)

            # 2. AUDIO CHUNKS (streaming from microphone)
            elif input_type == "audio_chunk":
                chunk_b64 = payload.get("data")
                if chunk_b64:
                    audio_buffer.extend(base64.b64decode(chunk_b64))

            # 3. END OF SPEECH (user stopped talking)
            elif input_type == "audio_end":
                print(f"User finished speaking. Processing {len(audio_buffer)} bytes...")
                if len(audio_buffer) > 0:
                    stt_start = time.time()
                    loop = asyncio.get_event_loop()
                    transcript = await loop.run_in_executor(
                        None, transcribe_audio, bytes(audio_buffer)
                    )
                    print(f"[TIMING] STT: {time.time() - stt_start:.2f}s -> '{transcript}'")

                    if transcript.strip():
                        await websocket.send_json({"type": "transcript", "data": transcript})
                        rag_context = retrieve(transcript)
                        await process_and_stream_response(transcript, websocket, lipsync_engine, history, rag_context, tts_engine, llm_model, avatar_mode)

                audio_buffer.clear()

    except WebSocketDisconnect:
        print("Websocket disconnected")
    except Exception as e:
        print(f"Error in websocket: {e}")


def _run_lipsync(engine: str, audio_path: str) -> str:
    """Calls the appropriate lipsync engine (runs in executor thread)."""
    fn = _ENGINES.get(engine) or _ENGINES.get(_DEFAULT_ENGINE)
    if fn is None:
        raise RuntimeError("No lipsync engine available.")
    return fn(audio_path)


_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "frontend", "assets")


async def process_and_stream_response(message: str, websocket: WebSocket, lipsync_engine: str = "wav2lip", history: "ConversationHistory | None" = None, rag_context: str = "", tts_engine: str = "edge", llm_model: str = "", avatar_mode: bool = False):
    """Core pipeline: sends text to the LLM and streams lip-synced avatar output."""
    current_sentence = ""

    pipeline_start = time.time()
    first_token_time = None
    total_tts_time = 0.0
    total_lipsync_time = 0.0
    sentence_count = 0
    saved_video_url = None

    print(f"Assistant is thinking & speaking... [engine: {lipsync_engine}]")

    loop = asyncio.get_event_loop()

    async def _process_sentence(text: str, idx: int, label: str = ""):
        nonlocal total_tts_time, total_lipsync_time

        await websocket.send_json({"type": "text_chunk", "data": text + " "})

        tts_start = time.time()
        audio_bytes = bytearray()
        tts_fn = _TTS_ENGINES.get(tts_engine, text_to_speech_stream)
        async for audio_chunk in tts_fn(text):
            audio_bytes.extend(audio_chunk)
        tts_elapsed = time.time() - tts_start
        total_tts_time += tts_elapsed
        print(f"[TIMING] TTS({tts_engine}) sentence #{idx}{label}: {tts_elapsed:.2f}s")

        if not audio_bytes:
            return

        # Avatar OFF → audio-only (skip Wav2Lip entirely, huge latency win)
        if not avatar_mode:
            audio_b64 = base64.b64encode(bytes(audio_bytes)).decode("utf-8")
            await websocket.send_json({"type": "audio_chunk", "data": audio_b64})
            return

        tmp_audio_path = None
        video_path = None
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(bytes(audio_bytes))
            tmp_audio_path = tmp.name

        try:
            ls_start = time.time()
            video_path = await loop.run_in_executor(None, _run_lipsync, lipsync_engine, tmp_audio_path)
            ls_elapsed = time.time() - ls_start
            total_lipsync_time += ls_elapsed
            print(f"[TIMING] {lipsync_engine} sentence #{idx}{label}: {ls_elapsed:.2f}s")

            with open(video_path, "rb") as f:
                video_bytes = f.read()
            video_b64 = base64.b64encode(video_bytes).decode("utf-8")
            await websocket.send_json({"type": "video_chunk", "data": video_b64})

            # Save first sentence video to assets for persistent display
            nonlocal saved_video_url
            if saved_video_url is None:
                try:
                    os.makedirs(_ASSETS_DIR, exist_ok=True)
                    saved_path = os.path.join(_ASSETS_DIR, "last_response.mp4")
                    with open(saved_path, "wb") as sf:
                        sf.write(video_bytes)
                    saved_video_url = "/app/assets/last_response.mp4"
                except Exception as save_err:
                    print(f"[SAVE] Could not save video: {save_err}")

        except Exception as e:
            err_msg = str(e)
            print(f"[LIPSYNC ERROR] {lipsync_engine} sentence #{idx}{label}:\n{err_msg}")
            await websocket.send_json({"type": "lipsync_error", "engine": lipsync_engine, "detail": err_msg})
            audio_b64 = base64.b64encode(bytes(audio_bytes)).decode("utf-8")
            await websocket.send_json({"type": "audio_chunk", "data": audio_b64})

        finally:
            for p in (tmp_audio_path, video_path):
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

    # 1. Stream LLM tokens and process sentence by sentence
    for token in stream_llm_response(message, history=history, context=rag_context, model=llm_model or None):
        if first_token_time is None:
            first_token_time = time.time()
            print(f"[TIMING] Time to first LLM token: {first_token_time - pipeline_start:.2f}s")

        current_sentence += token

        if token in [".", "!", "?", "\n"] or len(current_sentence) > 80:
            sentence_to_speak = current_sentence.strip()
            if sentence_to_speak:
                sentence_count += 1
                await _process_sentence(sentence_to_speak, sentence_count)
            current_sentence = ""

    llm_total = time.time() - pipeline_start

    # 2. Handle trailing text without terminal punctuation
    if current_sentence.strip():
        sentence_count += 1
        await _process_sentence(current_sentence.strip(), sentence_count, " (trailing)")

    total_elapsed = time.time() - pipeline_start
    avg_lipsync = total_lipsync_time / sentence_count if sentence_count else 0.0
    avg_tts = total_tts_time / sentence_count if sentence_count else 0.0

    print(
        f"[TIMING] SUMMARY -> total: {total_elapsed:.2f}s | "
        f"LLM: {llm_total:.2f}s | TTS total: {total_tts_time:.2f}s | "
        f"{lipsync_engine} total: {total_lipsync_time:.2f}s | sentences: {sentence_count}"
    )

    await websocket.send_json({
        "type": "timing",
        "engine": lipsync_engine,
        "model": llm_model or config.OLLAMA_MODEL,
        "tts": tts_engine,
        "total": round(total_elapsed, 2),
        "llm": round(llm_total, 2),
        "tts_total": round(total_tts_time, 2),
        "tts_avg": round(avg_tts, 2),
        "lipsync_total": round(total_lipsync_time, 2),
        "lipsync_avg": round(avg_lipsync, 2),
        "sentences": sentence_count,
    })
    if saved_video_url:
        await websocket.send_json({"type": "video_saved", "url": saved_video_url})
    await websocket.send_json({"type": "end_of_response"})


# Mount the frontend folder to serve the page
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)