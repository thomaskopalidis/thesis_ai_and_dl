import asyncio
import tempfile
import os
import io

def _load_model():
    import torch
    from chatterbox.tts import ChatterboxTTS
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ChatterboxTTS.from_pretrained(device=device)
    print(f"[ChatterboxTTS] Loaded on {device}")
    return model

_model = None

def _get_model():
    global _model
    if _model is None:
        _model = _load_model()
    return _model

async def chatterbox_tts_stream(text: str):
    """Generate audio using Chatterbox TTS, yield raw WAV bytes."""
    if not text or not text.strip():
        return
    try:
        import torch
        import torchaudio
        loop = asyncio.get_event_loop()

        def _generate():
            model = _get_model()
            wav = model.generate(text)
            buf = io.BytesIO()
            torchaudio.save(buf, wav, model.sr, format="wav")
            buf.seek(0)
            return buf.read()

        audio_bytes = await loop.run_in_executor(None, _generate)
        yield audio_bytes
    except Exception as e:
        print(f"[ChatterboxTTS] Error: {e}")
        return
