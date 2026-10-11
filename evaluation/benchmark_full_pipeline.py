"""
Full-pipeline benchmark: STT + RAG + LLM + TTS + Avatar (Wav2Lip).

Produces the model-vs-stage table from the thesis plan:

  Model          STT    RAG    LLM    TTS    Avatar  Total
  qwen2.5:3b     X ms   Y ms   Z s    A s    B s     T s
  qwen2.5:7b     ...
  llama3.1:8b    ...
  mistral:7b     ...
  phi3:mini      ...
  llama3.2:3b    ...

Design decisions (see docs/DECISIONS.md D-00X):
  STT    — measured ONCE on 10 reference wavs; same value filled per model.
  RAG    — measured per query (should be ~constant across models since embedding
           is model-independent, but we keep per-run data for completeness).
  LLM    — measured per (model, question, run).
  TTS    — measured per (model, question, run) because answer length varies.
  Avatar — measured ONCE on a fixed reference audio (depends only on audio
           duration, not on which LLM produced the text).

Outputs under evaluation/results/:
  pipeline_<timestamp>.csv         detailed per-run rows
  stages_summary_<timestamp>.csv   final model×stage table
  pipeline_progress_<timestamp>.log

Usage:
  python evaluation/benchmark_full_pipeline.py \\
      --models qwen2.5:3b qwen2.5:7b llama3.1:8b mistral:7b phi3:mini llama3.2:3b \\
      --runs 1 --warmups 1

  python evaluation/benchmark_full_pipeline.py --skip-avatar   # drop Wav2Lip
  python evaluation/benchmark_full_pipeline.py --skip-stt      # drop STT
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from core.rag import retrieve_with_metadata  # noqa: E402
from core.llm import stream_llm_response  # noqa: E402
from core.tts import text_to_speech_stream  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODELS = [
    "qwen2.5:3b", "qwen2.5:7b", "llama3.1:8b",
    "mistral:7b", "phi3:mini", "llama3.2:3b",
]
DEFAULT_RUNS = 1
DEFAULT_WARMUPS = 1
DEFAULT_MAX_TOKENS = 50
DEFAULT_TOP_K = 3
AVATAR_REFERENCE_WAV = PROJECT_ROOT / "evaluation" / "audio" / "synthetic" / "Q05.wav"
AVATAR_RUNS = 3

RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"
QUESTIONS_PATH = PROJECT_ROOT / "evaluation" / "eval_questions.json"
AUDIO_DIR = PROJECT_ROOT / "evaluation" / "audio" / "synthetic"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log(msg: str, log_path: Path) -> None:
    line = f"[{_now_iso()}] {msg}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_questions(in_scope_only: bool = True) -> list[dict]:
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    qs = data["questions"]
    if in_scope_only:
        qs = [q for q in qs if q.get("in_scope")]
    return qs


# ─────────────────────────────────────────────────────────────────────────────
# Stage: STT (measured ONCE, independent of LLM)
# ─────────────────────────────────────────────────────────────────────────────

def measure_stt(log_path: Path) -> float | None:
    """Transcribe each synthetic wav and return mean elapsed time per file."""
    from core.stt import transcribe_audio

    wavs = sorted(AUDIO_DIR.glob("*.wav"))
    if not wavs:
        log(f"[STT] No wav files in {AUDIO_DIR}, skipping STT", log_path)
        return None

    # Warm-up (load model, JIT, cuDNN autotune)
    log(f"[STT] Warm-up on {wavs[0].name}...", log_path)
    _ = transcribe_audio(wavs[0].read_bytes())

    times: list[float] = []
    for w in wavs:
        t0 = time.time()
        _ = transcribe_audio(w.read_bytes())
        dt = time.time() - t0
        times.append(dt)
        log(f"[STT] {w.name}: {dt:.3f}s", log_path)

    mean = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0.0
    log(f"[STT] mean={mean:.3f}s  std={std:.3f}s  (n={len(times)})", log_path)
    return mean


# ─────────────────────────────────────────────────────────────────────────────
# Stage: Avatar / Wav2Lip (measured ONCE on a reference audio)
# ─────────────────────────────────────────────────────────────────────────────

def measure_avatar(log_path: Path) -> float | None:
    """Run Wav2Lip N times on a fixed reference wav; return mean elapsed."""
    try:
        from core.wav2lip_lipsync import generate_wav2lip_video
    except Exception as e:
        log(f"[AVATAR] Wav2Lip not importable: {e}", log_path)
        return None

    if not AVATAR_REFERENCE_WAV.is_file():
        log(f"[AVATAR] Reference wav missing: {AVATAR_REFERENCE_WAV}", log_path)
        return None

    # Warm-up
    log(f"[AVATAR] Warm-up on {AVATAR_REFERENCE_WAV.name}...", log_path)
    try:
        _ = generate_wav2lip_video(str(AVATAR_REFERENCE_WAV))
    except Exception as e:
        log(f"[AVATAR] Warm-up FAILED: {e}", log_path)
        return None

    times: list[float] = []
    for i in range(AVATAR_RUNS):
        t0 = time.time()
        try:
            out = generate_wav2lip_video(str(AVATAR_REFERENCE_WAV))
            dt = time.time() - t0
            times.append(dt)
            log(f"[AVATAR] run {i+1}/{AVATAR_RUNS}: {dt:.3f}s  →  {out}", log_path)
            # Clean up produced video
            if out and os.path.exists(out):
                try: os.unlink(out)
                except Exception: pass
        except Exception as e:
            log(f"[AVATAR] run {i+1} FAILED: {e}", log_path)

    if not times:
        return None

    mean = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0.0
    log(f"[AVATAR] mean={mean:.3f}s  std={std:.3f}s  (n={len(times)})", log_path)
    return mean


# ─────────────────────────────────────────────────────────────────────────────
# Stage: TTS (measured per answer)
# ─────────────────────────────────────────────────────────────────────────────

async def _tts_bytes(text: str) -> tuple[int, float]:
    """Yield-concat Edge-TTS mp3 bytes for `text`; return (nbytes, elapsed)."""
    t0 = time.time()
    nbytes = 0
    async for chunk in text_to_speech_stream(text):
        nbytes += len(chunk)
    return nbytes, time.time() - t0


def tts_sync(text: str) -> tuple[int, float]:
    try:
        return asyncio.run(_tts_bytes(text))
    except RuntimeError:
        # already inside event loop (e.g. Jupyter); fall back to new loop
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_tts_bytes(text))
        finally:
            loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Per-query measurement: RAG + LLM + TTS
# ─────────────────────────────────────────────────────────────────────────────

def run_rag_llm_tts(question: dict, model: str, use_rag: bool,
                    max_tokens: int, top_k: int) -> dict:
    """One query. Returns timings + answer."""
    out = {
        "model": model,
        "rag": "on" if use_rag else "off",
        "question_id": question["id"],
        "rag_time_s": 0.0,
        "llm_first_token_s": None,
        "llm_total_s": None,
        "tts_time_s": None,
        "tts_bytes": None,
        "tokens_generated": 0,
        "answer_chars": 0,
        "answer": "",
        "retrieved_chunk_ids": "",
        "retrieved_chapters": "",
        "hit_at_3_chapter": 0,
        "hit_at_3_section": 0,
        "error": "",
    }
    kb_src = question.get("kb_source") or {}
    kb_ch = kb_src.get("chapter", "")
    kb_sec = kb_src.get("section", "")

    # 1) RAG
    rag_ctx = ""
    if use_rag:
        t0 = time.time()
        r = retrieve_with_metadata(question["question"], top_k=top_k)
        out["rag_time_s"] = round(time.time() - t0, 4)
        out["retrieved_chunk_ids"] = ";".join(r.get("ids", []) or [])
        chapters, sections = [], []
        for m in (r.get("metadatas") or []):
            if isinstance(m, dict):
                chapters.append(m.get("chapter", ""))
                sections.append(m.get("section", ""))
        out["retrieved_chapters"] = ";".join(chapters)
        out["hit_at_3_chapter"] = int(bool(kb_ch) and kb_ch in chapters)
        out["hit_at_3_section"] = int(bool(kb_sec) and kb_sec in sections)
        rag_ctx = "\n\n".join(r.get("documents") or [])

    # 2) LLM (streaming)
    parts: list[str] = []
    first_t: float | None = None
    t0 = time.time()
    try:
        for tok in stream_llm_response(question["question"], context=rag_ctx, model=model):
            if first_t is None:
                first_t = time.time() - t0
            parts.append(tok)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        out["llm_total_s"] = round(time.time() - t0, 4)
        return out

    answer = "".join(parts).strip()
    out["llm_first_token_s"] = round(first_t, 4) if first_t is not None else None
    out["llm_total_s"] = round(time.time() - t0, 4)
    out["answer"] = answer
    out["answer_chars"] = len(answer)
    out["tokens_generated"] = len(parts)

    # 3) TTS
    if answer:
        try:
            nbytes, elapsed = tts_sync(answer)
            out["tts_time_s"] = round(elapsed, 4)
            out["tts_bytes"] = nbytes
        except Exception as e:
            out["error"] = (out["error"] + f" | TTS: {type(e).__name__}: {e}").strip(" |")

    return out


# ─────────────────────────────────────────────────────────────────────────────
# CSV / Summary
# ─────────────────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "timestamp", "model", "rag", "question_id", "run_idx",
    "rag_time_s", "llm_first_token_s", "llm_total_s",
    "tts_time_s", "tts_bytes",
    "tokens_generated", "answer_chars", "answer",
    "retrieved_chunk_ids", "retrieved_chapters",
    "hit_at_3_chapter", "hit_at_3_section",
    "error",
]


def write_row(csv_path: Path, row: dict) -> None:
    is_new = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if is_new:
            w.writeheader()
        w.writerow(row)


def write_stages_summary(
    *,
    detailed_csv: Path,
    summary_csv: Path,
    stt_mean: float | None,
    avatar_mean: float | None,
) -> None:
    """Build the per-model stages table: STT | RAG | LLM | TTS | Avatar | Total."""
    import csv as _csv
    buckets: dict[str, list[dict]] = {}
    with detailed_csv.open("r", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            if row.get("error"):
                continue
            # Only use rag=on rows for the "with-RAG" summary. Could extend to split.
            if row.get("rag") != "on":
                continue
            buckets.setdefault(row["model"], []).append(row)

    def _mean(xs):
        xs = [float(x) for x in xs if x not in ("", None)]
        return round(statistics.mean(xs), 4) if xs else None

    cols = ["model", "stt_s", "rag_s", "llm_s", "tts_s", "avatar_s", "total_s", "n_runs"]
    with summary_csv.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for model, rows in sorted(buckets.items()):
            rag_s = _mean(r["rag_time_s"] for r in rows) or 0.0
            llm_s = _mean(r["llm_total_s"] for r in rows) or 0.0
            tts_s = _mean(r["tts_time_s"] for r in rows) or 0.0
            stt_s = round(stt_mean, 4) if stt_mean is not None else 0.0
            av_s  = round(avatar_mean, 4) if avatar_mean is not None else 0.0
            total = round(stt_s + rag_s + llm_s + tts_s + av_s, 4)
            w.writerow({
                "model": model,
                "stt_s":    stt_s,
                "rag_s":    rag_s,
                "llm_s":    llm_s,
                "tts_s":    tts_s,
                "avatar_s": av_s,
                "total_s":  total,
                "n_runs":   len(rows),
            })


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    ap.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--rag", choices=["on", "off", "both"], default="on",
                    help="Default 'on' because that is what the stages table shows.")
    ap.add_argument("--limit-questions", type=int, default=None)
    ap.add_argument("--skip-stt", action="store_true")
    ap.add_argument("--skip-avatar", action="store_true")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = RESULTS_DIR / f"pipeline_{stamp}.csv"
    summary_path = RESULTS_DIR / f"stages_summary_{stamp}.csv"
    log_path = RESULTS_DIR / f"pipeline_progress_{stamp}.log"

    os.environ.setdefault("OLLAMA_READ_TIMEOUT", "300")

    log("=== Full pipeline benchmark ===", log_path)
    log(f"Models:    {args.models}", log_path)
    log(f"RAG:       {args.rag}", log_path)
    log(f"Runs/Q:    {args.runs} (+{args.warmups} warm-up per config)", log_path)
    log(f"Max tok:   {args.max_tokens}", log_path)
    log(f"CSV:       {csv_path}", log_path)

    # Patch LLM wrapper to honour --max-tokens
    import core.llm as _llm_mod
    _orig = _llm_mod._ollama_chat

    def _patched(messages, stream=True, max_tokens=args.max_tokens, model=None):
        return _orig(messages, stream=stream, max_tokens=max_tokens, model=model)

    _llm_mod._ollama_chat = _patched

    # 1) STT measured ONCE
    stt_mean = None
    if not args.skip_stt:
        log("", log_path)
        log("── Measuring STT (once, independent of LLM) ──", log_path)
        try:
            stt_mean = measure_stt(log_path)
        except Exception as e:
            log(f"[STT] FAILED: {e}", log_path)

    # 2) Avatar measured ONCE
    avatar_mean = None
    if not args.skip_avatar:
        log("", log_path)
        log("── Measuring Avatar/Wav2Lip (once, on reference wav) ──", log_path)
        try:
            avatar_mean = measure_avatar(log_path)
        except Exception as e:
            log(f"[AVATAR] FAILED: {e}", log_path)

    # 3) RAG + LLM + TTS per model
    questions = load_questions(in_scope_only=True)
    if args.limit_questions:
        questions = questions[: args.limit_questions]
    rag_values = ["on", "off"] if args.rag == "both" else [args.rag]
    log("", log_path)
    log(f"── Per-model LLM/TTS/RAG on {len(questions)} questions × {len(rag_values)} rag × {args.runs} runs ──", log_path)

    t_overall = time.time()
    completed = 0
    errors = 0
    for model in args.models:
        for rag_flag in rag_values:
            use_rag = (rag_flag == "on")
            log(f"── {model}  rag={rag_flag} ──", log_path)

            # warmup
            for w in range(args.warmups):
                try:
                    _ = run_rag_llm_tts(
                        questions[0], model=model, use_rag=use_rag,
                        max_tokens=args.max_tokens, top_k=args.top_k,
                    )
                    log(f"  warmup {w+1}/{args.warmups} ok", log_path)
                except Exception as e:
                    log(f"  warmup {w+1} FAILED: {e}", log_path)

            # measured
            for q in questions:
                for run_idx in range(1, args.runs + 1):
                    try:
                        row = run_rag_llm_tts(
                            q, model=model, use_rag=use_rag,
                            max_tokens=args.max_tokens, top_k=args.top_k,
                        )
                        row["timestamp"] = _now_iso()
                        row["run_idx"] = run_idx
                        write_row(csv_path, row)
                        completed += 1
                        if row.get("error"):
                            errors += 1
                            log(f"  {q['id']} r{run_idx}: ERROR {row['error']}", log_path)
                        else:
                            log(
                                f"  {q['id']} r{run_idx}: "
                                f"rag={row['rag_time_s']:.3f}s "
                                f"llm={row['llm_total_s']:.2f}s "
                                f"tts={row['tts_time_s']:.2f}s "
                                f"hit@3={row['hit_at_3_chapter']}",
                                log_path,
                            )
                    except Exception as e:
                        errors += 1
                        tb = traceback.format_exc(limit=2)
                        log(f"  {q['id']} r{run_idx}: UNCAUGHT {e}\n{tb}", log_path)
                        write_row(csv_path, {
                            "timestamp": _now_iso(), "model": model, "rag": rag_flag,
                            "question_id": q["id"], "run_idx": run_idx,
                            "error": f"{type(e).__name__}: {e}",
                        })

    log("", log_path)
    log(f"=== Done === completed={completed} errors={errors} "
        f"elapsed={(time.time()-t_overall)/60:.1f} min", log_path)

    # 4) Final summary table
    try:
        write_stages_summary(
            detailed_csv=csv_path,
            summary_csv=summary_path,
            stt_mean=stt_mean,
            avatar_mean=avatar_mean,
        )
        log(f"Summary written: {summary_path}", log_path)

        # Print the table to stdout
        log("", log_path)
        log("=== STAGES TABLE (RAG=on, averaged across questions) ===", log_path)
        with summary_path.open("r", encoding="utf-8") as f:
            print(f.read())
    except Exception as e:
        log(f"Summary FAILED: {e}", log_path)


if __name__ == "__main__":
    main()
