"""One shared text-similarity function.

The single-resume Analyser and the pool Ranker must never disagree about the
same resume, so both call this module.  The score blends two signals:

  * lexical recall  - the share of the vacancy's content terms that actually
                      appear in the resume.  This is what a human recruiter
                      means by "does this resume talk about the job".
  * distributional  - cosine similarity against the vacancy text, using
                      sentence embeddings when the optional model is
                      installed, otherwise TF-IDF.

Pure TF-IDF alone punishes short resumes and unusual wording, which made good
candidates look weak.  Blending keeps the score interpretable while staying
robust.
"""
import os

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .analyzer import lexical_recall

try:  # optional heavy dependency
    from .semantic import semantic_scores
except Exception:  # pragma: no cover - optional
    semantic_scores = None

EMBEDDING_MODEL = "Sentence Transformers: all-MiniLM-L6-v2"
TFIDF_ENGINE = "TF-IDF cosine + lexical recall blend"


def text_similarity(query, documents):
    """Return (scores, engine_name) for `documents` against `query`."""
    documents = [str(d or "") for d in documents]
    if not documents:
        return np.zeros(0), TFIDF_ENGINE

    recall = np.array([lexical_recall(query, d) for d in documents], dtype=float)

    if semantic_scores is not None and os.environ.get("FAIRHIRE_USE_EMBEDDINGS", "1") != "0":
        try:
            sim = np.clip(np.asarray(semantic_scores(query, documents), dtype=float), 0.0, 1.0)
            return np.clip(0.45 * recall + 0.55 * sim, 0.0, 1.0), EMBEDDING_MODEL
        except Exception:  # model missing or failed to load -> fall through
            pass

    try:
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        mat = vec.fit_transform([query] + documents)
        sim = np.clip(cosine_similarity(mat[0], mat[1:]).ravel(), 0.0, 1.0)
    except ValueError:  # empty vocabulary
        sim = np.zeros(len(documents))
    return np.clip(0.55 * recall + 0.45 * sim, 0.0, 1.0), TFIDF_ENGINE
