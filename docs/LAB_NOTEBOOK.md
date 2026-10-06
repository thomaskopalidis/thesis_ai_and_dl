# LAB_NOTEBOOK — AI Physics Tutor

Χρονολογικό ημερολόγιο εργασίας για τη διπλωματική
**«AI Assistant — A Multimodal Conversational Agent with Realistic Avatar for Physics Education»**
MSc AI & Deep Learning, University of West Attica.

> Νεότερη εγγραφή πάνω. Μία εγγραφή ανά βήμα που ολοκληρώθηκε.
> Γράφεται **μόνο μετά** από επιβεβαίωση ότι το βήμα δούλεψε.

---

## [2026-10-07] Βήμα 1.3b — Διόρθωση ToC extraction (3 950 clean chunks)

- **Στόχος**: Εξάλειψη των ~5 000 duplicate chunks του πρώτου run και σωστή απόδοση `chapter` metadata για κάθε chunk.
- **Τι άλλαξε**:
  - `evaluation/ingest_kb.py`:
    - `EXCLUDE_PATTERNS`: προστέθηκαν 5 νέα patterns — `^chapter outline`, `^contents$`, `^blank page`, `^universityphysicsvolume\d+\.pdf$`, `^chapter\s+\d+\s*$` (για bare `Chapter N` χωρίς τίτλο).
    - `extract_sections_from_pdf()`: πλήρης αναδιάρθρωση. Level-1 entries **ποτέ δεν γίνονται sections** — είναι μόνο labels για το `chapter` metadata των level-2+ children. Το chapter ancestor βρίσκεται παραλείποντας excluded τίτλους (ώστε το auto-generated `UniversityPhysicsVolumeN.pdf` bookmark να μην γίνει chapter label).
  - Το commit θα γίνει μετά το rebuild του index.
- **Εντολές που έτρεξαν**:
  ```powershell
  python evaluation/ingest_kb.py --chunk-size 220 --overlap 32 --preview 5
  ```
- **Αποτελέσματα** (hardware: Windows 11, CPU-only, ~3 λεπτά):

  | Metric | Buggy run (10-07, πρωί) | Fixed run (10-07, βράδυ) | Δ |
  |---|---|---|---|
  | Total chunks | 10 528 | **3 950** | −62.5% (duplicates removed) |
  | Vol.1 / 2 / 3 chunks | 4 309 / 3 448 / 2 771 | 1 612 / 1 265 / 1 073 | |
  | Sections kept V1/V2/V3 | 152 / 145 / 111 | 116 / 111 / 87 | |
  | Mean tokens / chunk | 196.4 | **194.5** | stable |
  | Oversize chunks (>256) | 0 | **0** ✅ | stable |
  | Chapter metadata examples | `UniversityPhysicsVolume1.pdf` ❌ | `Chapter 5 Newton's Laws of Motion` ✅ | fixed |
  | Page ranges per chunk | up to pp.2-959 ❌ | 3-11 σελ. ✅ | fixed |

- **Προβλήματα και πώς λύθηκαν**:
  1. **Fake PDF-level bookmark** (`L1 UniversityPhysicsVolume{1,2,3}.pdf` στην αρχή του ToC, p.1): παραγόταν ξανά ολόκληρο το βιβλίο ως «chapter». Λύση: regex `^universityphysicsvolume\d+\.pdf$` στα EXCLUDE_PATTERNS και αλγοριθμική αναδιάταξη ώστε τα level-1 να μην γίνονται ποτέ sections.
  2. **End-matter noise στο Vol.1** (`L2 Chapter N` entries χωρίς τίτλο στις σελίδες 915-947): regex `^chapter\s+\d+\s*$`.
  3. **Mini-sections χωρίς ουσιαστικό περιεχόμενο** (`Chapter Outline` σε κάθε κεφάλαιο, `Contents`, `Blank Page`): regexes αντίστοιχα.
- **Γνωστός περιορισμός (δεν διορθώνεται σε αυτό το βήμα)**:
  Μαθηματικά σύμβολα (π.χ. θ, μ, φ, υποδείκτες) χάνονται κατά το text extraction από PDF — PyMuPDF `get_text("text")` επιστρέφει κενό στη θέση του glyph. Το RAG retrieval βασίζεται σε περιβαλλοντικές λέξεις, όχι σύμβολα, οπότε αποδεκτό για το πρώτο iteration. Σημειωτέο για **Κεφ. 4 §Limitations**.
- **Για τη διπλωματική**:
  - **Κεφ. 4 §Knowledge base statistics**: τελικά νούμερα (3 950 chunks, 194.5 mean tokens, 0 oversize, 314 sections συνολικά).
  - **Κεφ. 4 §Preprocessing**: ToC-based extraction, λίστα EXCLUDE_PATTERNS, παράδειγμα του auto-generated bookmark bug ως illustration πολυπλοκότητας real-world ingestion.
  - **Κεφ. 4 §Limitations**: text extraction loses math glyphs → semantic retrieval only.

---

## [2026-10-07] Βήμα 1.3 — Πρώτο ingestion του KB (10 528 chunks, εντοπίστηκε bug ToC)

- **Στόχος**: Να χτίσουμε την πρώτη έκδοση του `chunks.jsonl` από τα 3 PDFs του OpenStax με chunking 220 tokens / overlap 32, και metadata από τα PDF bookmarks.
- **Τι άλλαξε**:
  - `evaluation/ingest_kb.py`: προστέθηκε watchdog (max_iters) και fix για infinite loop όταν overlap tail == buffer. Προστέθηκε `tokenizer.model_max_length = int(1e9)` για να σιωπήσει το warning «544 > 512». Προστέθηκε per-section progress κάθε 20 sections για να φαίνεται ότι τρέχει.
  - `evaluation/debug_toc.py`: νέο diagnostic script που εκτυπώνει τα πρώτα 60 ToC entries κάθε PDF, για να διαγνωστεί το chapter-extraction bug.
- **Εντολές που έτρεξαν**:
  ```powershell
  pip install pymupdf==1.24.10
  python evaluation/ingest_kb.py --chunk-size 220 --overlap 32 --preview 5
  ```
- **Αποτελέσματα**:
  - Hardware: Windows 11, Python 3.12.3, CPU-only ingestion
  - Total chunks: **10 528**
  - Mean tokens/chunk: **196.4**
  - Oversize chunks (>256 tokens): **0** ✅
  - Chunks ανά volume: Vol1 = 4 309 | Vol2 = 3 448 | Vol3 = 2 771
  - Sections kept: Vol1 = 152 | Vol2 = 145 | Vol3 = 111
  - Αρχεία που δημιουργήθηκαν: `Knowledge_base/processed/chunks.jsonl`, `Knowledge_base/KB_NOTES.md`
- **Προβλήματα και πώς λύθηκαν**:
  1. **Infinite loop στα τελευταία sections του Vol.1**: το script έτρεχε για πάντα μεταξύ 141/152 και του τέλους. Αιτία: όταν η overlap tail ήταν ίδια με το buffer και το `i` δεν προχωρούσε, το ίδιο chunk emit-αρόταν ατέρμονα. Λύση: έλεγχος `if tail_sents == buf_sents: force-advance i` + watchdog `max_iters = len(sentences) * 4 + 16`.
  2. **Warning «544 > 512»**: τοκενίζαμε ολόκληρες προτάσεις για να μετρήσουμε το μέγεθος. Το warning ήταν cosmetic — δεν σήμαινε bug. Σιώπησε με `tokenizer.model_max_length = int(1e9)`.
  3. **🟡 Ανοιχτό πρόβλημα — chapter metadata σπασμένο**: στο preview, chunks με μεγάλες sections (π.χ. `pp.2-959`) έχουν `chapter = "UniversityPhysicsVolume1.pdf"` αντί για το σωστό όνομα κεφαλαίου. Προκαλείται από level-1 ToC entries χωρίς children (π.χ. το bookmark του αρχείου). Υπολογίζεται ~5 000 chunks έχουν αυτό το πρόβλημα → duplicate content στο ChromaDB. **Το index ΔΕΝ χτίστηκε** για να μη διαδοθεί το bug. Σε εξέλιξη: διάγνωση ToC με `evaluation/debug_toc.py`.
- **Για τη διπλωματική**:
  - **Κεφ. 4 §Knowledge base**: αναφορά των metrics (10 528 chunks, mean 196.4 tokens, 0 oversize).
  - **Κεφ. 4 §Ingestion pipeline**: αρχιτεκτονικό διάγραμμα (PDFs → PyMuPDF → ToC walk → clean → chunk → jsonl → ChromaDB).
  - **Κεφ. 4 Appendix**: παράμετροι chunking (220/32), tokenizer, λίστα εξαιρέσεων (Index/Problems/Appendix…).

---

## [2026-10-04 / 2026-10-06] Βήμα 1.1–1.2 — Στήσιμο ingestion pipeline

- **Στόχος**: Να έχουμε αναπαραγώγιμο pipeline που διαβάζει PDFs OpenStax και παράγει chunks με πλήρη metadata, ώστε η RAG αξιολόγηση να έχει νόημα.
- **Τι άλλαξε**:
  - `requirements.txt`: προστέθηκε `pymupdf==1.24.10`.
  - `evaluation/ingest_kb.py` (νέο): PyMuPDF `get_toc()` → clean text → sentence-aware chunking → `chunks.jsonl`. Παράγει επίσης `KB_NOTES.md`.
  - `evaluation/build_index.py` (νέο): διαγράφει `chroma_db/` και ξαναχτίζει index από `chunks.jsonl`.
  - `Knowledge_base/sources/.gitkeep`, `misc/.gitkeep`: διατήρηση δομής φακέλων στο git.
  - `.gitignore`: εξαιρούνται `Knowledge_base/sources/*.pdf` και `processed/`.
  - Μετονομασία τοπικών PDFs → `openstax_vol1.pdf`, `_vol2.pdf`, `_vol3.pdf`.
  - Commit `4ea4d91` _(feat(kb): ingestion pipeline for OpenStax physics PDFs)_
  - Commit `bde7d29` _(chore(kb): untrack large PDFs, rename to canonical names)_
- **Εντολές που έτρεξαν**:
  ```powershell
  pip install pymupdf==1.24.10
  git init  # (από Βήμα 0)
  git add .  && git commit -m "..."
  ```
- **Αποτελέσματα**: δομή φακέλων έτοιμη, PDFs στη θέση τους, pipeline έτοιμο για το Βήμα 1.3.
- **Προβλήματα και πώς λύθηκαν**:
  - PDFs κατεβήκαν με άλλα ονόματα (`university-physics-volume-1_-_WEB.pdf`) → μετονομάστηκαν στα canonical.
  - Τα PDFs μπήκαν κατά λάθος στο πρώτο commit → bumped out με `git rm --cached` + `.gitignore` rule.
- **Για τη διπλωματική**:
  - **Κεφ. 4 §Data sources**: αναφορά OpenStax Vol 1-3 (CC BY 4.0) + attribution.
  - **Κεφ. 3 §Design decisions**: επιλογή PyMuPDF (ToC bookmarks) έναντι pypdf.

---

## [2026-10-04] Βήμα 0 — Baseline audit του project

- **Στόχος**: Καταγραφή της κατάστασης του project **πριν** από οποιαδήποτε αλλαγή για τη διπλωματική, ώστε να ξέρουμε τι υπήρχε έτοιμο και τι προσθέσαμε.
- **Τι άλλαξε**:
  - `.gitignore` (νέο): secrets, model weights, chroma_db, venv, outputs.
  - `config.py`: ενοποίηση paths — `BASE_DIR / "Knowledge_base"` (με κεφαλαίο, όπως υπάρχει στο disk) ως single source of truth. Προστέθηκαν `CHROMA_COLLECTION_NAME`, `RAG_TOP_K`, `RAG_EMBEDDING_MODEL`, `KNOWLEDGE_BASE_FILE`.
  - `core/rag.py`: διαβάζει paths από `config`, όχι hardcoded. Προστέθηκε `retrieve_with_metadata()` για Precision@k eval.
  - `git init` + 2 baseline commits.
  - Commit `c053bda` _(chore: add .gitignore and unify KB path via config.py)_
  - Commit `c8165a6` _(chore: baseline commit of existing project)_
- **Εντολές που έτρεξαν**:
  ```bash
  git init
  git config user.email "mscaidl-0100@uniwa.gr"
  git config user.name  "Kopalidis Thomas"
  git add .gitignore config.py core/rag.py
  git commit -m "chore: add .gitignore and unify KB path via config.py"
  git add -A ; git rm --cached -f MuseTalk SadTalker Wav2Lip
  git commit -m "chore: baseline commit of existing project"
  curl -s --max-time 3 http://localhost:11434/api/tags
  nvidia-smi -L
  ffmpeg -version
  python --version
  ```
- **Αποτελέσματα**:
  - Hardware: Windows 11, Python 3.12.3, NVIDIA GeForce GTX 1650 (4 GB VRAM), ffmpeg 8.0.1
  - Ollama models pulled: `qwen2.5:14b-instruct-q4_K_M` (9.0 GB), `qwen2.5:7b` (4.7 GB), `gemma3:1b` (0.8 GB)
  - Lipsync status: Wav2Lip ✅ checkpoint στο disk — SadTalker ✅ checkpoints στο disk, untested στο μηχάνημα — MuseTalk ❌ wrapper είναι stub (`core/musictalk_lipsync.py` επιστρέφει κενό mp4)
  - TTS: edge-tts ✅ — chatterbox ⚠️ όχι εγκατεστημένο
  - KB αρχικά: 3 chunks (3 νόμοι Newton) — ανεπαρκές για αξιολόγηση
- **Προβλήματα και πώς λύθηκαν**:
  - Το project δεν ήταν git repo → `git init` + baseline commits.
  - Path mismatch `knowledge_base` (config) vs `Knowledge_base` (disk) → ενοποίηση μέσω config.
- **Αποφάσεις που ελήφθησαν** _(βλ. docs/DECISIONS.md)_:
  - MuseTalk εκτός benchmark αρχικά.
  - Cloud LLM = OpenAI `gpt-4o-mini` (ο φοιτητής βάζει API key).
  - LLM comparison set: `qwen2.5:3b`, `qwen2.5:7b`, `qwen2.5:14b-instruct-q4_K_M`, `llama3.1:8b`, cloud.
- **Για τη διπλωματική**:
  - **Κεφ. 3 §System architecture**: περιγραφή των 5 layers (STT/RAG/LLM/TTS/Avatar) και των wrapper modules.
  - **Κεφ. 4 §Development environment**: Windows local + Kubernetes cluster (A100 MIG 20 GB).
