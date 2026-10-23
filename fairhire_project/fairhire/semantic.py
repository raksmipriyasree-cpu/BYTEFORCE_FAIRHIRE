"""Semantic retrieval helpers for FairHire.

Uses a pretrained sentence-transformer when available. It does not fine-tune or train
weights. If the model package/model cannot load, the caller can fall back to TF-IDF.
"""
from __future__ import annotations
import os
import re
from functools import lru_cache
from typing import Iterable
import numpy as np

MODEL_NAME = os.environ.get("FAIRHIRE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

@lru_cache(maxsize=1)
def load_encoder():
    """Load the pretrained encoder once per app process (CPU by default)."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME, device="cpu")

def chunk_text(text: str, words_per_chunk: int = 110) -> list[str]:
    """Split long resumes into overlapping text windows to reduce truncation."""
    words = re.findall(r"\S+", text or "")
    if not words:
        return [""]
    step = max(1, words_per_chunk - 20)
    return [" ".join(words[i:i + words_per_chunk]) for i in range(0, len(words), step)]

def semantic_scores(query: str, documents: Iterable[str]) -> np.ndarray:
    """Return 0..1 semantic relevance scores using top-chunk similarity aggregation."""
    encoder = load_encoder()
    q = encoder.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
    scores = []
    for doc in documents:
        chunks = chunk_text(doc)
        vectors = encoder.encode(chunks, normalize_embeddings=True, convert_to_numpy=True,
                                 batch_size=16, show_progress_bar=False)
        similarities = np.clip(vectors @ q, -1.0, 1.0)
        top = np.sort(similarities)[-min(3, len(similarities)):]
        # Cosine can be negative; transform to a bounded 0..1 range.
        scores.append(float(np.clip((float(top.mean()) + 1.0) / 2.0, 0.0, 1.0)))
    return np.asarray(scores, dtype=float)
