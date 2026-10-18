# LAB_NOTEBOOK — AI Physics Tutor

Χρονολογικό ημερολόγιο εργασίας για τη διπλωματική
**«AI Assistant — A Multimodal Conversational Agent with Realistic Avatar for Physics Education»**
MSc AI & Deep Learning, University of West Attica.

> Νεότερη εγγραφή πάνω. Μία εγγραφή ανά βήμα που ολοκληρώθηκε.
> Γράφεται **μόνο μετά** από επιβεβαίωση ότι το βήμα δούλεψε.

---

## [2026-10-18] Avatar σύγκριση — ΒΗΜΑ 0: κοινό interface, Wav2Lip adapter

- **Στόχος**: Κοινή διεπαφή για όλα τα avatar engines (Wav2Lip σήμερα, SadTalker/MuseTalk επόμενα βήματα), με μετρήσιμα πεδία για το benchmark του ΒΗΜΑΤΟΣ 4. Zero regression στο live app.
- **Τι άλλαξε**:
  - `core/avatar_engine.py` (νέο): Protocol `AvatarEngine` + dataclass `LipsyncResult` (video_path, time_s, video_duration_s, fps, peak_vram_mb, load_time_s, prepare_time_s, encode_time_s, engine, base_kind, is_warmup, extra). Helpers: `probe_video`, `VRAMSampler` (nvidia-smi κάθε 200 ms), `reencode_browser_safe` (h264+yuv420p+faststart, μετράει `encode_time_s`), `detect_base_kind` (video/image από extension), `register`/`get`/`available_engines`.
  - `core/engines/__init__.py` + `core/engines/wav2lip.py` + `core/engines/sadtalker.py`: adapters που κάνουν `@register(...)` στο import, με lazy `prepare()`. Υποστήριξη image **και** video base στο Wav2Lip (video → ffmpeg fps-normalize σε 25 fps + cache). `--static True` περνιέται μόνο σε image (bool argparse gotcha στο Wav2Lip/inference.py:23). `resize_factor` παραμετρικό (D-013).
  - `app.py`: ο dispatcher καλεί `avatar_engine.get(name).generate(audio_path)`. Νέο endpoint `/api/engines`. `_AVAILABLE` εκτίθεται στο frontend. Το legacy user-site path (`/tmp/.local/...`) έφυγε από το Wav2Lip env (ο χρήστης το μετακίνησε στο top-level `sys.path.insert` για K8s pods — παραμένει εκεί, όχι μέσα στα engines).
  - `frontend/index.html` + `frontend/main.js`: dropdown lipsync γίνεται dynamic (`<option value="">Loading…</option>`). Νέο `loadEngines()` + `init()` που ανοίγει το WS μόνο αφού φορτωθούν models + engines (αποφεύγει race με άδειο `set_engine`).
  - Διαγραφή: `core/lipsync.py`, `core/musictalk_lipsync.py`, `core/wav2lip_lipsync.py`, `core/sadtalker_lipsync.py` (η λογική τους μεταφέρθηκε στο `core/engines/`).
  - `.gitignore`: `_test_*.mp4` για throwaway test βίντεο.
- **Bugs που εντοπίστηκαν και διορθώθηκαν**:
  1. **Σχετικά paths στα subprocess**: Το Wav2Lip τρέχει με `cwd=WAV2LIP_PATH`, άρα σχετικά paths από το caller αποτύγχαναν σιωπηλά. Λύση: `os.path.abspath` σε όλα τα paths πριν σταλούν στον υποδιαδικασία (`prepare`/`generate`).
  2. **ffmpeg + paths με κενά**: Όταν το audio path περιείχε κενά (π.χ. "AI and DL/Thesis…/evaluation/audio/…"), το Wav2Lip φτιάχνει έναν συνδυασμένο ffmpeg command που κατέληγε σε **σιωπηλά άδειο output** (returncode=0, size=0). Λύση: αντιγραφή του audio σε temp path χωρίς κενά πριν την inference. Το error message πλέον περιλαμβάνει stdout/stderr αντί για γενικό "empty output".
  3. **Edge-TTS 403 Forbidden**: Το edge-tts άρχισε να απαντά 403 στο Microsoft endpoint. Λύση: `pip install -U edge-tts` → **7.2.8** (ήδη αυτή η έκδοση είναι pinned στο `requirements.txt`, άρα για όποιον κάνει fresh install δεν αλλάζει τίποτα· το issue αφορά παλαιότερες εκδόσεις).
- **Μέτρηση — Test 3a** (Wav2Lip σε image, GTX 1650 4 GB, cold subprocess):
  - `time_s = 57.10 s` (περιλαμβάνει model load — βλ. D-012, θα απομονωθεί στο ΒΗΜΑ 2)
  - `video_duration_s = 2.76 s`
  - **RTF ≈ 20.7** (χρόνος / διάρκεια)
  - `peak_vram_mb ≈ 3028 MB`
  - `prepare_time_s = 1.67 s` (image resize/crop, μία φορά)
  - `encode_time_s = 0.27 s`
  - `load_time_s = NaN` (subprocess bundles load+infer)
- **Μέτρηση — Test 3b** (Wav2Lip σε video base):
  - **Συνθήκες**:
    - GPU: Colab T4 (16 GB)
    - Base: 3 s / 75 frames, `-vf "scale=-2:512"`, 25 fps, h264 yuv420p (`_test_video.mp4`)
    - Audio: `_test_audio.wav` (**όχι** `Q05.wav` — δεν υπήρχε στο Colab, βλ. εκκρεμές WER script fix)
    - Ollama: **πιθανότατα σε λειτουργία** (ξεκίνησε στην Ενότητα 1 του notebook πριν το test), άρα η μέτρηση `peak_vram_mb` **δεν είναι αξιόπιστη** για σύγκριση avatar engines (παραβιάζει το D-011).
  - **Ωμά νούμερα** (όπως τυπώθηκαν):
    - Available engines: `['wav2lip']` (SadTalker μη εγκατεστημένο στο Colab image — αναμενόμενο)
    - `[Wav2Lip] Prepared video: /content/thesis_ai_and_dl/_test_video.mp4` → video base cached, καμία re-encode (ήταν ήδη 25 fps)
    - `base_kind = video` ✅
    - `time_s = 52.34 s`
    - `video_duration_s = 2.76 s`
    - `fps = 25.0`
    - `peak_vram_mb = 10 096 MB` (με Ollama ζωντανό — μη αξιόπιστο)
    - `encode_time_s = 0.22 s`
  - **Τι επιβεβαιώθηκε**:
    - `detect_base_kind` επιστρέφει `"video"` για .mp4.
    - Το `--static` **δεν** εμφανίστηκε στο Wav2Lip command (bool argparse gotcha αποφεύχθηκε).
    - Το output video αναπαράγεται σωστά στο Colab (0:03/0:03 στον embedded player).
  - **Τι ΔΕΝ επιβεβαιώθηκε**:
    - Σύγκριση με το Test 3a δεν γίνεται: διαφορετικό GPU (GTX 1650 vs T4), διαφορετική βάση (image vs video), διαφορετικό audio.
    - **Υπόθεση προς έλεγχο στο ΒΗΜΑ 2**: ο χρόνος `time_s` κυριαρχείται από το model load του subprocess (cold-start, D-012). Μέθοδος ελέγχου: cold subprocess vs warm persistent worker, στο **ίδιο GPU, ίδιο audio, ίδια βάση**.
- **Σημείωση για ΒΗΜΑ 4**: τα engines θα μετρηθούν **διαδοχικά** (όχι ταυτόχρονα), με Ollama **σταματημένο** (D-011), ώστε το `peak_vram_mb` να είναι αξιόπιστο.
- **Υστερόχρονη διευκρίνιση — `generate_wer_audio.py`**: Η αρχική αποτυχία («το Q05.wav δεν δημιουργήθηκε») **δεν ήταν bug του script**. Σε επανεκτέλεση στο Colab (μετά από `pip install -U edge-tts` στην ίδια session), το script έτρεξε με exit code 0 και παρήγαγε και τα 10 WAV (Q01, Q03, Q05, Q07, Q10, Q13, Q16, Q22, Q24, Q28) + `transcripts.json`. Αιτία: το κελί είχε τρέξει πριν την εγκατάσταση/αναβάθμιση του edge-tts στη session.
- **Υλοποίηση D-014 — frozen reference set για WER audio**:
  - Νέο `evaluation/sync_wer_audio.py` (helper, callable και τοπικά και στο Colab).
  - Policy: cache στο `<THESIS_ROOT>/audio/synthetic/` στο Drive με `audio_manifest.json`. Σε κάθε session: hash-verify + copy. Αν λείπει κάτι → ERROR (όχι σιωπηλό regen). Rebuild μόνο με `--regenerate`, που **αρχειοθετεί** το παλιό σετ σε `synthetic_archived_<timestamp>/` (δεν σβήνεται ποτέ).
  - Manifest fields ανά WAV: `sha256`, `size_bytes`, `sample_rate_hz`, `channels`, `duration_s`. Top-level: `created_utc`, `edge_tts_version`, `voice`.
  - Το Cell 18.5 του `colab/thesis_colab_clean.ipynb` ενημερώθηκε: καλεί το helper (`--drive <path>`), ρίχνει `RuntimeError` αν το script αποτύχει (κανένα silent fallback).
- **Acceptance tests που πέρασαν**:
  - Import test: `python -c "from core import avatar_engine; print(avatar_engine.available_engines())"` → `['wav2lip', ...]`.
  - App start: `[ENGINE] Available: ['wav2lip', ...] | Default: wav2lip`, καμία import error από τα παλιά modules.
  - E2E στο Colab: Avatar ON + wav2lip → video όπως πριν. Avatar OFF → audio-only (κανόνας που διορθώθηκε νωρίτερα).
- **Για τη διπλωματική**:
  - **Κεφ. 6 §Avatar architecture**: περιγραφή του common interface + registry pattern (δίκαιη βάση σύγκρισης multiple engines).
  - **Κεφ. 7 §Latency decomposition**: η τριμερής διάσπαση (`load / prepare / inference / encode`) θα χρησιμοποιηθεί για να εξηγηθεί γιατί το Wav2Lip φαίνεται αργό σε cold-start subprocess αλλά συγκρίσιμο όταν στρωθεί σε persistent worker (ΒΗΜΑ 2).
- **Επόμενο**: ΒΗΜΑ 1 — SadTalker idle video (idle 8–10 s της δασκάλας με φυσική κίνηση κεφαλιού και blinks). Σημείωση: ο `SadTalkerEngine` σήμερα έχει hard-coded `--still` και `--preprocess crop` — όταν φτάσουμε εκεί, θα γίνουν παράμετροι του constructor.

---

## [2026-10-07] Βήμα 2 — Α1: Synthetic audio για WER (10 wav)

- **Στόχος**: Παραγωγή synthetic audio για 10 από τις 33 ερωτήσεις, ώστε στο ΒΗΜΑ 4 να μετρηθεί WER του Whisper σε «καθαρές» συνθήκες (lower-bound baseline).
- **Τι άλλαξε**:
  - `evaluation/generate_wer_audio.py` (νέο): async script που καλεί edge-tts (Jenny voice) για 10 επιλεγμένες ερωτήσεις και παράγει 16 kHz mono WAV μέσω ffmpeg.
  - `evaluation/audio/synthetic/Q{01,03,05,07,10,13,16,22,24,28}.wav`: 10 αρχεία, 83-275 KB το καθένα (3-8 δευτερόλεπτα).
  - `evaluation/audio/transcripts.json`: reference text για WER measurement (τι «λέει» κάθε wav).
- **Επιλογή των 10 ερωτήσεων**:
  7 από τα 8 topics × μίγμα easy/medium. Οι τύποι-βαρείς hard ερωτήσεις (Q04, Q08, Q15, Q19, Q23) εξαιρέθηκαν γιατί η καταγραφή τύπων σε φωνή είναι άλλο πρόβλημα (STT formula transcription) και αλλοιώνει το WER με thesis-irrelevant θόρυβο.
- **Εντολές που έτρεξαν**:
  ```powershell
  python evaluation/generate_wer_audio.py
  python -c "import sys; sys.path.insert(0, '.'); from core.stt import transcribe_audio; ..."
  ```
- **Αποτελέσματα**:
  - 10 wav αρχεία παρήχθησαν επιτυχώς, όλα 16 kHz mono.
  - Smoke test Whisper (`small`, CPU, int8) σε Q05:
    - REF: `State Newton's first law of motion.`
    - HYP: `State Newton's First Law of Motion.`
    - Διαφορά μόνο σε capitalization (κανονικοποιείται στο WER metric).
  - Το pipeline synthetic-wav → faster-whisper δουλεύει end-to-end.
- **Για τη διπλωματική**:
  - **Κεφ. 5 §STT evaluation**: synthetic WER = Whisper baseline σε κλειστές συνθήκες (TTS → Whisper). Recorded WER (Α2, pending) = ρεαλιστικό scenario (ελληνική προφορά). Διαφορά = STT accent penalty.

---

## [2026-10-07] Βήμα 2 — Σετ αξιολόγησης (eval_questions.json, 33 ερωτήσεις)

- **Στόχος**: Να φτιάξουμε το ground truth πάνω στο οποίο θα μετρηθούν Precision@3, Hit@3, LLM-as-judge correctness, STT WER και refuse-rate.
- **Τι άλλαξε**:
  - `evaluation/eval_questions.json` (νέο): 30 ερωτήσεις φυσικής + 3 εκτός θέματος.
  - `evaluation/validate_questions.py` (νέο): επιβεβαιώνει JSON schema, duplicates, kb_source αντιστοίχιση με το KB, τήρηση δηλωμένης κατανομής.
- **Σχεδιαστικές επιλογές**:
  - `kb_source` ως structured object `{volume, chapter, section}` (όχι flat chunk_id) → σταθερό ακόμα και αν ξανατρέξουμε ingestion. βλ. DECISIONS D-007.
  - Αγγλικά-μόνο ερωτήσεις/απαντήσεις (ευθυγράμμιση με KB και Teacher prompt).
  - WER testing: synthetic (TTS) + ηχογραφημένες από τον φοιτητή (ρεαλιστικό accent). βλ. DECISIONS D-008.
  - 6 ερωτήσεις αναφέρονται σε `section = "Introduction"` όπου η έννοια καλύπτεται από το intro του κεφαλαίου· Precision@3 μετριέται σε chapter granularity για αυτές.
- **Εντολές που έτρεξαν**:
  ```powershell
  python evaluation/validate_questions.py
  ```
- **Αποτελέσματα**:
  - 33 ερωτήσεις, 30 in-scope + 3 out-of-scope.
  - Κατανομή δυσκολίας: easy=12, medium=12, hard=6 ✅
  - Κατανομή topics: kinematics=4, newton_laws=4, energy_momentum=4, fluids=3, thermodynamics=4, electromagnetism=4, waves_optics=4, modern_physics=3 ✅
  - KB cross-check: 44 chapters, 314 sections verified. Όλες οι `kb_source` references αντιστοιχούν σε έγκυρα chapter/section.
  - Validator exit code: 0 — `[OK] All checks passed.`
- **Προβλήματα και πώς λύθηκαν**:
  1. Αρχικό JSON είχε κατανομή easy=13 / hard=5 (λάθος μέτρηση κατά τη σύνταξη). Το Q27 (Doppler effect) μετακινήθηκε από easy σε hard — ταιριάζει καλύτερα γιατί απαιτεί τύπο με division και σκέψη relative motion. Μετά τη διόρθωση: 12/12/6.
- **Για τη διπλωματική**:
  - **Κεφ. 5 §Evaluation protocol**: Πίνακας με την κατανομή ερωτήσεων (topics × difficulty) + αιτιολόγηση του schema.
  - **Κεφ. 5 §Evaluation metrics**: ορισμοί Precision@3, Hit@3, LLM-judge rubric, refuse rate.
  - **Appendix**: ολόκληρο το eval_questions.json ως πίνακας (ή reference σε git commit hash).

---

## [2026-10-07] Βήμα 1.4 — Rebuild ChromaDB + smoke test retrieval

- **Στόχος**: Να φορτώσουμε τα 3 950 clean chunks στο ChromaDB και να επιβεβαιώσουμε end-to-end ότι το RAG retrieval επιστρέφει σωστά metadata.
- **Τι άλλαξε**:
  - `chroma_db/` ξαναχτίστηκε από το μηδέν (drop + rebuild).
  - `core/rag.py`: προστέθηκε `from __future__ import annotations` στην κορυφή για να δουλεύει το `int | None` type syntax κάτω από Python 3.9 (τοπικό venv). PEP 563 lazy evaluation.
- **Εντολές που έτρεξαν**:
  ```powershell
  python evaluation/build_index.py
  python -c "import sys; sys.path.insert(0, '.'); from core.rag import retrieve_with_metadata; r = retrieve_with_metadata('What is Newton second law?', top_k=3); ..."
  ```
- **Αποτελέσματα**:
  - Collection `physics_kb` με **3 950 chunks**.
  - Χρόνος index build: ~2 λεπτά (CPU embeddings, batch=256).
  - Smoke test retrieval για query _"What is Newton second law?"_:
    - Top-3 όλα από `Chapter 5 Newton's Laws of Motion`.
    - Hit@3 ✅ (το section `5.3 Newton's Second Law` επιστράφηκε στο rank 3).
    - Distances: 0.749, 0.827, 0.851.
- **Προβλήματα και πώς λύθηκαν**:
  1. **PEP 604 syntax error σε Python 3.9**: Το smoke test αρχικά απέτυχε με `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`. Το venv τρέχει Python 3.9.12 (όχι 3.12 όπως το global). Λύση: `from __future__ import annotations` → όλα τα type annotations του module γίνονται strings και αξιολογούνται lazy.
  2. **ChromaDB telemetry errors** (`Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given`): γνωστό θέμα με τη βιβλιοθήκη `posthog` που χρησιμοποιεί η Chroma. Δεν επηρεάζει τη λειτουργία — μόνο αναφορά χρήσης. Αγνοείται.
- **Σημείωση περιβάλλοντος για μελλοντικά βήματα**:
  Το τοπικό venv είναι Python 3.9.12. Για το ΒΗΜΑ 3 (benchmark στο cluster) θα χρησιμοποιηθεί 3.11+ (K8s PyTorch base image). Αν προκύψουν νέα modules με PEP 604 syntax, θα πρέπει είτε να προσθέτουμε `from __future__ import annotations` είτε να αναβαθμίσουμε το τοπικό venv σε 3.11.
- **Για τη διπλωματική**:
  - **Κεφ. 4 §RAG implementation**: περιγραφή retrieval pipeline (query → MiniLM embedding → ChromaDB cosine → top-K με metadata).
  - **Κεφ. 5 §Evaluation metrics**: αιτιολόγηση γιατί μετράμε Hit@3 και όχι μόνο Hit@1 (το embedding model επιστρέφει semantically close κείμενα που δεν είναι πάντα το ακριβές section).

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
