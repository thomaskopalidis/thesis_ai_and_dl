import os
import logging
import chromadb
from chromadb.utils import embedding_functions

import config

# Suppress ChromaDB telemetry noise
logging.getLogger("chromadb.telemetry").setLevel(logging.ERROR)

# All paths and settings are centralised in config.py so the same code
# works on Windows (dev) and Linux (K8s cluster).
KB_PATH = str(config.KNOWLEDGE_BASE_FILE)
CHROMA_DIR = str(config.CHROMA_DB_DIR)
COLLECTION_NAME = config.CHROMA_COLLECTION_NAME
TOP_K = config.RAG_TOP_K
EMBEDDING_MODEL = config.RAG_EMBEDDING_MODEL

_collection = None


def _get_collection():
    global _collection
    if _collection is not None:
        return _collection

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    existing = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing:
        _collection = client.get_collection(COLLECTION_NAME, embedding_function=ef)
        print(f"[RAG] Loaded existing collection: {_collection.count()} chunks")
        return _collection

    _collection = client.create_collection(COLLECTION_NAME, embedding_function=ef)
    _index_knowledge_base(_collection)
    return _collection


def _index_knowledge_base(collection):
    if not os.path.isfile(KB_PATH):
        print(f"[RAG] Knowledge base not found at {KB_PATH}")
        return

    with open(KB_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    # Split on blank lines into paragraphs — simple fallback used only when the
    # proper ingestion pipeline (evaluation/ingest_kb.py) has not been run.
    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]

    ids = [f"chunk_{i}" for i in range(len(chunks))]
    collection.add(documents=chunks, ids=ids)
    print(f"[RAG] Indexed {len(chunks)} chunks from knowledge base")


def retrieve(query: str, top_k: int | None = None) -> str:
    """Returns the most relevant KB passages for the query as a single string."""
    try:
        col = _get_collection()
        if col.count() == 0:
            return ""
        k = top_k or TOP_K
        results = col.query(query_texts=[query], n_results=min(k, col.count()))
        docs = results.get("documents", [[]])[0]
        return "\n\n".join(docs)
    except Exception as e:
        print(f"[RAG] Retrieval error: {e}")
        return ""


def retrieve_with_metadata(query: str, top_k: int | None = None) -> dict:
    """
    Same as retrieve() but also returns ids and metadata for each hit.
    Used by the benchmark/evaluation scripts to compute Precision@k and Hit@k.
    """
    try:
        col = _get_collection()
        if col.count() == 0:
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}
        k = top_k or TOP_K
        results = col.query(
            query_texts=[query],
            n_results=min(k, col.count()),
            include=["documents", "metadatas", "distances"],
        )
        return {
            "ids": results.get("ids", [[]])[0],
            "documents": results.get("documents", [[]])[0],
            "metadatas": results.get("metadatas", [[]])[0],
            "distances": results.get("distances", [[]])[0],
        }
    except Exception as e:
        print(f"[RAG] Retrieval error: {e}")
        return {"ids": [], "documents": [], "metadatas": [], "distances": []}
