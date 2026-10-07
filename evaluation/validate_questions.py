"""
Validates evaluation/eval_questions.json against the current ChromaDB index.

Checks:
  - JSON is well-formed and contains the expected keys.
  - No duplicate question ids.
  - Each in-scope question's kb_source.volume/chapter/section exists in
    Knowledge_base/processed/chunks.jsonl (so Precision@k/Hit@k can be
    computed later without false negatives).
  - Out-of-scope questions have kb_source = null and in_scope = false.
  - The declared distribution in meta matches the actual counts.

Exit code 0 if everything is OK, 1 otherwise.

Usage:
  python evaluation/validate_questions.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

QUESTIONS_PATH = PROJECT_ROOT / "evaluation" / "eval_questions.json"
CHUNKS_PATH = config.KNOWLEDGE_BASE_DIR / "processed" / "chunks.jsonl"


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not QUESTIONS_PATH.is_file():
        print(f"[FAIL] {QUESTIONS_PATH} not found", file=sys.stderr)
        return 1
    if not CHUNKS_PATH.is_file():
        print(f"[FAIL] {CHUNKS_PATH} not found. Run evaluation/ingest_kb.py first.",
              file=sys.stderr)
        return 1

    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    questions = data.get("questions", [])
    meta = data.get("meta", {})

    # Build an index of valid (volume, chapter) and (volume, chapter, section) tuples
    # that actually exist in the KB.
    valid_chapters: set[tuple[str, str]] = set()
    valid_sections: set[tuple[str, str, str]] = set()
    with CHUNKS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            valid_chapters.add((c["volume"], c["chapter"]))
            valid_sections.add((c["volume"], c["chapter"], c["section"]))

    print(f"[INFO] KB contains {len(valid_chapters)} chapters, "
          f"{len(valid_sections)} unique sections.")

    seen_ids: set[str] = set()
    diff_counter: Counter[str] = Counter()
    topic_counter: Counter[str] = Counter()
    in_scope_count = 0
    oos_count = 0

    for q in questions:
        qid = q.get("id", "<missing>")

        # Required keys
        for k in ("id", "question", "reference_answer", "kb_source",
                  "difficulty", "topic", "in_scope"):
            if k not in q:
                errors.append(f"{qid}: missing key '{k}'")

        if qid in seen_ids:
            errors.append(f"duplicate id '{qid}'")
        seen_ids.add(qid)

        in_scope = q.get("in_scope")
        diff = q.get("difficulty")
        topic = q.get("topic")

        if in_scope:
            in_scope_count += 1
            diff_counter[diff] += 1
            topic_counter[topic] += 1

            src = q.get("kb_source")
            if not isinstance(src, dict):
                errors.append(f"{qid}: in-scope question must have a kb_source object")
                continue
            vol = src.get("volume")
            ch = src.get("chapter")
            sec = src.get("section")
            if (vol, ch) not in valid_chapters:
                errors.append(
                    f"{qid}: chapter not found in KB — '{vol}' / '{ch}'"
                )
            elif sec and (vol, ch, sec) not in valid_sections:
                warnings.append(
                    f"{qid}: section not found exactly, but chapter OK — "
                    f"'{sec}' under '{ch}'. Precision will still be measurable "
                    f"at chapter granularity."
                )
        else:
            oos_count += 1
            if q.get("kb_source") is not None:
                errors.append(f"{qid}: out-of-scope question must have kb_source=null")
            if topic != "out_of_scope":
                errors.append(f"{qid}: out-of-scope question must have topic='out_of_scope'")

    # Cross-check against the declared distribution in meta.
    declared = meta.get("distribution", {})
    if declared.get("in_scope_total") != in_scope_count:
        errors.append(
            f"meta.distribution.in_scope_total={declared.get('in_scope_total')} "
            f"but actual in-scope count={in_scope_count}"
        )
    if declared.get("out_of_scope_total") != oos_count:
        errors.append(
            f"meta.distribution.out_of_scope_total={declared.get('out_of_scope_total')} "
            f"but actual out-of-scope count={oos_count}"
        )
    for k, v in declared.get("by_difficulty", {}).items():
        if diff_counter[k] != v:
            errors.append(
                f"meta.distribution.by_difficulty.{k}={v} but actual={diff_counter[k]}"
            )
    for k, v in declared.get("by_topic", {}).items():
        if topic_counter[k] != v:
            errors.append(
                f"meta.distribution.by_topic.{k}={v} but actual={topic_counter[k]}"
            )

    print(f"\n[SUMMARY]")
    print(f"  Total questions:     {len(questions)}")
    print(f"  In-scope:            {in_scope_count}")
    print(f"  Out-of-scope:        {oos_count}")
    print(f"  By difficulty:       {dict(diff_counter)}")
    print(f"  By topic:            {dict(topic_counter)}")

    if warnings:
        print("\n[WARNINGS]")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print("\n[ERRORS]")
        for e in errors:
            print(f"  - {e}")
        print(f"\n[FAIL] {len(errors)} error(s) found.")
        return 1

    print("\n[OK] All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())