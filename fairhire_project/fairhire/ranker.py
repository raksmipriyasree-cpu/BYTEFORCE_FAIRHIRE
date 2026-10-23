"""Scoring, ranking and exact additive explanations.

Score (0-100) = 100 * sum(weight_i * feature_i) over five features in [0, 1]:
  skill_match  weighted coverage of the role's CORE competencies (evidence-based)
  nice_skills  weighted coverage of PREFERRED competencies
  experience   years detected / years the role asks for (capped at 1)
  education    highest degree level / level the role asks for (capped at 1)
  text_match   semantic similarity when available; otherwise TF-IDF cosine

Explanations: because the model is linear, the exact contribution of feature i
for one candidate is  weight_i * (x_i - mean_i) * 100, where mean_i is the
average over the applicant pool.  Contributions + base value add up exactly to
the score, so every ranking can be explained with zero approximation.

Every candidate also carries a full evidence trail (per-competency matched
phrases and quoted sentences), a plain-language verdict with reasons for and
against, counterfactuals, confidence and resume-improvement feedback.
"""
import os
import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from .semantic import semantic_scores
except Exception:  # optional model dependency
    semantic_scores = None

from .analyzer import (
    DEFAULT_WEIGHTS,
    FEATURES,
    build_feedback,
    build_verdict,
    evaluate_candidate,
    job_query,
    lexical_recall,
)
from .anonymizer import anonymize
from .similarity import text_similarity
from .taxonomy import get_profile


def _normalise_weights(weights):
    """Make the weights sum to 1 so scores stay on a 0-100 scale."""
    w = {f: max(float((weights or DEFAULT_WEIGHTS).get(f, 0.0)), 0.0) for f in FEATURES}
    total = sum(w.values()) or 1.0
    return {f: v / total for f, v in w.items()}


def _job_query(job):
    return job_query(job)


def _text_similarity(job, documents):
    """Return (scores, engine_name) using the same function as the Analyser."""
    return text_similarity(job_query(job), list(documents))


def rank_candidates(job, candidates, weights=None, anonymise=True):
    """Rank candidates for one job and attach a full explanation to each row.

    job        dict with title, description, required, nice, min_years, min_edu
    candidates DataFrame with columns id, name, text
    anonymise  True  -> text similarity uses identity-masked resumes (default)
               False -> raw text (used only by the fairness audit to show 'before')
    """
    w = _normalise_weights(weights)
    cands = candidates.reset_index(drop=True)
    if cands.empty:
        return cands

    evaluations = [evaluate_candidate(str(c["text"] or ""), job) for _, c in cands.iterrows()]

    used = [anonymize(str(t), n) if anonymise else str(t)
            for t, n in zip(cands["text"], cands["name"])]
    sim, engine = _text_similarity(job, used)

    rows = []
    for i, ev in enumerate(evaluations):
        features = dict(ev["features"])
        features["text_match"] = float(sim[i])
        rows.append({
            **features,
            "matched": [c["label"] for c in ev["criteria"] if c["core"] and c["matched"]],
            "missing": [c["label"] for c in ev["criteria"] if c["core"] and not c["matched"]],
            "bonus": [c["label"] for c in ev["criteria"] if not c["core"] and c["matched"]],
            "detected_skills": ev["parsed"]["skills"],
            "years": ev["years"],
            "core_coverage": ev["core_coverage"],
            "preferred_coverage": ev["preferred_coverage"],
            "education_level": ev["education_level"],
            "ats_score": ev["parsed"]["ats_score"],
        })
    feat = pd.DataFrame(rows)

    X = feat[FEATURES].to_numpy(dtype=float)
    wv = np.array([w[f] for f in FEATURES])
    scores = X @ wv * 100
    base = float(X.mean(axis=0) @ wv * 100)
    contribs = (X - X.mean(axis=0)) * wv * 100

    out = cands[["id", "name"]].copy()
    out["score"] = np.round(scores, 2)
    for f in FEATURES:
        out[f] = np.round(feat[f], 4)
    for col in ("matched", "missing", "bonus", "detected_skills", "years",
                "core_coverage", "preferred_coverage", "education_level", "ats_score"):
        out[col] = feat[col]

    # Build verdict + feedback per candidate, now that the final score is known.
    verdicts, feedbacks, criteria_all, parsed_all = [], [], [], []
    for i, ev in enumerate(evaluations):
        ev["features"] = {**ev["features"], "text_match": float(sim[i])}
        verdict = build_verdict(ev, float(scores[i]), weights, role=job.get("title", ""))
        feedback = build_feedback(ev, verdict)
        verdicts.append(verdict)
        feedbacks.append(feedback)
        criteria_all.append(ev["criteria"])
        parsed_all.append({
            "name": ev["parsed"]["name"],
            "email": ev["parsed"]["email"],
            "phone": ev["parsed"]["phone"],
            "links": ev["parsed"]["links"],
            "section_names": ev["parsed"]["section_names"],
            "word_count": ev["parsed"]["word_count"],
            "total_years": ev["parsed"]["total_years"],
            "experience": ev["parsed"]["experience"],
            "education": ev["parsed"]["education"],
            "education_label": ev["parsed"]["education_label"],
            "skills": ev["parsed"]["skills"],
            "quantified": ev["parsed"]["quantified"],
            "bullet_lines": ev["parsed"]["bullet_lines"],
            "action_verbs": ev["parsed"]["action_verbs"],
            "ats": ev["parsed"]["ats"],
            "ats_score": ev["parsed"]["ats_score"],
        })

    out["criteria"] = criteria_all
    out["verdict"] = verdicts
    out["feedback"] = feedbacks
    out["parsed"] = parsed_all
    out["confidence"] = [v["confidence"] for v in verdicts]
    out["recommendation"] = [v["label"] for v in verdicts]
    out["contribs"] = [dict(zip(FEATURES, np.round(row, 2))) for row in contribs]
    out["base_value"] = round(base, 2)
    out["matching_engine"] = engine
    out = out.sort_values(["score", "id"], ascending=[False, True], kind="stable").reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out


def verify_with_shap(job, candidates, weights=None):
    """Optional cross-check against shap.LinearExplainer (needs the shap package)."""
    try:
        import shap
    except ImportError:
        return None
    ranked = rank_candidates(job, candidates, weights)
    w = _normalise_weights(weights)
    X = ranked[FEATURES].to_numpy(dtype=float)
    coef = np.array([w[f] for f in FEATURES]) * 100
    explainer = shap.LinearExplainer((coef, 0.0), X)
    shap_values = explainer.shap_values(X)
    ours = np.array([[c[f] for f in FEATURES] for c in ranked["contribs"]])
    return float(np.abs(shap_values - ours).max())


def precision_at_k(ranked, labels, target, k=10):
    """Share of the top-k ranked candidates whose true category equals `target`."""
    top = ranked.head(k)["id"].tolist()
    return sum(labels.get(i) == target for i in top) / max(len(top), 1)
