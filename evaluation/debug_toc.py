"""Diagnostic script: dump the ToC of each OpenStax PDF so we can see
how the ingestion script is interpreting the structure."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

import fitz

for pdf_name in ["openstax_vol1.pdf", "openstax_vol2.pdf", "openstax_vol3.pdf"]:
    path = config.KNOWLEDGE_BASE_DIR / "sources" / pdf_name
    if not path.is_file():
        print(f"[SKIP] {pdf_name}")
        continue

    doc = fitz.open(path)
    toc = doc.get_toc(simple=True)
    print(f"\n{'='*70}\n{pdf_name}  ({doc.page_count} pages, {len(toc)} ToC entries)\n{'='*70}")
    for level, title, page in toc[:60]:
        indent = "  " * (level - 1)
        print(f"  L{level} p{page:4d}  {indent}{title}")
    if len(toc) > 60:
        print(f"  ... ({len(toc) - 60} more entries)")
    doc.close()
