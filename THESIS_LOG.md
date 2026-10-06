# THESIS_LOG — AI Assistant with Realistic Avatar for Physics Education

> **Ημερολόγιο εργασίας** / **Working journal**
>
> Αυτό το αρχείο καταγράφει **όλες τις αποφάσεις, αλλαγές κώδικα, και πειράματα**
> που γίνονται για τη διπλωματική. Οργανωμένο ανά **βήμα του πλάνου εργασίας**
> και με **cross-references στα κεφάλαια της διπλωματικής** (Ch.3, Ch.4, Ch.5).
>
> This file is the single source of truth for the thesis work. Entries written
> to be mostly ready-to-paste into the final thesis in English, with Greek
> commentary explaining rationale and context.
>
> _Last updated: 2026-10-06_
>
> **Student:** Kopalidis, Thomas (AIDL-xxxx)
> **Supervisor:** Prof. Christoforos Kachris
> **Institution:** University of West Attica — MSc in AI & Deep Learning
> **Project title:** AI Assistant — A Multimodal Conversational Agent with
> Realistic Avatar for Physics Education

---

## Table of Contents

- [ΒΗΜΑ 0 — Baseline audit of the existing pipeline](#βημα-0--baseline-audit-of-the-existing-pipeline)
- [ΒΗΜΑ 1 — Knowledge Base construction](#βημα-1--knowledge-base-construction)
- [ΒΗΜΑ 2 — Evaluation question set](#βημα-2--evaluation-question-set) _(pending)_
- [ΒΗΜΑ 3 — Benchmark script](#βημα-3--benchmark-script) _(pending)_
- [ΒΗΜΑ 4 — Analysis](#βημα-4--analysis) _(pending)_
- [ΒΗΜΑ 5 — Thesis-ready notes](#βημα-5--thesis-ready-notes) _(pending)_

**Cross-reference index (για γρήγορη αναζήτηση κατά τη συγγραφή)**:

| Thesis chapter | Relevant log sections |
|---|---|
| Ch.3 System Architecture & Design | §0.1, §0.2, §1.1 |
| Ch.4 Implementation | §0.2, §1.2, §1.3 |
| Ch.5 Experimental Evaluation | §2, §3, §4 _(pending)_ |

---

## ΒΗΜΑ 0 — Baseline audit of the existing pipeline

**Date:** 2026-10-04
**Goal:** Document the state of the system **before** any thesis-evaluation
work, so that later chapters can describe exactly what was already in place
and what was added for the thesis.

### §0.1 Hardware & software environment

> _For Ch.4 §Implementation Environment and Ch.5 §Experimental Setup_

| Component | Value |
|---|---|
| Development machine | Windows 11 Home, Python 3.12.3 |
| Development GPU | NVIDIA GeForce GTX 1650 (4 GB VRAM) |
| Deployment target | University of West Attica Kubernetes cluster, NVIDIA A100 MIG slice `nvidia.com/mig-3g.20gb` (20 GB), 8 CPU, 64 GiB RAM |
| ffmpeg | 8.0.1 (gyan.dev full build) |
| Local LLM runtime | Ollama 0.6.5 at `localhost:11434` |

**Rationale (για το κείμενο της διπλωματικής):** Η επιλογή διπλού περιβάλλοντος
(ανάπτυξη σε consumer-grade GPU + αποτίμηση σε cluster) εξυπηρετεί τον στόχο 2
της διπλωματικής (deployment flexibility, cloud-vs-local trade-offs).

### §0.2 Modules supported by the baseline code

> _For Ch.3 §System Architecture and Ch.4 §Pipeline Components_

Mapping of the five pipeline layers to concrete components in the codebase:

| Layer | Module | Backend | Status at start of thesis work |
|---|---|---|---|
| STT | `core/stt.py` | faster-whisper (`small`, CPU int8) | ✅ Working |
| RAG | `core/rag.py` | ChromaDB + `all-MiniLM-L6-v2` embeddings | ⚠️ Working but KB has only 3 chunks |
| LLM | `core/llm.py` | Ollama (local) + optional OpenAI / Anthropic | ✅ Local works; cloud not configured |
| TTS | `core/tts.py`, `core/chatterbox_tts.py` | Microsoft Edge-TTS; Chatterbox (optional) | ✅ Edge works; Chatterbox not installed |
| Avatar | `core/wav2lip_lipsync.py`, `core/sadtalker_lipsync.py`, `core/musictalk_lipsync.py` | Wav2Lip; SadTalker; MuseTalk | ✅ Wav2Lip; ⚠️ SadTalker untested locally; ❌ MuseTalk wrapper is a stub |

**Pulled local LLM models (via Ollama) at audit time:**
- `qwen2.5:14b-instruct-q4_K_M` (9.0 GB) — default in `.env`
- `qwen2.5:7b` (4.7 GB)
- `gemma3:1b` (0.8 GB)

**Avatar checkpoints verified on disk:**
- Wav2Lip: `wav2lip_gan.pth` (436 MB) ✅
- SadTalker: all required `.pth`/`.pth.tar` files present (≈ 2.9 GB total) ✅
- MuseTalk: model folders exist but the inference wrapper only returns an empty MP4 — **not benchmarkable** without re-implementation.

### §0.3 Issues identified and resolved

> _For Ch.4 §Pre-processing fixes_

| # | Issue | Resolution | Commit |
|---|---|---|---|
| 1 | Project not under version control | `git init` + two baseline commits | `c053bda`, `c8165a6` |
| 2 | Path mismatch: `config.py` used lowercase `knowledge_base`, code used `Knowledge_base` → would break on Linux | Centralised all paths in `config.py` (BASE_DIR / `Knowledge_base`), refactored `core/rag.py` to read from `config` | `c053bda` |
| 3 | `rag.py` lacked a way to return per-chunk metadata for Precision@k | Added `retrieve_with_metadata()` returning ids/metadatas/distances | `c053bda` |
| 4 | Chat history pulled no retrieval metadata, no scoring hooks for RAG eval | Infrastructure now in place via `retrieve_with_metadata()` | `c053bda` |
| 5 | Embedded submodule clones (`Wav2Lip/`, `SadTalker/`, `MuseTalk/`) tracked by git | Excluded via `.gitignore` — cloned manually per environment | `.gitignore` |

### §0.4 Decisions for the thesis evaluation

> _For Ch.5 §Experimental Setup_

Based on the audit, the following decisions were taken (confirmed by supervisor-equivalent review):

1. **MuseTalk is excluded from the main benchmark.** Its wrapper is a stub; integrating it would consume time disproportionate to its marginal contribution. Noted as _future work_.
2. **Cloud LLM** will be included via OpenAI `gpt-4o-mini` as a counterpart to local Ollama models (student provides API key).
3. **LLM comparison set** will be: `qwen2.5:3b`, `qwen2.5:7b`, `qwen2.5:14b-instruct-q4_K_M`, `llama3.1:8b`, cloud. The 3B/8B models must be pulled before benchmarking.
4. **Reproducibility**: every evaluation artifact (chunks, questions, benchmark CSVs, analysis plots) lives under `evaluation/` and is version-controlled.

---

## ΒΗΜΑ 1 — Knowledge Base construction

**Date:** 2026-10-04 — 2026-10-06
**Goal:** Replace the 3-paragraph placeholder knowledge base with a reproducible, licensed, metadata-rich corpus large enough to make RAG evaluation meaningful.

### §1.1 Design decisions

> _For Ch.4 §Knowledge base_

| Decision | Value | Rationale |
|---|---|---|
| Primary source | OpenStax *University Physics* Vol. 1–3 | Open licence (CC BY 4.0), undergraduate level, broad coverage, citable |
| Secondary source | NASA public-domain pages (black holes, Hawking radiation) | Covers "modern physics" items from the student's scope that OpenStax touches only lightly |
| Chunk size | **220 tokens** | all-MiniLM-L6-v2 truncates at 256 subword tokens; 220 leaves headroom for overlap and avoids silent truncation |
| Overlap | **32 tokens** | ≈ 15 %; empirically enough to preserve equations that straddle chunk boundaries |
| Tokeniser | `AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")` | Measured exactly in the units the embedding model will see (not words, not `tiktoken`) |
| Chunk boundaries | Sentence-greedy, falling back to hard token split only when a single sentence exceeds the chunk size | Keeps semantic units intact where possible |
| Chapter / section detection | `fitz.Document.get_toc()` (PDF bookmarks) | Robust to layout changes, no fragile regex over the body text |
| Sections excluded | Index, Answer Key, Appendix, References, Bibliography, Glossary, Problems, Exercises, Review, Challenge Problems, Preface, "About OpenStax" | Non-content pages pollute retrieval signal |
| Sections kept | All chapter prose including worked **Examples** | Examples contain the formulae the Teacher persona needs |
| Per-chunk metadata | `source`, `volume`, `chapter`, `section`, `page_start`, `page_end`, `chunk_id`, `license`, `n_tokens` | Required for Precision@k / Hit@k evaluation and for CC-BY attribution |
| Legacy `physics_kb.txt` | **Not re-indexed** | Kept on disk as historical artifact; new RAG index is built exclusively from `processed/chunks.jsonl` |

**Why PyMuPDF over pypdf:** PyMuPDF (`pymupdf==1.24.10`) extracts text with
higher fidelity for scientific layout (equations, two-column pages) and exposes
the embedded ToC directly via `get_toc(simple=True)`, which pypdf does not do as
cleanly.

### §1.2 Folder structure

```
Knowledge_base/
├── physics_kb.txt              # legacy, not re-indexed
├── sources/
│   ├── openstax_vol1.pdf       # not in git (large)
│   ├── openstax_vol2.pdf
│   ├── openstax_vol3.pdf
│   └── misc/                   # NASA .txt files, each starting with
│                               # 'SOURCE: <url> | ACCESSED: <date>'
├── processed/
│   └── chunks.jsonl            # ingestion output, not in git
└── KB_NOTES.md                 # auto-generated per run
```

### §1.3 Pipeline

> _For Ch.4 §Ingestion pipeline (figure caption candidate)_

Two independent scripts, so chunking and indexing can be re-run separately:

```
PDFs + NASA .txt
      │
      ▼
evaluation/ingest_kb.py          (PyMuPDF → ToC walk → clean → chunk → jsonl)
      │
      ▼
Knowledge_base/processed/chunks.jsonl
      │
      ▼
evaluation/build_index.py        (drops & rebuilds ChromaDB from jsonl)
      │
      ▼
chroma_db/   (consumed by core/rag.py at inference time)
```

**Key implementation details** (for Ch.4):

- `ingest_kb.py` fails loudly (`exit 1`) if any chunk exceeds the embedding
  model's 256-token hard limit — i.e., silent truncation is impossible.
- Light cleanup: joining hyphenated line-wraps (`accel-\neration` →
  `acceleration`), stripping page-number-only lines and running
  volume/chapter headers.
- `build_index.py` deletes `chroma_db/` before rebuilding, so metadata-schema
  changes cannot leave stale documents behind.

### §1.4 Commands actually run

```powershell
# One-time dependency install
pip install pymupdf==1.24.10

# Ingestion (chunking) — parameters locked for the thesis
python evaluation/ingest_kb.py --chunk-size 220 --overlap 32 --preview 5

# Index rebuild (fast; just re-embeds chunks.jsonl)
python evaluation/build_index.py
```

### §1.5 Results — first ingestion run (2026-10-07)

> _For Ch.4 §Knowledge base statistics_

| Metric | Value |
|---|---|
| Total chunks | **10,528** |
| Mean tokens / chunk | **196.4** |
| Chunks exceeding 256 tokens (silent-truncation guard) | **0** ✅ |
| Chunks from Volume 1 (Mechanics / Fluids / Thermodynamics) | 4,309 |
| Chunks from Volume 2 (Thermo / EM / Circuits / Optics) | 3,448 |
| Chunks from Volume 3 (Waves / Modern / Quantum) | 2,771 |
| Pre-chunking sections kept per volume | 152 / 145 / 111 |

**Known problem flagged after the run (fix in progress):**

The preview revealed that several level-1 ToC entries (e.g. a bookmark named
after the PDF filename itself) were kept as giant "chapter" sections spanning
the entire book (`pp. 2-959`), producing ≈ 5 000 duplicated chunks whose
`chapter` metadata is useless (`UniversityPhysicsVolume1.pdf` instead of
e.g. `Chapter 5 Newton's Laws of Motion`). Also, nested headings sometimes
inherit the wrong chapter. A debug script (`evaluation/debug_toc.py`) was
added to inspect the actual ToC structure, and the extraction logic will
be rewritten before indexing. **The ChromaDB index was NOT built from this
run** to avoid propagating the issue downstream.

**Example preview chunks (post-cleanup):** _to be refreshed after the ToC fix._

### §1.6 Licence attribution

The knowledge base contains text adapted from:

> OpenStax, *University Physics* Volumes 1, 2, and 3. Authors: Samuel J. Ling,
> Jeff Sanny, William Moebs, et al. Houston, Texas: OpenStax. Access for free
> at <https://openstax.org/details/books/university-physics-volume-1> (and
> corresponding links for volumes 2 and 3). Licensed under Creative Commons
> Attribution 4.0 International (CC BY 4.0):
> <https://creativecommons.org/licenses/by/4.0/>.

Modifications performed in this thesis:

- Extracted plain text from the official PDF releases via PyMuPDF.
- Removed non-content sections (index, answer key, appendices, end-of-chapter
  problems and exercises).
- Split content into fixed-size overlapping chunks (220 tokens / 32 overlap)
  for retrieval-augmented generation.
- No modifications were made to the physics content itself.

Additional sources under NASA's public-domain policy are listed with their
original URL and access date in `Knowledge_base/sources/misc/*.txt`.

---

## ΒΗΜΑ 2 — Evaluation question set

_Pending (will be filled in when work starts on this step)._

---

## ΒΗΜΑ 3 — Benchmark script

_Pending._

---

## ΒΗΜΑ 4 — Analysis

_Pending._

---

## ΒΗΜΑ 5 — Thesis-ready notes

_Pending._

---

## Appendix — Change log (git commits for the thesis work)

| Commit | Date | Summary |
|---|---|---|
| `c053bda` | 2026-10-04 | chore: add .gitignore and unify KB path via config.py |
| `c8165a6` | 2026-10-04 | chore: baseline commit of existing project |
| _(next)_ | 2026-10-06 | feat(kb): ingestion pipeline for OpenStax physics PDFs |
| _(next)_ | 2026-10-06 | chore(kb): untrack large PDFs, rename to canonical names |

_This table is updated by the assistant after each step._
