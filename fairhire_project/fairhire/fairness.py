"""Fairness audit: Demographic Parity, Disparate Impact and twin-rank stability.

Method (counterfactual 'twin' test):
  1. For every applicant create a synthetic twin whose resume is identical except
     the name, gender pronouns and years (a proxy for age) are changed.
  2. Rank originals + twins together, with and without anonymisation.
  3. Shortlist the top k%.  Compare selection rates of female- vs male-coded
     applicants (Demographic Parity difference, Disparate Impact ratio) and
     measure how far each twin's rank moves compared with its original.
A fair pipeline gives parity difference ~0, impact ratio ~1 and rank shift ~0.
"""
import re
import numpy as np
import pandas as pd

from .identity import counterpart_name, infer_gender, swap_pronouns
from .ranker import rank_candidates

_YEAR = re.compile(r"\b(19[6-9]\d|20[0-3]\d)\b")
FOUR_FIFTHS = 0.80

def _shift_years(text, delta=3, cap=2025):
    """Shift every year by `delta` (capped) - a stand-in for an age difference."""
    return _YEAR.sub(lambda m: str(min(int(m.group(1)) + delta, cap)), text)

def make_twins(df):
    """Return originals + twins.  df needs id, name, text and (optionally) gender."""
    pool = df.copy()
    pool["pair_id"] = pool["id"]
    pool["is_twin"] = False
    if "gender" not in pool.columns:
        pool["gender"] = [infer_gender(t, n) for t, n in zip(pool["text"], pool["name"])]
    twins = []
    for _, r in pool.iterrows():
        new_gender = {"female": "male", "male": "female"}.get(r["gender"], "unknown")
        new_name = counterpart_name(r["name"], r["gender"])

        text = r["text"]
        for old, new in zip(r["name"].split(), new_name.split()):

            text = re.sub(r"\b" + re.escape(old) + r"\b",
                          lambda m, new=new: new.lower() if m.group(0).islower() else new, text, flags=re.I)
        text = _shift_years(swap_pronouns(text))
        if r["gender"] in ("female", "male"):
            text = re.sub(r"(?im)^(Gender:\s*)(female|male)", lambda m: m.group(1) + new_gender.capitalize(), text)
        twins.append({"id": f"{r['id']}_twin", "name": new_name, "text": text, "gender": new_gender,
                      "pair_id": r["id"], "is_twin": True})
    return pd.concat([pool, pd.DataFrame(twins)], ignore_index=True)

def audit(job, df, top_percent=20, weights=None, anonymise=True):
    """Run the twin test for one job; returns a metrics dict."""
    pool = make_twins(df)
    ranked = rank_candidates(job, pool[["id", "name", "text"]], weights, anonymise=anonymise)
    ranked = ranked.merge(pool[["id", "gender", "pair_id", "is_twin"]], on="id")
    k = max(1, int(round(len(ranked) * top_percent / 100)))

    ranked["tie_rank"] = ranked["score"].rank(method="min", ascending=False)
    ranked["shortlisted"] = ranked["tie_rank"] <= k

    rates = {}
    for g in ("female", "male"):
        grp = ranked[ranked["gender"] == g]
        rates[g] = float(grp["shortlisted"].mean()) if len(grp) else float("nan")
    hi, lo = max(rates.values()), min(rates.values())
    di = (lo / hi) if hi > 0 else 1.0

    orig = ranked[~ranked["is_twin"]].set_index("pair_id")
    twin = ranked[ranked["is_twin"]].set_index("pair_id").reindex(orig.index)
    shift = (orig["tie_rank"] - twin["tie_rank"]).abs()
    score_gap = (orig["score"] - twin["score"]).abs()
    return {
        "anonymised": anonymise, "pool_size": len(ranked), "shortlist_size": k,
        "selection_rate_female": rates["female"], "selection_rate_male": rates["male"],
        "demographic_parity_diff": float(abs(rates["female"] - rates["male"])),
        "disparate_impact": float(di), "passes_four_fifths": bool(di >= FOUR_FIFTHS),
        "mean_twin_rank_shift": float(shift.mean()), "max_twin_rank_shift": float(shift.max()),
        "mean_twin_score_gap": float(score_gap.mean()),
    }

def before_after(job, df, top_percent=20, weights=None):
    """Audit without and with anonymisation - the 'before / after' comparison."""
    return {"before": audit(job, df, top_percent, weights, anonymise=False),
            "after": audit(job, df, top_percent, weights, anonymise=True)}

def identity_sensitivity_audit(job, candidates, weights=None):
    """Measure whether identity masking changes score/rank for the uploaded resume pool.

    This is a counterfactual sensitivity check, not proof of demographic fairness.
    It does not infer or assign protected-group labels. It compares the same uploaded
    records with the normal blind-review masking path versus unmasked text.
    """
    if candidates.empty:
        return pd.DataFrame(columns=["id", "name", "score_unmasked", "score_masked", "score_delta", "rank_unmasked", "rank_masked", "rank_shift"])
    cols = candidates[["id", "name", "text"]].copy()
    unmasked = rank_candidates(job, cols, weights, anonymise=False)
    masked = rank_candidates(job, cols, weights, anonymise=True)
    merged = unmasked[["id", "score", "rank"]].merge(
        masked[["id", "score", "rank"]], on="id", suffixes=("_unmasked", "_masked"))
    merged = merged.merge(cols[["id", "name"]], on="id", how="left")
    merged["score_delta"] = (merged["score_unmasked"] - merged["score_masked"]).round(2)
    merged["rank_shift"] = (merged["rank_unmasked"] - merged["rank_masked"]).abs()
    return merged.rename(columns={"score_unmasked": "score_unmasked", "score_masked": "score_masked",
                                  "rank_unmasked": "rank_unmasked", "rank_masked": "rank_masked"})[
        ["id", "name", "score_unmasked", "score_masked", "score_delta", "rank_unmasked", "rank_masked", "rank_shift"]
    ].sort_values("rank_masked")
