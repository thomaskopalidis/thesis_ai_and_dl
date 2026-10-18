"""
Παράγει το PowerPoint (.pptx) για το meeting με τον Prof. Kachris.
Τρέξε: python docs/generate_presentation.py
Παράγει: docs/Thesis_Progress_Kachris.pptx
"""
from __future__ import annotations
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

OUT = Path(__file__).parent / "Thesis_Progress_Kachris.pptx"

# ── Χρώματα (dark theme για να δένει με το UI) ─────────────────
BG = RGBColor(0x0D, 0x0D, 0x14)       # σχεδόν μαύρο
FG = RGBColor(0xEA, 0xEA, 0xF0)       # ανοιχτό γκρι
ACCENT = RGBColor(0x8B, 0x5C, 0xF6)   # μωβ (όπως το UI)
MUTED = RGBColor(0x9A, 0x9A, 0xA6)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

def add_slide(title: str, bullets: list[str] | None = None, subtitle: str | None = None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    # background
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = BG

    # title
    tx = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12.1), Inches(1.0))
    tf = tx.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(34)
    p.font.bold = True
    p.font.color.rgb = ACCENT

    # subtitle
    y = 1.5
    if subtitle:
        sx = slide.shapes.add_textbox(Inches(0.6), Inches(y), Inches(12.1), Inches(0.5))
        sf = sx.text_frame
        sp = sf.paragraphs[0]
        sp.text = subtitle
        sp.font.size = Pt(18)
        sp.font.italic = True
        sp.font.color.rgb = MUTED
        y += 0.7

    # bullets
    if bullets:
        bx = slide.shapes.add_textbox(Inches(0.8), Inches(y), Inches(11.7), Inches(5.5))
        bf = bx.text_frame
        bf.word_wrap = True
        for i, b in enumerate(bullets):
            para = bf.paragraphs[0] if i == 0 else bf.add_paragraph()
            para.text = f"•  {b}"
            para.font.size = Pt(20)
            para.font.color.rgb = FG
            para.space_after = Pt(10)

    return slide

# ─── SLIDE 1 — Τίτλος ────────────────────────────────────────
s1 = prs.slides.add_slide(prs.slide_layouts[6])
s1.background.fill.solid()
s1.background.fill.fore_color.rgb = BG

tx = s1.shapes.add_textbox(Inches(0.8), Inches(2.0), Inches(11.7), Inches(2.0))
tf = tx.text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
p.text = "AI Assistant"
p.font.size = Pt(60); p.font.bold = True; p.font.color.rgb = ACCENT

p2 = tf.add_paragraph()
p2.text = "Πολυτροπικός Συνομιλητικός Πράκτορας με Ρεαλιστικό Avatar"
p2.font.size = Pt(28); p2.font.color.rgb = FG

p3 = tf.add_paragraph()
p3.text = "για την Εκπαίδευση Φυσικής"
p3.font.size = Pt(28); p3.font.color.rgb = FG

meta = s1.shapes.add_textbox(Inches(0.8), Inches(5.5), Inches(11.7), Inches(1.5))
mf = meta.text_frame
mp = mf.paragraphs[0]
mp.text = "Θωμάς Κωπαλίδης  ·  MSc AI & Deep Learning"
mp.font.size = Pt(18); mp.font.color.rgb = FG

mp2 = mf.add_paragraph()
mp2.text = "Επιβλέπων: Καθ. Χρήστος Καχρής  ·  Πανεπιστήμιο Δυτικής Αττικής"
mp2.font.size = Pt(16); mp2.font.color.rgb = MUTED

mp3 = mf.add_paragraph()
mp3.text = "Παράδοση: Ιανουάριος 2027"
mp3.font.size = Pt(14); mp3.font.italic = True; mp3.font.color.rgb = MUTED

# ─── SLIDE 2 — Πρόβλημα & Κίνητρο ────────────────────────────
add_slide(
    "Το Πρόβλημα",
    subtitle="Γιατί χρειαζόμαστε έναν AI καθηγητή Φυσικής;",
    bullets=[
        "Οι φοιτητές δυσκολεύονται με αφηρημένες έννοιες Φυσικής και χρειάζονται 1-προς-1 υποστήριξη",
        "Τα γενικά LLM chatbots (ChatGPT κ.ά.) παράγουν hallucinations χωρίς αναφορές σε πηγές",
        "Δεν υπάρχει πολυτροπική εμπειρία: ήχος, εικόνα, συνομιλία σε πραγματικό χρόνο",
        "Στόχος: ένας αξιόπιστος AI tutor βασισμένος σε ανοιχτό εκπαιδευτικό υλικό (OpenStax)",
    ],
)

# ─── SLIDE 3 — Αρχιτεκτονική ─────────────────────────────────
add_slide(
    "Αρχιτεκτονική Συστήματος",
    subtitle="Pipeline 5 επιπέδων σε πραγματικό χρόνο",
    bullets=[
        "🎙  STT — faster-whisper (ομιλία → κείμενο)",
        "📚  RAG — ChromaDB + Sentence-Transformers (3.950 chunks από OpenStax)",
        "🧠  LLM — 10+ μοντέλα: local (Ollama) + cloud (Gemini, Groq, OpenRouter)",
        "🔊  TTS — Edge-TTS (κείμενο → φυσική ομιλία)",
        "🎬  Avatar — Wav2Lip lip-sync (video με συγχρονισμένα χείλη)",
        "⚡  Backend: FastAPI + WebSocket streaming (chunked audio/video)",
    ],
)

# ─── SLIDE 4 — Knowledge Base ────────────────────────────────
add_slide(
    "Βάση Γνώσης (Knowledge Base)",
    subtitle="Αξιόπιστο, ανοιχτό εκπαιδευτικό υλικό",
    bullets=[
        "Πηγή: OpenStax University Physics Vol. 1-3 (άδεια CC-BY 4.0)",
        "Chunking: 3.950 κομμάτια × 220 tokens με overlap 32",
        "Embeddings: all-MiniLM-L6-v2 (384 διαστάσεις, γρήγορο & ακριβές)",
        "Αποθήκευση: ChromaDB (local, persistent vector store)",
        "Ανάκτηση: top-k=4 με similarity scoring + metadata (κεφάλαιο, σελίδα)",
        "Κάθε απάντηση συνοδεύεται από citations → μηδενικό hallucination",
    ],
)

# ─── SLIDE 5 — Σύνολο Αξιολόγησης ────────────────────────────
add_slide(
    "Μεθοδολογία Αξιολόγησης",
    subtitle="Αντικειμενικές μετρήσεις, πολλαπλά runs",
    bullets=[
        "33 ερωτήσεις: 30 εντός ύλης (Φυσική) + 3 εκτός ύλης (safety test)",
        "Πολλαπλά runs ανά μοντέλο για έλεγχο διακύμανσης (variance)",
        "Μετρικές: latency ανά στάδιο (STT/RAG/LLM/TTS/Avatar)",
        "Μετρικές ποιότητας: ακρίβεια retrieval, άρνηση εκτός-ύλης, WER",
        "540 runs baseline benchmark (3 LLMs × 30Q × 3 runs × 2 RAG modes)",
        "Full-pipeline benchmark σε 10 μοντέλα (6 local + 4 cloud)",
    ],
)

# ─── SLIDE 6 — Αποτελέσματα ──────────────────────────────────
add_slide(
    "Αποτελέσματα Benchmark",
    subtitle="10 LLMs × 3 πλατφόρμες",
    bullets=[
        "Local (GTX 1650, 4GB): Llama 3.2:3b, Phi-3:mini, Mistral:7b, Llama 3.1:8b, Qwen 2.5:3b/7b",
        "Cloud free-tier: Google Gemini, Groq (gpt-oss-20b/120b, Qwen3.8-27b)",
        "Google Colab T4 (16GB): επαναλήψιμα runs, όλα τα local μοντέλα",
        "UNIWA cluster A100 (20GB MIG): εκκρεμεί kubectl exec permission",
        "Ταχύτερο συνολικό pipeline: Groq gpt-oss-20b (~2s end-to-end)",
        "Καλύτερη τοπική ποιότητα/ταχύτητα: Qwen 2.5:7b",
    ],
)

# ─── SLIDE 7 — Live Demo ─────────────────────────────────────
add_slide(
    "🎬  Live Demo",
    subtitle="Πραγματική επίδειξη του συστήματος",
    bullets=[
        "Platform: Google Colab (T4 GPU) + ngrok tunnel",
        "URL: https://<ngrok>.ngrok-free.app/app/   (κοινόχρηστο)",
        "Default: Qwen 2.5:7b + Edge-TTS   (Avatar OFF για ταχύτητα)",
        "3 ερωτήσεις επίδειξης:",
        "   1.  “What is Newton's second law of motion?”",
        "   2.  “Explain conservation of energy with an example.”",
        "   3.  “What is the capital of France?”  (out-of-scope → άρνηση)",
        "Bonus: Avatar ON → video απάντηση με Wav2Lip",
        "Αναπαραγωγιμότητα: δημόσιο GitHub repo + Colab notebook",
    ],
)

# ─── SLIDE 8 — Roadmap ───────────────────────────────────────
add_slide(
    "Roadmap & Επόμενα Βήματα",
    subtitle="Παράδοση: Ιανουάριος 2027",
    bullets=[
        "✅  Ολοκληρωμένα: KB (3.950 chunks), eval set, multi-provider LLM, benchmarks",
        "🔄  Σε εξέλιξη: benchmarks στο A100 (εκκρεμεί πρόσβαση kubectl exec)",
        "📅  Νοέ–Δεκ: case study / expert evaluation, γραφήματα (PNG @ 300dpi)",
        "📅  Νοέ–Δεκ: συγγραφή Κεφαλαίων 3–8 της διπλωματικής",
        "🎯  Ιαν 2027: υποβολή",
        "",
        "Αιτήματα προς τον επιβλέποντα:",
        "   •  Διευκόλυνση για kubectl exec στο cluster UNIWA (Dr. Garofalaki)",
        "   •  Feedback για το set 33 ερωτήσεων αξιολόγησης",
    ],
)

prs.save(OUT)
print(f"✓ Το PPT αποθηκεύτηκε: {OUT}")
print(f"  Μέγεθος: {OUT.stat().st_size / 1024:.1f} KB")
