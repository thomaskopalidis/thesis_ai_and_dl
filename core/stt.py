import tempfile
import os
import subprocess
import config

# Global μεταβλητή για το μοντέλο Whisper
_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print(f"   [STT] Loading Whisper ({config.WHISPER_MODEL}) on {config.WHISPER_DEVICE}...")

        # Καθορισμός compute type ανάλογα με τη συσκευή
        compute_type = "float16" if config.WHISPER_DEVICE == "cuda" else "int8"

        _whisper_model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=compute_type
        )
        print("   [STT] ✓ Whisper Model Ready!")
    return _whisper_model


def transcribe_audio(audio_bytes: bytes) -> str:
    """Μετατρέπει τα ακατέργαστα bytes ήχου σε κείμενο χρησιμοποιώντας το faster-whisper."""
    if not audio_bytes:
        return ""

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        raw_path = tmp.name

    wav_path = raw_path.replace(".webm", ".wav")

    try:
        # Μετατροπή του webm/opus stream από τον browser σε PCM WAV 16kHz Mono για το Whisper
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", raw_path, "-ar", "16000", "-ac", "1", wav_path],
            capture_output=True, timeout=15
        )

        if result.returncode != 0 or not os.path.exists(wav_path):
            print(f"   ✗ FFmpeg conversion failed: {result.stderr.decode(errors='ignore')}")
            return ""

        model = _get_whisper_model()
        segments, info = model.transcribe(
            wav_path,
            beam_size=1,        # μεγαλύτερο beam = πιο ακριβές (λίγο πιο αργό)
            language="en",      # αποφεύγει λάθος αναγνώριση γλώσσας σε σύντομα clips
            vad_filter=True,    # φιλτράρει σιωπή/θόρυβο πριν το transcribe
        )
        text = " ".join(seg.text for seg in segments).strip()
        return text

    except Exception as e:
        print(f"   ✗ STT Error: {e}")
        return ""

    finally:
        for p in (raw_path, wav_path):
            try:
                os.unlink(p)
            except Exception:
                pass