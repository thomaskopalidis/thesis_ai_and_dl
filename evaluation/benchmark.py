"""
Light benchmark for the physics tutor pipeline.

Design (see docs/DECISIONS.md D-00X for rationale):
  - 3 LLMs:    qwen2.5:3b, qwen2.5:7b, llama3.1:8b
  - 2 RAG:     on / off
  - 30 Qs:     evaluation/eval_questions.json (in-scope only; OOS excluded)
  - 1 warm-up per (model, rag) config + 3 measured runs per question
  - max_tokens=50 (matches the Teacher system prompt "1-2 sentences max")

Metrics per run:
  rag_time_s, llm_first_token_s, llm_total_s,
  tokens_generated, tokens_per_sec, answer,
  retrieved_chunk_ids, retrieved_chapters,
  kb_source_chapter, hit_at_3_chapter

Outputs (under evaluation/results/):
  benchmark_<timestamp>.csv   one row per measured run
  summary_<timestamp>.csv     mean/std per (model, rag) config
  progress_<timestamp>.log    rolling log for monitoring

Resumability:
  If an existing benchmark_*.csv is passed via --resume, previously completed
  (model, rag, question_id, run_idx) tuples are skipped so a crashed run can
  continue without duplicates.

Usage:
  python evaluation/benchmark.py                           # defaults (3+3 LLMs listed below)
  python evaluation/benchmark.py --models qwen2.5:3b       # single model
  python evaluation/benchmark.py --runs 5 --warmups 2      # override run counts
  python evaluation/benchmark.py --resume results/benchmark_20261011_120000.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from core.rag import retrieve_with_metadata  # noqa: E402
from core.llm import stream_llm_response, ConversationHistory  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODELS = ["qwen2.5:3b", "qwen2.5:7b", "llama3.1:8b"]
DEFAULT_RUNS = 3
DEFAULT_WARMUPS = 1
DEFAULT_MAX_TOKENS = 50
DEFAULT_TOP_K = 3

RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"
QUESTIONS_PATH = PROJECT_ROOT / "evaluation" / "eval_questions.json"

CSV_FIELDS = [
    "timestamp",
    "model",
    "rag",
    "question_id",
    "topic",
    "difficulty",
    "run_idx",
    "question",
    "answer",
    "answer_chars",
    "tokens_generated",
    "rag_time_s",
    "llm_first_token_s",
    "llm_total_s",
    "tokens_per_sec",
    "retrieved_chunk_ids",
    "retrieved_chapters",
    "retrieved_sections",
    "kb_source_chapter",
    "kb_source_section",
    "hit_at_3_chapter",
    "hit_at_3_section",
    "error",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_questions(in_scope_only: bool = True) -> list[dict]:
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    qs = data["questions"]
    if in_scope_only:
        qs = [q for q in qs if q.get("in_scope")]
    return qs


def load_completed(resume_path: Path | None) -> set[tuple]:
    """Return the set of (model, rag, question_id, run_idx) tuples already done."""
    done: set[tuple] = set()
    if resume_path and resume_path.is_file():
        with resume_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("error"):
                    continue  # retry failed rows
                key = (row["model"], row["rag"], row["question_id"], int(row["run_idx"]))
                done.add(key)
    return done


def do_single_run(
    *,
    question: dict,
    model: str,
    use_rag: bool,
    max_tokens: int,
    top_k: int,
) -> dict:
    """Executes one measured query. Returns a flat dict matching CSV_FIELDS."""
    qid = question["id"]
    text = question["question"]
    kb_src = question.get("kb_source") or {}
    kb_ch = kb_src.get("chapter", "")
    kb_sec = kb_src.get("section", "")

    row = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "model": model,
        "rag": "on" if use_rag else "off",
        "question_id": qid,
        "topic": question.get("topic", ""),
        "difficulty": question.get("difficulty", ""),
        "question": text,
        "kb_source_chapter": kb_ch,
        "kb_source_section": kb_sec,
        "error": "",
    }

    # 1) RAG retrieval (if enabled)
    rag_context = ""
    retrieved_ids: list[str] = []
    retrieved_chapters: list[str] = []
    retrieved_sections: list[str] = []
    t_rag = 0.0
    if use_rag:
        t0 = time.time()
        r = retrieve_with_metadata(text, top_k=top_k)
        t_rag = time.time() - t0
        retrieved_ids = r.get("ids", []) or []
        for m in (r.get("metadatas") or []):
            if isinstance(m, dict):
                retrieved_chapters.append(m.get("chapter", ""))
                retrieved_sections.append(m.get("section", ""))
            else:
                retrieved_chapters.append("")
                retrieved_sections.append("")
        docs = r.get("documents") or []
        rag_context = "\n\n".join(docs)

    row["rag_time_s"] = round(t_rag, 4)
    row["retrieved_chunk_ids"] = ";".join(retrieved_ids)
    row["retrieved_chapters"] = ";".join(retrieved_chapters)
    row["retrieved_sections"] = ";".join(retrieved_sections)
    row["hit_at_3_chapter"] = int(bool(kb_ch) and (kb_ch in retrieved_chapters))
    row["hit_at_3_section"] = int(bool(kb_sec) and (kb_sec in retrieved_sections))

    # 2) LLM streaming
    history = ConversationHistory()
    parts: list[str] = []
    first_token_t: float | None = None
    t_llm0 = time.time()
    try:
        for token in stream_llm_response(text, history=history, context=rag_context, model=model):
            if first_token_t is None:
                first_token_t = time.time() - t_llm0
            parts.append(token)
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"
        row["llm_first_token_s"] = ""
        row["llm_total_s"] = round(time.time() - t_llm0, 4)
        row["answer"] = ""
        row["answer_chars"] = 0
        row["tokens_generated"] = 0
        row["tokens_per_sec"] = ""
        return row

    t_llm_total = time.time() - t_llm0
    answer = "".join(parts).strip()
    n_tokens = len(parts)

    row["llm_first_token_s"] = round(first_token_t, 4) if first_token_t is not None else ""
    row["llm_total_s"] = round(t_llm_total, 4)
    row["answer"] = answer
    row["answer_chars"] = len(answer)
    row["tokens_generated"] = n_tokens
    row["tokens_per_sec"] = round(n_tokens / t_llm_total, 2) if t_llm_total > 0 else ""
    return row


def write_row(csv_path: Path, row: dict) -> None:
    is_new = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def log(msg: str, log_path: Path) -> None:
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

def write_summary(csv_in: Path, csv_out: Path) -> None:
    """Produces per (model, rag) aggregates: mean/std of key timing metrics +
    Hit@3 rates."""
    import statistics
    buckets: dict[tuple[str, str], list[dict]] = {}
    with csv_in.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("error"):
                continue
            buckets.setdefault((row["model"], row["rag"]), []).append(row)

    cols = [
        "model", "rag", "n_runs",
        "llm_first_token_s_mean", "llm_first_token_s_std",
        "llm_total_s_mean", "llm_total_s_std",
        "tokens_per_sec_mean",
        "tokens_generated_mean",
        "answer_chars_mean",
        "rag_time_s_mean",
        "hit_at_3_chapter_rate",
        "hit_at_3_section_rate",
    ]

    def _mean(xs):
        xs = [float(x) for x in xs if x not in ("", None)]
        return round(statistics.mean(xs), 4) if xs else ""

    def _std(xs):
        xs = [float(x) for x in xs if x not in ("", None)]
        return round(statistics.stdev(xs), 4) if len(xs) > 1 else ""

    with csv_out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for (model, rag), rows in sorted(buckets.items()):
            writer.writerow({
                "model": model,
                "rag": rag,
                "n_runs": len(rows),
                "llm_first_token_s_mean": _mean(r["llm_first_token_s"] for r in rows),
                "llm_first_token_s_std":  _std(r["llm_first_token_s"] for r in rows),
                "llm_total_s_mean":       _mean(r["llm_total_s"] for r in rows),
                "llm_total_s_std":        _std(r["llm_total_s"] for r in rows),
                "tokens_per_sec_mean":    _mean(r["tokens_per_sec"] for r in rows),
                "tokens_generated_mean":  _mean(r["tokens_generated"] for r in rows),
                "answer_chars_mean":      _mean(r["answer_chars"] for r in rows),
                "rag_time_s_mean":        _mean(r["rag_time_s"] for r in rows),
                "hit_at_3_chapter_rate":  _mean(r["hit_at_3_chapter"] for r in rows),
                "hit_at_3_section_rate":  _mean(r["hit_at_3_section"] for r in rows),
            })


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS,
                    help="Ollama model names to benchmark")
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                    help="Measured runs per (model, rag, question)")
    ap.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS,
                    help="Warm-up runs per (model, rag) BEFORE measurement")
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--rag", choices=["on", "off", "both"], default="both")
    ap.add_argument("--limit-questions", type=int, default=None,
                    help="Only use first N questions (for smoke-testing)")
    ap.add_argument("--resume", type=str, default=None,
                    help="Path to existing benchmark CSV to resume")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Honour max_tokens via env var (our LLM wrapper reads MAX_TOKENS at call time
    # only via the function arg; we patch stream_llm_response's path via monkey
    # patching the default max_tokens of _ollama_chat below.)
    # Simplest: just set an env our code can respect.
    os.environ.setdefault("OLLAMA_READ_TIMEOUT", "300")

    # Prepare outputs
    if args.resume:
        resume_path = Path(args.resume)
        if not resume_path.is_absolute():
            resume_path = PROJECT_ROOT / resume_path
        csv_path = resume_path
        stamp = resume_path.stem.replace("benchmark_", "")
    else:
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        csv_path = RESULTS_DIR / f"benchmark_{stamp}.csv"
    log_path = RESULTS_DIR / f"progress_{stamp}.log"
    summary_path = RESULTS_DIR / f"summary_{stamp}.csv"

    log(f"=== Benchmark starting ===", log_path)
    log(f"Models:    {args.models}", log_path)
    log(f"RAG:       {args.rag}", log_path)
    log(f"Runs:      {args.runs} (+ {args.warmups} warm-up per config)", log_path)
    log(f"Max tok:   {args.max_tokens}", log_path)
    log(f"Top-K:     {args.top_k}", log_path)
    log(f"CSV out:   {csv_path}", log_path)

    # Patch default max_tokens in the LLM wrapper (crude but effective)
    import core.llm as _llm_mod
    _orig_ollama_chat = _llm_mod._ollama_chat

    def _patched(messages, stream=True, max_tokens=args.max_tokens, model=None):
        return _orig_ollama_chat(messages, stream=stream, max_tokens=max_tokens, model=model)

    _llm_mod._ollama_chat = _patched

    # Also, re-bind the name used inside stream_llm_response (closure captures
    # at def-time, so we must poke the module).
    _llm_mod._ollama_chat = _patched

    # Load inputs
    questions = load_questions(in_scope_only=True)
    if args.limit_questions:
        questions = questions[: args.limit_questions]
    log(f"Questions: {len(questions)} (in-scope only)", log_path)

    rag_values = ["on", "off"] if args.rag == "both" else [args.rag]
    done = load_completed(csv_path if args.resume else None)
    log(f"Resumed:   {len(done)} rows already present", log_path)

    total_runs = len(args.models) * len(rag_values) * len(questions) * args.runs
    log(f"Total runs planned: {total_runs}", log_path)
    log("", log_path)

    completed = 0
    errors = 0
    t_overall = time.time()

    for model in args.models:
        for rag_flag in rag_values:
            use_rag = (rag_flag == "on")
            log(f"── Config: model={model} rag={rag_flag} ──", log_path)

            # Warm-up (not recorded)
            for w in range(args.warmups):
                try:
                    q0 = questions[0]
                    _ = do_single_run(
                        question=q0, model=model, use_rag=use_rag,
                        max_tokens=args.max_tokens, top_k=args.top_k,
                    )
                    log(f"  warmup {w+1}/{args.warmups} ok", log_path)
                except Exception as e:
                    log(f"  warmup {w+1} FAILED: {e}", log_path)

            # Measured runs
            for q in questions:
                for run_idx in range(1, args.runs + 1):
                    key = (model, rag_flag, q["id"], run_idx)
                    if key in done:
                        continue
                    try:
                        row = do_single_run(
                            question=q, model=model, use_rag=use_rag,
                            max_tokens=args.max_tokens, top_k=args.top_k,
                        )
                        row["run_idx"] = run_idx
                        write_row(csv_path, row)
                        completed += 1
                        if row.get("error"):
                            errors += 1
                            log(f"  {q['id']} run {run_idx}: ERROR {row['error']}", log_path)
                        else:
                            elapsed = row["llm_total_s"]
                            log(
                                f"  {q['id']} run {run_idx}: "
                                f"{elapsed:.2f}s, {row['tokens_generated']} tok, "
                                f"hit@3_ch={row['hit_at_3_chapter']}",
                                log_path,
                            )
                    except Exception as e:
                        errors += 1
                        tb = traceback.format_exc(limit=2)
                        log(f"  {q['id']} run {run_idx}: UNCAUGHT {type(e).__name__}: {e}\n{tb}", log_path)
                        # Still write a stub row so we can skip on resume
                        stub = {
                            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                            "model": model, "rag": rag_flag, "question_id": q["id"],
                            "run_idx": run_idx, "error": f"{type(e).__name__}: {e}",
                        }
                        write_row(csv_path, stub)

    dur = time.time() - t_overall
    log("", log_path)
    log(f"=== Benchmark done ===", log_path)
    log(f"Completed: {completed}/{total_runs}  errors={errors}", log_path)
    log(f"Elapsed:   {dur/60:.1f} min", log_path)

    # Summary
    try:
        write_summary(csv_path, summary_path)
        log(f"Summary written: {summary_path}", log_path)
    except Exception as e:
        log(f"Summary FAILED: {e}", log_path)


if __name__ == "__main__":
    main()
