import edge_tts
import config


async def text_to_speech_stream(text: str, voice: str = None):
    """
    Μετατρέπει κείμενο σε ήχο χρησιμοποιώντας το Edge TTS και κάνει stream
    τα audio bytes chunk-by-chunk καθώς παράγονται.

    Χρήση:
        async for audio_chunk in text_to_speech_stream("Hello world"):
            ...  # audio_chunk είναι raw MP3 bytes

    Args:
        text: Το κείμενο προς εκφώνηση.
        voice: Προαιρετικό override της φωνής (default: config.TTS_VOICE).
    """
    if not text or not text.strip():
        return

    selected_voice = voice or config.TTS_VOICE

    try:
        communicate = edge_tts.Communicate(text, selected_voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
    except Exception as e:
        print(f"   ✗ TTS Error: {e}")
        return