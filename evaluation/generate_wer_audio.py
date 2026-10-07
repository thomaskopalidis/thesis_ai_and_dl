"""
Generate synthetic audio (edge-tts) for the 10 WER-benchmark questions.

Writes WAV files to evaluation/audio/synthetic/Qnn.wav plus a transcripts.json
with the exact reference text each file speaks. The reference text is what we
compare the Whisper transcription against to compute WER.

Usage:
  python evaluation/generate_wer_audio.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

# IDs chosen to span 7 topics x easy/medium difficulty, avoiding questions
# that are mostly numeric computations (where WER is noisy and not
# representative of real tutor-style queries).
WER_QUESTION_IDS = ["Q01", "Q03", "Q05", "Q07", "Q10", "Q13", "Q16", "Q22", "Q24", "Q28"]

QUESTIONS_PATH = PROJECT_ROOT / "evaluation" / "eval_questions.json"
OUT_DIR = PROJECT_ROOT / "evaluation" / "audio" / "synthetic"
TRANSCRIPTS_PATH = PROJECT_ROOT / "evaluation" / "audio" / "transcripts.json"
VOICE = config.TTS_VOICE  # en-US-JennyNeural


async def _generate_one(text: str, out_wav: Path) -> None:
    """edge-tts yields MP3; we re-encode to 16 kHz mono WAV so Whisper is happy."""
    import edge_tts

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. edge-tts to MP3 (temp file).
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = Path(tmp.name)
    try:
        communicate = edge_tts.Communicate(text, VOICE)
        with mp3_path.open("wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])

        # 2. ffmpeg: MP3 -> 16 kHz mono WAV (same format Whisper uses internally).
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(mp3_path),
                "-ar", "16000", "-ac", "1",
                str(out_wav),
            ],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed: {result.stderr.decode(errors='ignore')[-500:]}"
            )
    finally:
        if mp3_path.exists():
            mp3_path.unlink()


async def main() -> None:
    questions = {q["id"]: q for q in json.loads(
        QUESTIONS_PATH.read_text(encoding="utf-8")
    )["questions"]}

    transcripts: dict[str, dict] = {}
    for qid in WER_QUESTION_IDS:
        if qid not in questions:
            print(f"[FAIL] Question {qid} not found in eval_questions.json")
            sys.exit(1)
        text = questions[qid]["question"]
        out_wav = OUT_DIR / f"{qid}.wav"
        print(f"[TTS] {qid}  '{text[:60]}{'…' if len(text) > 60 else ''}'")
        await _generate_one(text, out_wav)
        transcripts[qid] = {
            "reference": text,
            "file": str(out_wav.relative_to(PROJECT_ROOT)),
            "source": "synthetic_edge_tts",
            "voice": VOICE,
        }

    TRANSCRIPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS_PATH.write_text(
        json.dumps(transcripts, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n[OK] Wrote {len(transcripts)} WAV files to {OUT_DIR}")
    print(f"[OK] Reference transcripts: {TRANSCRIPTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())