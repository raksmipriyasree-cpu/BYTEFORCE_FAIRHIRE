"""Ranking helper shared by the Streamlit interface and tests."""
from .ranker import rank_candidates


def rank_job(store, job_id, weights=None, actor="system"):
    """Rank only the resumes currently stored for a role and save explanations."""
    candidates = store.candidates(job_id)
    if candidates.empty:
        return candidates
    ranked = rank_candidates(store.get_job(job_id), candidates[["id", "name", "text"]], weights)
    store.save_ranking(ranked, actor)
    return ranked
