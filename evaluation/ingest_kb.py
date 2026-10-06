"""
Knowledge base ingestion pipeline for the physics tutor RAG.

Reads OpenStax University Physics PDFs (and optional NASA .txt sources from
Knowledge_base/sources/misc/), extracts text structured by the PDF's own
table of contents (bookmarks), filters out non-content sections
(Index, Answer Key, Appendices, end-of-chapter Problems), chunks the text
with a sliding window measured in all-MiniLM-L6-v2 subword tokens, and
writes:

  Knowledge_base/processed/chunks.jsonl    one JSON per chunk + metadata
  Knowledge_base/KB_NOTES.md               reproducible summary for the thesis

Does NOT touch the ChromaDB index — that is done by evaluation/build_index.py
so ingestion and indexing can be re-run independently.

Usage:
  python evaluation/ingest_kb.py \
      --chunk-size 220 --overlap 32 --preview 5

CLI parameters are kept explicit so the exact values used for the thesis
experiments are visible in the shell history and in KB_NOTES.md.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Make the project root importable so `import config` works when the script
# is executed from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402


# ---------- Configuration (defaults — overridable via CLI) ---------- #

EMBEDDING_MODEL_NAME = config.RAG_EMBEDDING_MODEL  # "all-MiniLM-L6-v2"
EMBEDDING_MAX_TOKENS = 256  # hard limit of all-MiniLM-L6-v2
DEFAULT_CHUNK_TOKENS = 220
DEFAULT_OVERLAP_TOKENS = 32

SOURCES_DIR = config.KNOWLEDGE_BASE_DIR / "sources"
MISC_DIR = SOURCES_DIR / "misc"
PROCESSED_DIR = config.KNOWLEDGE_BASE_DIR / "processed"
CHUNKS_PATH = PROCESSED_DIR / "chunks.jsonl"
NOTES_PATH = config.KNOWLEDGE_BASE_DIR / "KB_NOTES.md"

# Sections to drop entirely (compiled against lowercased ToC titles).
EXCLUDE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^index$",
        r"^answer key",
        r"^answers to",
        r"^appendix\b",
        r"^references$",
        r"^bibliography$",
        r"^glossary$",         # dense term list hurts retrieval signal
        r"problems$",
        r"^problems\b",
        r"^exercises\b",
        r"challenge problems",
        r"^review\b",
        r"^conceptual questions",
        r"^additional problems",
        r"^chapter review",
        r"^chapter outline",   # learning objectives list, not content
        r"^about openstax",
        r"^about this book",
        r"^preface$",
        r"^contents$",
        r"^blank page",                     # PDF generator artifact
        r"^universityphysicsvolume\d+\.pdf$",# auto-added document-level bookmark
        # 'Chapter N' with no further title (bare entries in end-matter noise)
        r"^chapter\s+\d+\s*$",
    ]
]

# Expected PDF filenames in Knowledge_base/sources/
PDF_FILES = {
    "openstax_vol1.pdf": {"volume": "University Physics Volume 1"},
    "openstax_vol2.pdf": {"volume": "University Physics Volume 2"},
    "openstax_vol3.pdf": {"volume": "University Physics Volume 3"},
}


# ---------- Data classes ---------- #

@dataclass
class Section:
    """A contiguous block of text extracted from one ToC entry."""
    volume: str
    chapter: str          # top-level ToC title (level 1)
    section: str          # nearest ancestor at level 2+, else same as chapter
    page_start: int       # 1-based inclusive
    page_end: int         # 1-based inclusive
    text: str


@dataclass
class Chunk:
    chunk_id: str
    source: str
    volume: str
    chapter: str
    section: str
    page_start: int
    page_end: int
    license: str
    text: str
    n_tokens: int


# ---------- Tokeniser ---------- #

def load_tokenizer():
    """Return the subword tokenizer used by the embedding model."""
    try:
        from transformers import AutoTokenizer
    except ImportError as e:
        print(
            "[ERROR] transformers is required for tokenisation. "
            "It is already a dependency of sentence-transformers, so this "
            "should not happen in a working environment.",
            file=sys.stderr,
        )
        raise e
    name = f"sentence-transformers/{EMBEDDING_MODEL_NAME}"
    tok = AutoTokenizer.from_pretrained(name)
    # Silence the "sequence length is longer than max" warning: we deliberately
    # tokenise long sentences in full to measure their size, then hard-split
    # any sentence that exceeds chunk_tokens inside chunk_section(). The
    # tokenizer's own max_length is irrelevant here.
    tok.model_max_length = int(1e9)
    return tok


# ---------- PDF extraction ---------- #

def is_excluded_title(title: str) -> bool:
    t = title.strip().lower()
    return any(p.search(t) for p in EXCLUDE_PATTERNS)


def extract_sections_from_pdf(pdf_path: Path, volume_label: str) -> list[Section]:
    """
    Build a list of Section objects from a PDF, using its bookmarks (ToC)
    to delimit chapters and sections.

    Design (post-fix, 2026-10-07):
      - get_toc(simple=True) returns [[level, title, page], ...].
      - We ONLY keep level-2+ entries as sections. Level-1 entries ("Chapter N
        Something" or non-content bookmarks like "Contents"/the auto-generated
        PDF-filename bookmark) are never emitted as sections themselves; they
        exist only to label their descendants' `chapter` metadata.
      - For a level-2+ entry, `chapter` = nearest level-1 ancestor that is
        NOT in the exclusion list (so e.g. the stray 'UniversityPhysicsVolume1.pdf'
        root bookmark never becomes a chapter label).
      - Page range for an entry is [page, next_shallower_or_equal_level.page - 1].
      - Entries whose own title matches EXCLUDE_PATTERNS are skipped entirely.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    toc = doc.get_toc(simple=True)  # [[level, title, page], ...] (1-based pages)
    if not toc:
        print(f"  [WARN] {pdf_path.name}: no table of contents found.")
        doc.close()
        return []

    total_pages = doc.page_count
    sections: list[Section] = []

    for i, (level, title, page) in enumerate(toc):
        # 1. Never keep level-1 entries as sections. They are labels only.
        if level < 2:
            continue

        # 2. Skip entries whose own title is non-content.
        if is_excluded_title(title):
            continue

        # 3. Compute page range (end = page before next entry at same-or-shallower level).
        page_end = total_pages
        for j in range(i + 1, len(toc)):
            if toc[j][0] <= level:
                page_end = max(toc[j][2] - 1, page)
                break

        # 4. Find the nearest level-1 ancestor that is NOT excluded.
        chapter = ""
        for k in range(i - 1, -1, -1):
            if toc[k][0] == 1 and not is_excluded_title(toc[k][1]):
                chapter = toc[k][1].strip()
                break
        if not chapter:
            # No valid level-1 ancestor (e.g. 'About OpenStax' under 'Preface').
            # Drop the section; nothing sensible to attribute it to.
            continue

        section_name = title.strip()

        # 5. Extract text for the page range.
        text_parts = []
        for p in range(page - 1, min(page_end, total_pages)):
            try:
                text_parts.append(doc.load_page(p).get_text("text"))
            except Exception as e:
                print(f"  [WARN] {pdf_path.name} page {p+1}: {e}")
        text = clean_text("\n".join(text_parts))

        if len(text) < 200:  # too short to be useful content
            continue

        sections.append(
            Section(
                volume=volume_label,
                chapter=chapter,
                section=section_name,
                page_start=page,
                page_end=page_end,
                text=text,
            )
        )

    doc.close()
    return sections


# ---------- Cleaning ---------- #

_PAGE_NUMBER_LINE = re.compile(r"^\s*\d{1,4}\s*$")
_HEADER_LIKE = re.compile(r"^\s*(chapter\s+\d+\s*\|.+|university physics volume \d+.*)\s*$", re.IGNORECASE)
_MULTI_WS = re.compile(r"[ \t]+")
_HYPHEN_WRAP = re.compile(r"(\w+)-\n(\w+)")  # join hyphenated line-wraps


def clean_text(text: str) -> str:
    """Light cleanup: remove headers/footers/page numbers, join wrapped words."""
    # Join hyphenated line wraps: "accel-\neration" -> "acceleration"
    text = _HYPHEN_WRAP.sub(r"\1\2", text)

    out_lines = []
    for line in text.splitlines():
        if _PAGE_NUMBER_LINE.match(line):
            continue
        if _HEADER_LIKE.match(line):
            continue
        line = _MULTI_WS.sub(" ", line).rstrip()
        out_lines.append(line)

    # Collapse 3+ blank lines
    cleaned = "\n".join(out_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# ---------- Chunking ---------- #

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def split_sentences(text: str) -> list[str]:
    """Split into sentences, keeping terminal punctuation."""
    # First split on paragraph breaks, then on sentence boundaries inside each.
    sentences = []
    for para in _PARAGRAPH_SPLIT.split(text):
        para = para.strip()
        if not para:
            continue
        parts = _SENTENCE_SPLIT.split(para)
        sentences.extend(p.strip() for p in parts if p.strip())
    return sentences


def chunk_section(
    section: Section,
    tokenizer,
    chunk_tokens: int,
    overlap_tokens: int,
) -> Iterable[tuple[str, int]]:
    """
    Yield (chunk_text, n_tokens) tuples for one section, respecting sentence
    boundaries where possible.

    Strategy:
      1. Split section into sentences.
      2. Greedily accumulate sentences until adding the next one would
         exceed chunk_tokens. Emit the chunk.
      3. For overlap, re-prepend the trailing sentences of the previous
         chunk whose combined token count ~= overlap_tokens.
    """
    sentences = split_sentences(section.text)
    if not sentences:
        return

    # Pre-compute token counts per sentence.
    sent_tokens: list[list[int]] = [
        tokenizer.encode(s, add_special_tokens=False) for s in sentences
    ]

    buf_sents: list[int] = []  # indices
    buf_len = 0
    i = 0
    # Watchdog: in the worst case we visit each sentence at most twice
    # (once that triggers an emit, once after overlap). Give some headroom.
    max_iters = len(sentences) * 4 + 16
    iters = 0
    while i < len(sentences):
        iters += 1
        if iters > max_iters:
            # Defensive: emit whatever we have and bail out of this section.
            # This should never fire in practice; if it does we want visible
            # evidence rather than a silent hang.
            print(
                f"  [WARN] chunk_section watchdog tripped at sentence {i}/{len(sentences)}; "
                f"flushing buffer and skipping remainder.",
                flush=True,
            )
            break

        s_len = len(sent_tokens[i])

        # Skip empty sentences (zero tokens): they can appear after cleaning
        # produces things like a stand-alone "." or whitespace-only strings.
        if s_len == 0:
            i += 1
            continue

        # If a single sentence is larger than chunk_tokens, hard-split it.
        if s_len > chunk_tokens:
            if buf_sents:
                yield _emit(sentences, buf_sents, buf_len)
                buf_sents, buf_len = [], 0
            # Hard split by token slice. Guard the step to avoid zero/negative.
            step = max(1, chunk_tokens - overlap_tokens)
            tokens = sent_tokens[i]
            for start in range(0, len(tokens), step):
                piece = tokens[start : start + chunk_tokens]
                yield tokenizer.decode(piece, skip_special_tokens=True), len(piece)
            i += 1
            continue

        if buf_len + s_len <= chunk_tokens:
            buf_sents.append(i)
            buf_len += s_len
            i += 1
        else:
            # Emit current buffer only if it has content.
            if buf_sents:
                yield _emit(sentences, buf_sents, buf_len)

            # Build overlap tail from the end of buf_sents.
            tail_sents: list[int] = []
            tail_len = 0
            for idx in reversed(buf_sents):
                t = len(sent_tokens[idx])
                if tail_len + t > overlap_tokens:
                    break
                tail_sents.insert(0, idx)
                tail_len += t

            # Fix for infinite loop: if the overlap tail is identical to the
            # buffer we just emitted (nothing fit in overlap, or everything
            # fit), AND i has not advanced, we would retry forever. Detect
            # this and force-advance by starting fresh with the current
            # sentence as the only buffer content.
            if tail_sents == buf_sents:
                buf_sents = [i]
                buf_len = s_len
                i += 1
            else:
                buf_sents = list(tail_sents)
                buf_len = tail_len
                # Do NOT advance i — retry current sentence in fresh buffer.

    if buf_sents:
        yield _emit(sentences, buf_sents, buf_len)


def _emit(sentences: list[str], indices: list[int], n_tokens: int) -> tuple[str, int]:
    text = " ".join(sentences[i] for i in indices).strip()
    return text, n_tokens


# ---------- Misc .txt handling ---------- #

_SOURCE_HEADER = re.compile(r"^\s*SOURCE:\s*(?P<url>\S+)\s*\|\s*ACCESSED:\s*(?P<date>.+?)\s*$")


def load_misc_txt(path: Path) -> dict | None:
    """
    Parse a NASA / public-domain .txt file whose first line is:
        SOURCE: <url> | ACCESSED: <date>
    Returns dict with keys: url, accessed, body — or None if malformed.
    """
    with path.open("r", encoding="utf-8") as f:
        first = f.readline()
        m = _SOURCE_HEADER.match(first)
        if not m:
            print(f"  [WARN] {path.name}: missing SOURCE header, skipping.")
            return None
        body = f.read().strip()
    return {"url": m.group("url"), "accessed": m.group("date"), "body": body}


# ---------- Main pipeline ---------- #

def ingest(chunk_tokens: int, overlap_tokens: int, preview: int, seed: int) -> dict:
    tokenizer = load_tokenizer()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks: list[Chunk] = []
    per_source_counts: dict[str, int] = {}
    oversize_count = 0

    # ---- PDFs ----
    for fname, meta in PDF_FILES.items():
        path = SOURCES_DIR / fname
        if not path.is_file():
            print(f"[SKIP] {fname} not found at {path}")
            continue
        print(f"[READ] {fname}", flush=True)
        sections = extract_sections_from_pdf(path, meta["volume"])
        print(f"       → {len(sections)} sections kept (after exclusions)", flush=True)

        file_chunk_count = 0
        n_sections = len(sections)
        for sec_i, section in enumerate(sections):
            # Progress ping every 20 sections so the terminal never looks dead.
            if sec_i % 20 == 0:
                print(
                    f"       chunking section {sec_i + 1}/{n_sections} "
                    f"({file_chunk_count} chunks so far)…",
                    flush=True,
                )
            for ci, (text, n_tok) in enumerate(
                chunk_section(section, tokenizer, chunk_tokens, overlap_tokens)
            ):
                if n_tok > EMBEDDING_MAX_TOKENS:
                    oversize_count += 1
                chunk = Chunk(
                    chunk_id=f"{fname}:{sec_i}:{ci}",
                    source=fname,
                    volume=section.volume,
                    chapter=section.chapter,
                    section=section.section,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    license="CC BY 4.0",
                    text=text,
                    n_tokens=n_tok,
                )
                all_chunks.append(chunk)
                file_chunk_count += 1
        per_source_counts[fname] = file_chunk_count
        print(f"       → {file_chunk_count} chunks")

    # ---- NASA / misc .txt ----
    if MISC_DIR.is_dir():
        for path in sorted(MISC_DIR.glob("*.txt")):
            info = load_misc_txt(path)
            if info is None:
                continue
            print(f"[READ] misc/{path.name}  ({info['url']})")
            # Treat each file as one 'section'. Chapter = filename stem.
            section = Section(
                volume="NASA (public domain)",
                chapter=path.stem.replace("_", " ").title(),
                section=path.stem.replace("_", " ").title(),
                page_start=0,
                page_end=0,
                text=info["body"],
            )
            file_chunk_count = 0
            for ci, (text, n_tok) in enumerate(
                chunk_section(section, tokenizer, chunk_tokens, overlap_tokens)
            ):
                if n_tok > EMBEDDING_MAX_TOKENS:
                    oversize_count += 1
                chunk = Chunk(
                    chunk_id=f"misc/{path.name}:0:{ci}",
                    source=f"misc/{path.name}",
                    volume=f"NASA ({info['url']}, accessed {info['accessed']})",
                    chapter=section.chapter,
                    section=section.section,
                    page_start=0,
                    page_end=0,
                    license="Public domain (NASA)",
                    text=text,
                    n_tokens=n_tok,
                )
                all_chunks.append(chunk)
                file_chunk_count += 1
            per_source_counts[f"misc/{path.name}"] = file_chunk_count
            print(f"       → {file_chunk_count} chunks")

    # ---- Write jsonl ----
    with CHUNKS_PATH.open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    print(f"\n[WRITE] {CHUNKS_PATH}  ({len(all_chunks)} chunks)")

    # ---- Stats ----
    stats = {
        "total_chunks": len(all_chunks),
        "per_source": per_source_counts,
        "oversize_chunks": oversize_count,
        "mean_tokens": (sum(c.n_tokens for c in all_chunks) / len(all_chunks)) if all_chunks else 0,
        "max_tokens": max((c.n_tokens for c in all_chunks), default=0),
        "min_tokens": min((c.n_tokens for c in all_chunks), default=0),
    }

    # ---- Preview ----
    print("\n" + "=" * 70)
    print(f"PREVIEW: {preview} random chunks + 1 chunk containing a formula")
    print("=" * 70)
    rng = random.Random(seed)
    sample = rng.sample(all_chunks, min(preview, len(all_chunks)))
    formula_re = re.compile(r"=\s*[-+]?\d|\b[Ff]\s*=\s*m|[A-Za-z]\s*=\s*[A-Za-z0-9]")
    formula_chunks = [c for c in all_chunks if formula_re.search(c.text)]
    if formula_chunks:
        sample.append(rng.choice(formula_chunks))

    for c in sample:
        print(f"\n--- {c.chunk_id} | {c.volume} | ch='{c.chapter}' | pp.{c.page_start}-{c.page_end} | n_tokens={c.n_tokens} ---")
        print(c.text[:600] + ("…" if len(c.text) > 600 else ""))

    return stats


# ---------- KB_NOTES.md ---------- #

def write_notes(stats: dict, chunk_tokens: int, overlap_tokens: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Knowledge Base — ingestion notes",
        "",
        f"_Generated: {now}_",
        "",
        "## Sources",
        "",
        "| File | Volume | License | Chunks |",
        "|------|--------|---------|--------|",
    ]
    for fname, meta in PDF_FILES.items():
        lines.append(
            f"| `{fname}` | {meta['volume']} | CC BY 4.0 | "
            f"{stats['per_source'].get(fname, 0)} |"
        )
    for src, n in stats["per_source"].items():
        if src.startswith("misc/"):
            lines.append(f"| `{src}` | NASA page | Public domain | {n} |")

    lines += [
        "",
        "## Chunking parameters",
        "",
        f"- Embedding model: `{EMBEDDING_MODEL_NAME}` (max {EMBEDDING_MAX_TOKENS} tokens)",
        f"- Chunk size: **{chunk_tokens} tokens**",
        f"- Overlap: **{overlap_tokens} tokens**",
        "- Boundaries: sentences, then paragraphs (greedy sentence packing)",
        "- Section structure: taken from PDF bookmarks (`PyMuPDF.get_toc()`)",
        "",
        "## Statistics",
        "",
        f"- Total chunks: **{stats['total_chunks']}**",
        f"- Mean tokens / chunk: **{stats['mean_tokens']:.1f}**",
        f"- Min / max tokens: {stats['min_tokens']} / {stats['max_tokens']}",
        f"- Chunks exceeding {EMBEDDING_MAX_TOKENS} tokens (would be truncated): "
        f"**{stats['oversize_chunks']}** (target: 0)",
        "",
        "## Excluded ToC entries",
        "",
        "The following ToC entries are dropped entirely before chunking "
        "(matched case-insensitively against their titles):",
        "",
    ]
    for p in EXCLUDE_PATTERNS:
        lines.append(f"- `{p.pattern}`")

    lines += [
        "",
        "## Attribution (CC BY 4.0)",
        "",
        "This knowledge base contains text adapted from:",
        "",
        "> OpenStax, *University Physics* (Volumes 1, 2, and 3). "
        "Authors: Samuel J. Ling, Jeff Sanny, William Moebs, et al. "
        "Houston, Texas: OpenStax. "
        "Access for free at https://openstax.org/details/books/university-physics-volume-1 "
        "(and corresponding links for volumes 2 and 3). "
        "Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0): "
        "https://creativecommons.org/licenses/by/4.0/",
        "",
        "Modifications made for this thesis:",
        "- Extracted plain text from the official PDF releases.",
        "- Removed non-content sections (index, answer key, appendices, "
        "end-of-chapter problems/exercises).",
        "- Split content into fixed-size overlapping chunks for retrieval.",
        "- No modifications were made to the physics content itself.",
        "",
        "Additional sources under NASA public-domain policy are listed with "
        "their original URL and access date in `Knowledge_base/sources/misc/*.txt`.",
    ]
    NOTES_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[WRITE] {NOTES_PATH}")


# ---------- Entry point ---------- #

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_TOKENS,
                    help="Target chunk size in all-MiniLM-L6-v2 tokens.")
    ap.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP_TOKENS,
                    help="Token overlap between consecutive chunks.")
    ap.add_argument("--preview", type=int, default=5,
                    help="Number of random chunks to print after ingestion.")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if args.chunk_size + args.overlap > EMBEDDING_MAX_TOKENS:
        print(
            f"[ERROR] chunk-size ({args.chunk_size}) + overlap ({args.overlap}) "
            f"> embedding max ({EMBEDDING_MAX_TOKENS}). Reduce chunk-size.",
            file=sys.stderr,
        )
        sys.exit(2)

    stats = ingest(args.chunk_size, args.overlap, args.preview, args.seed)
    write_notes(stats, args.chunk_size, args.overlap)

    print("\n" + "=" * 70)
    print("INGESTION COMPLETE")
    print("=" * 70)
    print(f"Chunks:            {stats['total_chunks']}")
    print(f"Oversize (>{EMBEDDING_MAX_TOKENS}):   {stats['oversize_chunks']}  (must be 0)")
    print(f"Mean tokens:       {stats['mean_tokens']:.1f}")
    print(f"Output:            {CHUNKS_PATH}")
    print(f"Notes:             {NOTES_PATH}")
    print()
    print("Next step: run  python evaluation/build_index.py  to (re)build ChromaDB.")

    if stats["oversize_chunks"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
