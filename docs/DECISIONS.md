# DECISIONS — μεθοδολογικές αποφάσεις για τη διπλωματική

Κάθε απόφαση έχει:
- **Απόφαση**: τι επιλέχθηκε
- **Εναλλακτικές**: τι εξετάστηκε
- **Γιατί**: αιτιολόγηση
- **Πηγή / παραπομπή**: όπου υπάρχει

> Για συνέχειες και αλλαγές στο σχεδιασμό, εγγραφή νεότερη πάνω.

> **Κανόνας εγγραφής**: στο DECISIONS.md και στο LAB_NOTEBOOK.md καταγράφεται μόνο ό,τι έχει μετρηθεί ή επιβεβαιωθεί. Οι εκτιμήσεις σημειώνονται ρητά ως "εκτίμηση".

---

## D-016 — Αλλαγή avatar image σε v2 (AI-generated, 1792×2400) (2026-10-18)

- **Απόφαση**: Από εδώ και πέρα όλα τα avatar engines χρησιμοποιούν το `frontend/assets/teacher_avatar_v2.jpg` (1792×2400, portrait, AI-generated). Η παλιά `teacher_avatar.jpg` (263×350) παραμένει στο repo ως ιστορικό baseline, δεν χρησιμοποιείται σε νέα runs.
- **Παγωμένο artifact (SHA-256)**: `108f28ec760ebc57bb65772ee9cb186fc4b8ed5a51183084b3d65af253c78253`
- **Εργαλείο & prompt** (για reproducibility):
  - **Εργαλείο**: Google Gemini app (image generation), 2026-10-18. **Η ακριβής έκδοση του μοντέλου δεν εκτίθεται από το Gemini**.
  - **Prompt**:
    > "beautiful photorealistic portrait of a Swedish woman university physics lecturer, early 30s, light blonde shoulder-length hair, blue eyes, full natural lips, subtle natural makeup, thin-frame glasses, navy blazer over cream fine-knit top, small silver earrings, head and shoulders, facing camera, calm confident expression, mouth closed, soft natural window light, blurred modern lecture hall, sharp focus, 85mm"
  - **Seed**: δεν παρέχεται από το Gemini → **η εικόνα δεν αναπαράγεται από το prompt**. Reproducibility βασίζεται στο ίδιο το αρχείο (SHA-256 παραπάνω) ως παγωμένο artifact.
- **Χαρακτηριστικά**: Φανταστικό πρόσωπο (όχι υπαρκτό). Γυναίκα με γυαλιά λεπτού σκελετού, μικρά silver σκουλαρίκια, navy blazer πάνω από cream πλεκτή μπλούζα, θολωμένο background αίθουσας.
- **Γιατί αλλάξαμε**:
  - Η παλιά 263×350 ήταν πολύ μικρή. Μετά το face detection + center crop σε 263×263 και re-resize σε 480×480 (Wav2Lip default), το actual face region ήταν εκτίμηση ~80 px στις πρωτογενείς pixel του μοντέλου — πολύ κάτω από τα 96 px που θέλει εσωτερικά το Wav2Lip, εξού και η θολή απόδοση.
  - Για δίκαιη σύγκριση με MuseTalk (που απαιτεί face ~256 px native), χρειαζόμαστε source image που αφήνει αρκετό working resolution ΜΕΤΑ το crop.
- **Working resolution**: ~896×1200 (ο thumbnail με max side 1200 px δίνει 896×1200 διατηρώντας το 3:4 aspect ratio). Face bbox πέφτει εκτίμηση στα ~256-300 px που είναι το native target του MuseTalk. Εφαρμόζεται **μόνο για SadTalker/MuseTalk** — για Wav2Lip το resize_factor θα επανεκτιμηθεί στο ΒΗΜΑ 4.
- **Οπτική επαλήθευση center-square crop (για το Wav2Lip static mode)**: ελέγχθηκε ότι το σημερινό `_prepare_avatar` (center crop σε min_side × min_side) εφαρμοσμένο στη v2 δίνει τέλειο head-and-shoulders frame — ολόκληρο το κεφάλι μέσα, blazer ορατό. Το face είναι τοποθετημένο στο γεωμετρικό κέντρο της εικόνας από design του prompt. **Δεν χρειάζεται face-anchored crop.**
- **Δεν χρησιμοποιήθηκε upscale** (Real-ESRGAN κ.λπ.) — η v2 είναι ήδη source υψηλής ανάλυσης.
- **Γνωστά risk points στο idle video**:
  - Λεπτά γυαλιά → πιθανό morphing από face reenactment του SadTalker. Mitigation: χαμηλό `expression_scale`, οπτικός έλεγχος. **Αποτέλεσμα ΒΗΜΑΤΟΣ 1**: τα γυαλιά διατηρήθηκαν σωστά με `expression_scale=0.5` + `--still` + `preprocess=full` χωρίς GFPGAN.
- **TODO (prod deployment)**: Το [Dockerfile](../Dockerfile) και το [k8s-physics-tutor.yaml](../k8s-physics-tutor.yaml) ακόμα αναφέρουν την παλιά εικόνα. Μετά τη σύγκλιση των avatar πειραμάτων θα ενημερωθούν ώστε το prod image να έχει τη v2.
- **Αναθεώρηση D-013**: η τιμή `resize_factor` του Wav2Lip στο ΒΗΜΑ 4 θα επανεκτιμηθεί — με v2 και working res 896×1200, το default `resize_factor=2` μπορεί να μην είναι βέλτιστο.

---

## D-015 — SadTalker config για idle video της δασκάλας (2026-10-18)

- **Απόφαση**: Το idle video της δασκάλας (σιωπηλό, 10 s @ 25 fps, ping-pong σε ~20 s) παράγεται **μία φορά** με SadTalker και χρησιμοποιείται σε όλα τα downstream MuseTalk runs. Αποθηκεύεται στο Drive, hash-verified (D-014-style policy).
- **Διαδικασία επιλογής ρυθμίσεων** (4 στάδια, όλα εκτελέστηκαν στο Colab T4):
  1. **Σύγκριση 3 clips των 4 s** για επιλογή preprocess mode:
     - (i) `--preprocess full` χωρίς `--still`
     - (ii) `--preprocess extcrop` χωρίς `--still`
     - (iii) `--preprocess full` + `--still`
  2. **Σύγκριση 2 audio inputs** στην επιλεγμένη preprocess mode:
     - (A) πολύ-χαμηλός ροζ θόρυβος @ 16 kHz mono (`anoisesrc=c=pink:a=0.003`)
     - (B) καθαρή σιωπή (`anullsrc`)
  3. **Τελικό clip 10 s** με την επιλεγμένη combination.
  4. **Δύο εκδόσεις** του τελικού: μία χωρίς enhancer, μία με `--enhancer gfpgan`. Οπτική επιλογή της τελικής.
- **Αποτελέσματα επιλογών** (εκτέλεση 2026-10-18, Colab T4, Python 3.13.15, torch 2.11.0+cu130, numpy 2.1.3):
  - **Stage 1 → `full` + `--still`**. Το `extcrop` απορρίφθηκε γιατί παρήγαγε 256×256 output (crop μόνο προσώπου). Το `full` χωρίς still είχε υπερβολική κίνηση κεφαλιού. Το `full + still` κρατάει ήπιες μικροκινήσεις και blinks.
  - **Stage 2 → `pink` θόρυβος**. Μετρήσεις στα 4 s driver: `s2_pink` **97.46 s**, `s2_silence` **97.5 s** (ουσιαστικά ίδιο κόστος), **peak VRAM 2912 MB** και για τα δύο. Οπτικά πανομοιότυπο αποτέλεσμα (οι μικροκινήσεις είναι driven από το face reenactment, όχι από το audio envelope). Επιλέχθηκε το `pink` ως πιο ρεαλιστικό fallback αν αλλάξει μελλοντικά το SadTalker.
  - **Final → χωρίς GFPGAN**. Το GFPGAN κάνει 2× upscale σε 1792×2400 και κοστίζει σημαντικό χρόνο. Για το use case (idle video που θα loop-άρει με το MuseTalk να ξαναζωγραφίζει την περιοχή του στόματος) προέχουν η ταχύτητα απόκρισης και η συνέπεια ανάλυσης με τα downstream engines.
  - **Final 10 s run (`final_pink_none`)**: SadTalker **223.96 s** για 10 s driver, peak **VRAM 3100 MB**, pipeline total **239.43 s**.
- **Promoted asset — παγωμένες τιμές**:
  - Path: `<THESIS_ROOT>/avatar/teacher_idle_25fps.mp4` (+ `teacher_idle_manifest.json`)
  - Resolution: **896×1200**, 25 fps, **20 s playback** (ping-pong), 842 501 bytes
  - **Video SHA-256**: `6f5179af83370d3435898bc29bbc90e2abc9ee60f076cf8b596f72a060be2298`
  - **Source image SHA-256**: `108f28ec760ebc57bb65772ee9cb186fc4b8ed5a51183084b3d65af253c78253` (teacher_avatar_v2.jpg, D-016)
  - **SadTalker commit**: `cd4c0465ae0b54a6f85af57f5c65fec9fe23e7f8`
- **Τελικές SadTalker arguments**:
  - `--source_image`: `teacher_avatar_v2.jpg` (resized σε max 1200 px, aspect-preserved)
  - `--driven_audio`: 10 s pink noise @ 16 kHz mono
  - `--preprocess full`
  - `--still` (ενεργό)
  - `--pose_style 0`
  - `--expression_scale 0.5`
  - `--size 256`
  - **Χωρίς `--enhancer`**
- **Post-processing**: ping-pong loop (forward + reverse concat) → ~20 s βίντεο που κάνει seamless loop. Το σημείο αναστροφής είναι το ίδιο καρέ, άρα δεν υπάρχει ραφή.
- **Policy αναπαραγωγιμότητας** (όπως D-014): παγωμένο asset στο Drive με manifest (SHA-256 του video, SHA-256 του source image, SadTalker config, audio preset, created_utc, SadTalker commit hash). Rebuild μόνο με `--regenerate` που αρχειοθετεί το παλιό.
- **Γιατί "μία φορά"**: αλλαγή idle video → όλα τα MuseTalk benchmarks πρέπει να επανεκτελεστούν. Παγωμένο asset = συγκρίσιμες μετρήσεις στο ΒΗΜΑ 4.

---

## D-014 — Αναπαραγωγιμότητα synthetic audio (Drive-cached + manifest) (2026-10-18)

- **Απόφαση**: Τα 10 synthetic WAV για WER δημιουργούνται **μία φορά** και αποθηκεύονται στο Google Drive (`/content/drive/MyDrive/thesis_ai_and_dl/audio/synthetic/*.wav` + `transcripts.json`). Σε κάθε Colab session, το κελί γέννησης **πρώτα ελέγχει το Drive**: αν τα αρχεία υπάρχουν, τα αντιγράφει στο workspace. Αλλιώς τα παράγει (edge-tts → ffmpeg → WAV 16 kHz mono) και τα σώζει στο Drive. Παράλληλα γράφεται `audio_manifest.json` με: `edge_tts_version`, `voice`, `sample_rate`, `created_utc`, και sha256 hash κάθε WAV.
- **Εναλλακτικές**:
  - Αναγέννηση σε κάθε session: μη ντετερμινιστικό (edge-tts εξαρτάται από το Microsoft endpoint — βλ. το 403 incident στα 2026-10-17/18), αλλάζει το byte-content ανά εκτέλεση ακόμα και με ίδιο κείμενο/φωνή.
  - Repo-committed WAVs: ~10×100 KB = ~1 MB, όχι ιδανικό για git (binary blobs).
- **Γιατί**:
  - **Σταθερό input για WER**: Το Whisper μπορεί να έχει μικρές διαφορές ανά run — αν αλλάζει και το audio byte-for-byte, δεν ξέρουμε ποια είναι η διακύμανση του STT και ποια του TTS.
  - **Audit trail**: Το manifest επιτρέπει να πεις στη διπλωματική "όλα τα WER νούμερα παρήχθησαν από audio φτιαγμένο με edge-tts X.Y.Z, voice `en-US-JennyNeural`, στις DATE" — reproducible.
  - **Ανθεκτικότητα σε endpoint outages**: Αν η edge-tts σπάσει (403, downtime), το benchmark συνεχίζει με τα cached WAV.
- **Σημείωση**: Αν αλλάξει voice ή edge-tts major version και αλλάξει το ακουστικό αποτέλεσμα, γράφεται **νέο** manifest και ξανατρέχει το benchmark από την αρχή (όχι partial updates).

---

## D-013 — Wav2Lip `resize_factor` παράμετρος (2026-10-18)

- **Απόφαση**: Το `resize_factor` του Wav2Lip γίνεται παράμετρος του `Wav2LipEngine`, default **2** όπως στην προηγούμενη υλοποίηση. Στο ΒΗΜΑ 4 η επίδρασή του σε ταχύτητα/ποιότητα θα μετρηθεί, και η τιμή για τη σύγκριση με το MuseTalk θα επιλεγεί ώστε η τελική ανάλυση προσώπου να είναι συγκρίσιμη (**256×256** στόχος, εκτίμηση).
- **Γιατί**: Η resize πριν το face detection επηρεάζει ταυτόχρονα ταχύτητα και ποιότητα. Για δίκαιη σύγκριση ποιότητας (SyncNet LSE-D/LSE-C) στο ΒΗΜΑ 4, τα δύο engines πρέπει να παράγουν frames στην ίδια native resolution.
- **Σημείωση**: Η τιμή που χρησιμοποιήθηκε σε κάθε run καταγράφεται στο `extra.resize_factor` του `LipsyncResult`.
- **ΑΝΟΙΧΤΟ ΠΡΟΒΛΗΜΑ ΓΙΑ ΒΗΜΑ 4 (προστέθηκε 2026-10-18 μετά τη μετάβαση σε v2 — D-016)**:
  Ο σημερινός `Wav2LipEngine._prepare` κάνει **center square crop + resize σε 480×480**. Με τη v2 (1792×2400, face τοποθετημένο κεντρικά), το face bbox μετά το crop/resize πέφτει **εκτίμηση ~130 px** στα 480×480 pixels. Με `resize_factor=2` το Wav2Lip λαμβάνει εσωτερικά 240×240 → face ~65 px. **Δηλαδή ο Wav2Lip ΔΕΝ εκμεταλλεύεται την ανάλυση της v2** — τα pixels του προσώπου είναι λιγότερα από ό,τι θα παρήγαγε και η παλιά 263×350.
  **Για δίκαιη σύγκριση με MuseTalk στο ΒΗΜΑ 4** πρέπει:
  1. Είτε να αυξηθεί η working resolution του Wav2Lip adapter (π.χ. 896×1200 όπως στο SadTalker, aspect-preserved) **και** `resize_factor=1`, ώστε το face να φτάσει τα ~256-300 px native (ίδια τάξη μεγέθους με MuseTalk).
  2. Είτε να γίνει **face-anchored crop** γύρω από το face bbox σε tight region, resize σε 480×480, resize_factor=1 → face σχεδόν γεμίζει το κάδρο → ~400 px.
  Αυτή η αλλαγή θα γίνει στο ΒΗΜΑ 4 μαζί με τις μετρήσεις που θα δικαιολογήσουν την επιλογή. **ΔΕΝ γίνεται τώρα** γιατί θα σπάσει το live app που κάνει fallback στη static-image behavior.

---

## D-012 — Avatar engines ως persistent subprocess workers (2026-10-18)

- **Απόφαση**: Στο ΒΗΜΑ 2, όλα τα avatar engines θα τρέχουν ως **persistent subprocess workers** με κοινό πρωτόκολλο JSON-lines (`core/engines/worker_base.py`). Το μοντέλο φορτώνεται **μία φορά** (`load_time_s`), κάθε πρόταση μετριέται χωριστά (`time_s`).
- **Εναλλακτικές**:
  - In-process import: μολύνει το main app με Wav2Lip/MuseTalk deps, dependency conflicts.
  - Νέο subprocess ανά αίτημα (όπως σήμερα): τεράστιο noise από model load, αδικεί τη σύγκριση.
- **Γιατί**:
  - Οι ίδιες συνθήκες μέτρησης για Wav2Lip και MuseTalk → δίκαιη σύγκριση στη διπλωματική.
  - Απομόνωση εξαρτήσεων (MuseTalk θέλει mmcv/mmpose, Wav2Lip παλαιότερο torch).
  - Health check / auto-restart σε crash — απαραίτητο για long-running demo.
- **Σημείωση ΒΗΜΑΤΟΣ 0**: Προσωρινά το Wav2Lip τρέχει με το σημερινό subprocess-ανά-κλήση (`load_time_s = NaN`). Στο ΒΗΜΑ 2 μεταφέρεται στον worker πρωτόκολλο.

---

## D-011 — Μεθοδολογία μέτρησης avatar (2026-10-18)

- **Απόφαση**:
  - **VRAM**: `nvidia-smi --query-gpu=memory.used` sampling κάθε 200 ms από background thread κατά το `generate()`. `peak_vram_mb = max(samples) − baseline`. Ίδιο για in-process και subprocess engines.
  - **Χρόνοι**: χωριστά `load_time_s` (φόρτωση μοντέλου, μία φορά), `prepare_time_s` (one-off base prep), `time_s` (καθαρό inference, per sentence), `encode_time_s` (ffmpeg re-encode σε h264+yuv420p+faststart, κοινή συνάρτηση `reencode_browser_safe`).
  - **Warm-up**: 1 run ανά engine πριν τα μετρήσιμα runs, flagged `is_warmup=True` στο CSV, εξαιρείται από στατιστικά.
  - **Ollama**: σταματημένο κατά τη σύγκριση avatar engines ώστε η μέτρηση VRAM να μην μολύνεται.
- **Εναλλακτικές**:
  - `torch.cuda.max_memory_allocated()`: ακριβές αλλά τυφλό στα subprocess engines (Wav2Lip, SadTalker, μελλοντικό MuseTalk worker).
  - Μία μόνο μέτρηση χρόνου: μπερδεύει load + infer + encode, αδύνατη η δίκαιη σύγκριση.
- **Γιατί**: Τα engines τρέχουν σε διαφορετικά envs και subprocess types — η μόνη ομοιόμορφη πηγή VRAM μέτρησης είναι ο GPU driver (nvidia-smi). Ο διαχωρισμός χρόνων απομονώνει κάθε συνιστώσα του end-to-end latency.

---

## D-010 — LatentSync εκτός πειραμάτων (2026-10-18)

- **Απόφαση**: Το LatentSync **εξαιρείται από τα πειράματα** της διπλωματικής και αναφέρεται **μόνο στη βιβλιογραφία** ως ανώτερο όριο ποιότητας.
- **Εναλλακτικές**: Υλοποίηση και σύγκριση offline, παρά τον χρόνο εκτέλεσης.
- **Γιατί**: Diffusion πολλών βημάτων inference, δεν είναι real-time (ασυμβίβαστο με το σχεδιαστικό constraint του tutor). Η πρόσθεση ενός offline engine μόνο για benchmark δεν προσφέρει στο narrative "real-time multimodal tutor".

---

## D-009 — Κοινό interface `AvatarEngine` (2026-10-18)

- **Απόφαση**: Όλα τα avatar engines υλοποιούν το Protocol `AvatarEngine` με `is_available() / prepare(base_path) / generate(audio_path, base_path?, out_path?, is_warmup) -> LipsyncResult`. Εγγράφονται σε κεντρικό `ENGINES` registry στο [core/avatar_engine.py](../core/avatar_engine.py). Το app και το benchmark τα καλούν μόνο μέσω του registry.
- **Εναλλακτικές**:
  - Hard-coded dict `{"wav2lip": fn, ...}` στο app.py (η προηγούμενη κατάσταση): δεν δουλεύει για engines με `prepare()` (MuseTalk) ή για το benchmark που θέλει μετρικές.
  - Base class + inheritance αντί Protocol: περιττό boilerplate, καμία ανάγκη για shared state.
- **Γιατί**:
  - Τα engines έχουν διαφορετικά cost profiles: Wav2Lip = static image / ή idle video, μηδενικό ή ελαφρύ prepare. SadTalker = ίδιο αλλά βαρύτερο. MuseTalk = idle video, βαρύ prepare μία φορά, γρήγορο per-sentence inference. Χωρίς `prepare()`/`load_time_s` η σύγκριση είναι άδικη.
  - Το `LipsyncResult` έχει χωριστά πεδία `load_time_s`, `prepare_time_s`, `time_s`, `encode_time_s`, drop-in σε CSV (`as_row()`) για το benchmark του ΒΗΜΑΤΟΣ 4.
  - `is_available()` επιτρέπει στο HP να τρέχει το app χωρίς το MuseTalk (κανόνας D).

---

## D-001 — [ΑΝΑΘΕΩΡΗΣΗ 2026-10-18] MuseTalk επανεντάσσεται ως κύριο engine

- Η αρχική εξαίρεση του MuseTalk (λόγω stub implementation) **ακυρώνεται**. Στο νέο σχέδιο ΒΗΜΑΤΟΣ 2 υλοποιείται πλήρως ως persistent subprocess worker σε ξεχωριστό Python env (mmcv/mmpose), με pre-computed latents του idle βίντεο. Το Wav2Lip παραμένει ως baseline.

---

## D-008 — WER testing: synthetic + recorded audio (2026-10-07)

- **Απόφαση**: Για το STT WER benchmark, για 10 επιλεγμένες ερωτήσεις θα δημιουργηθεί **και** synthetic audio (TTS edge → wav) **και** ηχογραφημένη εκδοχή από τον φοιτητή.
- **Εναλλακτικές**:
  - Μόνο synthetic: ιδανικές συνθήκες, μη ρεαλιστικό για end-user physics tutor.
  - Μόνο real recording: ρεαλιστικό αλλά δεν δίνει καθαρό baseline του Whisper.
- **Γιατί**:
  - Το synthetic audio μας δίνει το **lower-bound WER** του Whisper (τι μπορεί σε ιδανικές συνθήκες).
  - Το real recording μετράει το WER σε ρεαλιστικές συνθήκες (ελληνική προφορά, θόρυβος δωματίου, κινητό μικρόφωνο). Αυτό είναι το πραγματικό scenario χρήσης.
  - Η διαφορά των δύο αριθμών είναι καθαρή ακαδημαϊκή συνεισφορά («το Whisper small χάνει N% ακρίβεια σε non-native accents»).
- **Πηγή**: Radford et al., "Robust Speech Recognition via Large-Scale Weak Supervision" (OpenAI, 2022) — όπου φαίνεται WER breakdown ανά accent subset.

---

## D-007 — Schema του eval_questions.json (2026-10-07)

- **Απόφαση**: Κάθε ερώτηση έχει `kb_source` ως **structured object** `{volume, chapter, section}` και όχι ως flat `chunk_id`.
- **Εναλλακτικές**:
  - Flat `chunk_id`: π.χ. `"openstax_vol1.pdf:29:2"`.
- **Γιατί**:
  - **Σταθερότητα**: αν ξανατρέξουμε ingestion (π.χ. αλλάζουμε chunk size), τα chunk_ids αλλάζουν αλλά τα chapter/section ονόματα παραμένουν σταθερά. Το eval set παραμένει έγκυρο.
  - **Ανάλυση σε πολλαπλά επίπεδα**: μπορούμε να μετρήσουμε Precision@3 στο chapter level **και** στο section level και να αναφέρουμε και τα δύο ως μέρος των ευρημάτων.
  - **Human-readable**: Σε περίπτωση ελέγχου από εξεταστές, το chapter name διαβάζεται άμεσα.
- **Πηγή**: Σχεδιαστική σύμβαση — ανάλογο με structured labels σε datasets όπως SciQ και PubMedQA.

---

## D-006 — ToC filtering rules για OpenStax PDFs (2026-10-07)

- **Απόφαση**: Στο ingestion των OpenStax PDFs:
  1. **Μόνο** level-2+ ToC entries γίνονται sections. Level-1 entries χρησιμοποιούνται ως labels (`chapter` metadata) των children τους.
  2. Αφαιρούμε (EXCLUDE_PATTERNS) τα following non-content ή artifact entries: `Index`, `Answer Key`, `Appendix`, `References`, `Bibliography`, `Glossary`, `Problems`/`Exercises`/`Challenge Problems`, `Review`, `Conceptual Questions`, `Chapter Review`, `Chapter Outline`, `About OpenStax`, `About this book`, `Preface`, `Contents`, `Blank Page`, το auto-generated `UniversityPhysicsVolume\d+\.pdf` bookmark, και bare `Chapter N` χωρίς τίτλο.
  3. Για να βρούμε το `chapter` metadata, αναζητούμε τον κοντινότερο level-1 ancestor που **δεν είναι** στα excluded. Αν δεν βρεθεί, το section πετιέται.
- **Εναλλακτικές**:
  - Να κρατάμε level-1 entries ως standalone sections όταν δεν έχουν children: αυτό ήταν η αρχική υλοποίηση και παρήγαγε duplicates (ένα level-1 bookmark στην p.1 κάθε PDF πιάνει όλο το βιβλίο).
  - Να κάνουμε regex-based chapter detection στο body text: fragile, παραβιάζει τον κανόνα «chapter/section από bookmarks» του πλάνου.
  - Να κρατάμε και το `Chapter Outline`: περιέχει μόνο learning objectives (bullet lists) — προσθέτει θόρυβο στο embedding space χωρίς πληροφορία.
- **Γιατί**:
  - Σωστότητα: duplicate content θα διαστρέβλωνε Precision@3 (δύο διαφορετικά chunk_ids με το ίδιο κείμενο δίνουν ψευδώς υψηλό precision).
  - Αξιοπιστία metadata: ερωτήσεις αξιολόγησης (ΒΗΜΑ 2) αντιστοιχίζονται σε `chapter`/`section` → πρέπει να είναι καθαρά και σταθερά.
- **Επίδραση στα νούμερα**:
  - Chunks: 10 528 → **3 950** (-62.5%).
  - Mean tokens/chunk σταθερό (196.4 → 194.5).
  - Oversize chunks: 0 (σταθερό).
- **Πηγή**: εσωτερική διάγνωση μέσω `evaluation/debug_toc.py` σε όλα τα PDFs (OpenStax University Physics Vol. 1-3).

---

## D-005 — Chunk size 220 tokens, overlap 32 tokens (2026-10-06)

- **Απόφαση**: Chunking με **220 tokens** ανά chunk, **32 tokens** overlap (~15 %), μετρημένα με τον tokenizer του `sentence-transformers/all-MiniLM-L6-v2`.
- **Εναλλακτικές**:
  - 256/0 (full capacity, no overlap): κίνδυνος truncation σε οριακές περιπτώσεις, καμία προστασία για φόρμουλες στα όρια.
  - 512/64 (όπως σε BERT-base RAG tutorials): δεν έχει νόημα — το all-MiniLM-L6-v2 κόβει σιωπηλά στα 256.
  - Word-based / character-based chunking: δεν αντιστοιχεί στα units που βλέπει το μοντέλο.
- **Γιατί**:
  - Το μοντέλο έχει hard limit 256 tokens. Το 220 αφήνει headroom για την overlap tail και για BPE idiosyncrasies.
  - Overlap 32 αρκεί για να εμφανίζεται μια εξίσωση 10–20 tokens και στα δύο γειτονικά chunks αν βρεθεί στα όρια.
  - Το εξασφαλίζουμε με έλεγχο: κανένα chunk > 256 tokens → `oversize_count == 0` (verified: 2026-10-07).
- **Πηγή**: Reimers & Gurevych, "Sentence-BERT" (EMNLP 2019); documentation του `sentence-transformers/all-MiniLM-L6-v2` (`max_seq_length=256`).

---

## D-004 — Embedding model: all-MiniLM-L6-v2 (2026-10-04)

- **Απόφαση**: Χρήση `sentence-transformers/all-MiniLM-L6-v2` ως embedding model.
- **Εναλλακτικές**: `all-mpnet-base-v2` (καλύτερα scores αλλά 3× αργότερο), OpenAI `text-embedding-3-small` (εξάρτηση από cloud + κόστος).
- **Γιατί**:
  - 6-layer MiniLM είναι ~5× ταχύτερο από mpnet-base, κρίσιμο για real-time retrieval.
  - 384-dim embeddings → μικρότερο ChromaDB index.
  - Το 256-token context όριο είναι αρκετό για physics passages μετά το chunking.
  - Υπάρχει ήδη στο baseline project — καμία ρήξη με τον υπάρχοντα κώδικα.
- **Πηγή**: MTEB benchmark leaderboard, HuggingFace model card.

---

## D-003 — PDF extraction: PyMuPDF αντί pypdf (2026-10-06)

- **Απόφαση**: Χρήση `pymupdf==1.24.10` για PDF ingestion.
- **Εναλλακτικές**: `pypdf`, `pdfplumber`, `unstructured`.
- **Γιατί**:
  - Το `fitz.Document.get_toc(simple=True)` εκθέτει τα PDF bookmarks ιεραρχικά, επιτρέποντας robust chapter/section detection χωρίς fragile regex πάνω στο body text.
  - Καλύτερη εξαγωγή κειμένου σε 2-column επιστημονικά layouts.
  - Μικρότερο footprint από `unstructured` (που έχει βαρύ dependency chain).
- **Σημείωση**: τα OpenStax PDFs περιέχουν rich bookmarks → το ToC-based approach είναι εφικτό.

---

## D-002 — Σύνολο μοντέλων για σύγκριση LLM (2026-10-04)

- **Απόφαση**: Benchmark στο ΒΗΜΑ 3 θα συγκρίνει τα παρακάτω LLMs:
  - `qwen2.5:3b` (Ollama, local, small)
  - `qwen2.5:7b` (Ollama, local, medium)
  - `qwen2.5:14b-instruct-q4_K_M` (Ollama, local, large)
  - `llama3.1:8b` (Ollama, local, εναλλακτική οικογένεια)
  - `cloud:openai:gpt-4o-mini` (cloud baseline)
- **Εναλλακτικές**:
  - Μόνο qwen family: δεν θα έδειχνε αν η διαφορά οφείλεται στη family ή στο μέγεθος.
  - Μεγαλύτερο Llama (70B): δεν τρέχει τοπικά, θα έβαζε bias στο cloud comparison.
  - Anthropic Claude: εξετάστηκε αλλά για τον πρώτο γύρο κρατάμε έναν cloud provider για ελεγχόμενο σύνολο.
- **Γιατί**:
  - 3b/7b/14b της ίδιας family → απομονώνει την επίδραση **μεγέθους**.
  - qwen2.5:7b vs llama3.1:8b (παρόμοιο μέγεθος, διαφορετική family) → απομονώνει την επίδραση **family/training**.
  - Cloud → baseline σύγκρισης state-of-the-art.
- **Πηγή**: Σχεδιασμός ανάλογος με Ouyang et al., "GPT-3 scaling laws" και πρακτικές σε evaluation surveys.

---

## D-001 — MuseTalk εκτός αρχικού benchmark (2026-10-04)

- **Απόφαση**: Το MuseTalk **εξαιρείται** από το κύριο benchmark του ΒΗΜΑΤΟΣ 3.
- **Εναλλακτικές**: Υλοποίηση κανονικού wrapper τώρα, πριν τα πειράματα.
- **Γιατί**:
  - Ο υπάρχων wrapper (`core/musictalk_lipsync.py`) είναι stub (επιστρέφει κενό mp4).
  - Η πλήρης υλοποίηση απαιτεί τουλάχιστον 1-2 ημέρες εργασίας (model loading, VAE encode, UNet denoise loop, blending back).
  - Προτεραιότητα: solid comparison Wav2Lip vs SadTalker (τα δύο που ήδη δουλεύουν). Το MuseTalk μπορεί να μπει ως future work ή επέκταση αν υπάρχει χρόνος.
- **Αναθεώρηση**: Αν ολοκληρωθεί νωρίς το ΒΗΜΑ 4, θα επανεξεταστεί.
