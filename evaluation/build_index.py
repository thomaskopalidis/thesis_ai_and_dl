"""
Rebuild the ChromaDB index from Knowledge_base/processed/chunks.jsonl.

Separated from ingest_kb.py so chunking can be re-run without re-indexing,
and vice-versa. Running this script DROPS the existing collection and
rebuilds it from scratch to guarantee the index matches the current chunks.

Usage:
  python evaluation/build_index.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

CHUNKS_PATH = config.KNOWLEDGE_BASE_DIR / "processed" / "chunks.jsonl"


def main():
    if not CHUNKS_PATH.is_file():
        print(f"[ERROR] {CHUNKS_PATH} not found. Run ingest_kb.py first.", file=sys.stderr)
        sys.exit(1)

    # Lazy imports — chromadb startup is slow, no reason to pay it on --help.
    import chromadb
    from chromadb.utils import embedding_functions

    # Nuke existing DB so metadata schema changes always take effect.
    db_dir = Path(config.CHROMA_DB_DIR)
    if db_dir.is_dir():
        print(f"[DROP] Removing existing index at {db_dir}")
        shutil.rmtree(db_dir)
    db_dir.mkdir(parents=True, exist_ok=True)

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=config.RAG_EMBEDDING_MODEL
    )
    client = chromadb.PersistentClient(path=str(db_dir))
    col = client.create_collection(config.CHROMA_COLLECTION_NAME, embedding_function=ef)

    documents, ids, metadatas = [], [], []
    with CHUNKS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            documents.append(c["text"])
            ids.append(c["chunk_id"])
            metadatas.append({
                "source": c["source"],
                "volume": c["volume"],
                "chapter": c["chapter"],
                "section": c["section"],
                "page_start": c["page_start"],
                "page_end": c["page_end"],
                "license": c["license"],
                "n_tokens": c["n_tokens"],
            })

    # Add in batches to keep peak memory sensible.
    BATCH = 256
    for i in range(0, len(documents), BATCH):
        col.add(
            documents=documents[i : i + BATCH],
            ids=ids[i : i + BATCH],
            metadatas=metadatas[i : i + BATCH],
        )
        print(f"[INDEX] {min(i + BATCH, len(documents))}/{len(documents)}")

    print(f"\n[DONE] Collection '{config.CHROMA_COLLECTION_NAME}' now has "
          f"{col.count()} chunks.")


if __name__ == "__main__":
    main()
