"""Deep, evidence-backed resume analysis for FairHire.

This module turns raw resume text into a structured, inspectable decision:

  parse_resume(text)                 -> contact details, sections, dated roles,
                                        education, skills, achievements, ATS checks
  evaluate_candidate(text, job)      -> per-competency evidence + five score features
  build_verdict(...)                 -> plain-language decision, reasons FOR and
                                        AGAINST, counterfactuals, confidence, feedback

Design principles
-----------------
* Evidence over keywords: every matched competency carries the sentence that
  triggered it, so a reviewer can check the claim.
* No identity signals: scoring only reads competencies, dates, degrees and role
  language.  Names, gender, age, institution and location are not features.
* No automatic rejection: the weakest outcome is "limited evidence - human
  review needed".  A person always makes the final call.
"""
from __future__ import annotations

import re
from collections import OrderedDict

from .skills import (
    education_label,
    extract_education_level,
    extract_skills,
    extract_years_experience,
)
from .taxonomy import get_profile

FEATURES = ["skill_match", "nice_skills", "experience", "education", "text_match"]
DEFAULT_WEIGHTS = {"skill_match": 0.45, "nice_skills": 0.10, "experience": 0.15,
                   "education": 0.10, "text_match": 0.20}

# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d{6,10}(?!\w)")
_LINK = re.compile(r"(?:https?://|www\.)\S+|(?:linkedin\.com|github\.com|behance\.net|dribbble\.com)/\S+", re.I)

_SECTION_PATTERNS = OrderedDict([
    ("summary", r"summary|profile|objective|career overview|about me|professional summary"),
    ("skills", r"skills|technical skills|core competencies|competencies|expertise|qualifications|areas of expertise"),
    ("experience", r"work experience|professional experience|employment|experience|career history|work history"),
    ("education", r"education|academic|training|qualifications|educational background|education and training|education & training|academic background"),
    ("projects", r"projects|selected projects|portfolio|case studies"),
    ("certifications", r"certifications?|certificates?|licen[cs]es?|courses"),
    ("achievements", r"achievements?|awards?|honors?|honours?|accomplishments"),
    ("languages", r"languages?"),
    ("references", r"references?"),
    ("interests", r"interests|hobbies"),
])

_HEADING_ONLY = re.compile(r"^[A-Za-z][A-Za-z &/,\-]{1,45}$")
_ACTION_VERBS = re.compile(
    r"\b(?:led|managed|built|designed|developed|implemented|created|delivered|improved|reduced|increased|"
    r"launched|tested|analysed|analyzed|automated|coordinated|co-ordinated|trained|mentored|resolved|"
    r"optimised|optimized|streamlined|established|planned|conducted|maintained|supported|achieved)\b", re.I)
_QUANTIFIED = re.compile(r"(?:\d+(?:\.\d+)?\s?%|\$\s?\d|₹\s?\d|\b\d{2,}\b|\b\d+(?:\.\d+)?\s?(?:x|times)\b)", re.I)


def _clean(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def split_sentences(text):
    """Split text into readable sentence/bullet units, preserving meaning."""
    text = _clean(text)
    parts = re.split(r"(?<=[.!?;])\s+|\n+|\s*[•▪◦●]\s*", text)
    out = []
    for p in parts:
        p = p.strip(" -–—\t")
        if len(p) >= 12:
            out.append(p)
    return out


def _first_snippet(text, term, max_len=230):
    """Return the sentence around the first occurrence of `term`."""
    pattern = re.compile(r"(?<![\w+#.])" + re.escape(term) + r"(?![\w+#])", re.I)
    match = pattern.search(text or "")
    if not match:
        return None
    start = max(0, match.start() - 110)
    end = min(len(text), match.end() + 130)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if start > 0:
        # Trim the partial word the window cut in half, so quotes start cleanly.
        head = snippet.split(" ", 1)
        snippet = head[1] if len(head) > 1 else snippet
        snippet = "…" + snippet
    if end < len(text):
        tail = snippet.rsplit(" ", 1)
        snippet = tail[0] if len(tail) > 1 else snippet
        snippet = snippet + "…"
    return snippet[:max_len]


def _detect_sections(text):
    lines = text.splitlines()
    sections = OrderedDict()
    current = "preamble"
    sections[current] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        candidate = line.strip(" :•-–—").lower()
        matched = None
        if len(line) <= 55 and _HEADING_ONLY.match(line):
            for key, pattern in _SECTION_PATTERNS.items():
                if re.fullmatch(pattern, candidate, re.I):
                    matched = key
                    break
        if matched:
            current = matched
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if v}


def _parse_experience(text, experience_text):
    """Return dated role blocks plus a total-years estimate."""
    source = experience_text or text
    matches = list(re.finditer(
        r"(?:(?:0?[1-9]|1[0-2])[/-](?:19|20)\d{2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(?:19|20)\d{2}|(?:19|20)\d{2})"
        r"\s*(?:to|until|through|–|—|-)\s*"
        r"(?:(?:0?[1-9]|1[0-2])[/-](?:19|20)\d{2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(?:19|20)\d{2}|(?:19|20)\d{2}|present|current|now|today)",
        source, re.I))
    roles = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(source), m.end() + 420)
        block = source[m.start():end].strip()
        block = re.sub(r"\s+", " ", block)
        roles.append({"period": m.group(0).strip(), "block": block[:400]})
    total_years = extract_years_experience(text)
    return roles, total_years


def _parse_education(education_text, text):
    source = education_text or text
    entries = []
    for sentence in split_sentences(source):
        if re.search(r"bachelor|master|ph\.?d|doctorate|m\.?sc|b\.?sc|m\.?tech|b\.?tech|mba|b\.?e\b|bca|b\.?com", sentence, re.I):
            entries.append(sentence[:260])
    return entries[:6]


def _ats_checks(parsed):
    text = parsed["text"]
    checks = [
        ("Email address found", bool(parsed["email"]), "Recruiters need a reliable way to reply."),
        ("Phone number found", bool(parsed["phone"]), "A contact number helps scheduling."),
        ("Online profile or portfolio link", bool(parsed["links"]), "A LinkedIn, GitHub or portfolio link adds verifiable evidence."),
        ("Summary or profile section", "summary" in parsed["sections"], "A short summary helps a reader place the resume in 10 seconds."),
        ("Skills section", "skills" in parsed["sections"], "A dedicated skills section makes capabilities easy to scan and parse."),
        ("Work experience section", "experience" in parsed["sections"], "Dated roles let the system verify real experience."),
        ("Education section", "education" in parsed["sections"], "Education should be easy to locate."),
        ("Dated work history", len(parsed["experience"]) >= 1, "Date ranges let experience be calculated, not guessed."),
        ("Readable length (250–1,000 words)", 250 <= parsed["word_count"] <= 1000,
         f"Current length: {parsed['word_count']} words."),
        ("Quantified achievements (2+)", len(parsed["quantified"]) >= 2,
         f"Found {len(parsed['quantified'])} sentence(s) with numbers, %, money or scale."),
        ("Bullet points used (4+)", parsed["bullet_lines"] >= 4, "Bullets are easier to scan than dense paragraphs."),
        ("No obvious identity fields in scoring", True, "Name, gender, age, institution and location are excluded from the score."),
    ]
    score = 100
    for _, passed, _ in checks:
        if not passed:
            score -= 7
    return checks, max(0, score)


def parse_resume(text):
    """Parse a resume into structured, reviewable facts."""
    text = _clean(text)
    sections = _detect_sections(text)
    email = _EMAIL.search(text)
    phone = _PHONE.search(text)
    links = sorted(set(_LINK.findall(text)))
    experience_text = sections.get("experience", "")
    roles, total_years = _parse_experience(text, experience_text)
    edu_level = extract_education_level(text)
    education = _parse_education(sections.get("education", ""), text)
    sentences = split_sentences(text)
    quantified = [s for s in sentences if _QUANTIFIED.search(s)][:8]
    bullet_lines = len(re.findall(r"(?m)^\s*(?:[•▪◦●\-*]|\d+[.)])\s+", text))
    skills = extract_skills(text)
    name = None
    _not_names = re.compile(
        r"resume|curriculum|vitae|profile|contact|email|phone|summary|overview|objective|"
        r"engineer|technician|analyst|developer|manager|specialist|consultant|scientist|"
        r"experience|education|skills|qualifications|projects|certifications", re.I)
    for line in text.splitlines()[:8]:
        line = line.strip()
        if not (re.fullmatch(r"[A-Za-z][A-Za-z .,'\-]{1,48}", line) and 1 <= len(line.split()) <= 5):
            continue
        if line.isupper() or _not_names.search(line):
            continue
        name = line
        break
    parsed = {
        "text": text,
        "name": name,
        "email": email.group(0) if email else "",
        "phone": phone.group(0) if phone else "",
        "links": links,
        "sections": sections,
        "section_names": list(sections.keys()),
        "word_count": len(re.findall(r"\S+", text)),
        "experience": roles,
        "total_years": total_years,
        "education": education,
        "highest_education": edu_level,
        "education_label": education_label(edu_level),
        "skills": skills,
        "quantified": quantified,
        "bullet_lines": bullet_lines,
        "action_verbs": len(_ACTION_VERBS.findall(text)),
        "sentences": sentences,
    }
    checks, ats_score = _ats_checks(parsed)
    parsed["ats"] = [{"check": c, "pass": p, "note": n} for c, p, n in checks]
    parsed["ats_score"] = ats_score
    return parsed


# ---------------------------------------------------------------------------
# Competency evidence
# ---------------------------------------------------------------------------
def competency_evidence(text, competency):
    """Find evidence for one competency, returning matched phrases and snippets."""
    aliases = competency.get("aliases", [])
    hits = []
    seen_terms = set()
    for alias in aliases:
        pattern = re.compile(r"(?<![\w+#.])" + re.escape(alias) + r"(?![\w+#])", re.I)
        matches = list(pattern.finditer(text or ""))
        if matches:
            seen_terms.add(alias.lower())
            snippet = _first_snippet(text, alias)
            if snippet and snippet not in [h["snippet"] for h in hits]:
                hits.append({"term": alias, "snippet": snippet})
    distinct = len(seen_terms)
    if distinct == 0:
        strength = 0.0
    elif distinct == 1:
        strength = 0.6
    elif distinct == 2:
        strength = 0.8
    else:
        strength = 1.0
    return {
        "matched": distinct > 0,
        "strength": strength,
        "distinct_terms": sorted(seen_terms),
        "evidence": hits[:4],
    }


def evaluate_candidate(text, job):
    """Return the five score features plus full per-competency evidence."""
    parsed = parse_resume(text)
    profile = get_profile(job.get("title") or job.get("category") or "Engineering")
    criteria = []
    for comp in profile["competencies"]:
        ev = competency_evidence(parsed["text"], comp)
        criteria.append({
            "key": comp["key"],
            "label": comp["label"],
            "core": bool(comp.get("core")),
            "weight": float(comp.get("weight", 1.0)),
            "hint": comp.get("hint", ""),
            "matched": ev["matched"],
            "strength": round(ev["strength"], 3),
            "evidence": ev["evidence"],
            "terms": ev["distinct_terms"],
        })

    core = [c for c in criteria if c["core"]]
    nice = [c for c in criteria if not c["core"]]
    core_weight = sum(c["weight"] for c in core) or 1.0
    nice_weight = sum(c["weight"] for c in nice) or 1.0
    core_coverage = sum(c["weight"] * c["strength"] for c in core) / core_weight
    preferred_coverage = sum(c["weight"] * c["strength"] for c in nice) / nice_weight if nice else 0.0

    years = parsed["total_years"]
    min_years = int(job.get("min_years") or 0)
    if min_years > 0:
        experience_fit = min(years / min_years, 1.0)
    else:
        experience_fit = min(years / 3.0, 1.0)

    edu = parsed["highest_education"]
    min_edu = int(job.get("min_edu") or 0)
    if min_edu > 0:
        education_fit = min(edu / min_edu, 1.0)
    else:
        education_fit = min(edu / 2.0, 1.0)

    features = {
        "skill_match": round(core_coverage, 4),
        "nice_skills": round(preferred_coverage, 4),
        "experience": round(experience_fit, 4),
        "education": round(education_fit, 4),
        "text_match": 0.5,  # replaced by the semantic/TF-IDF score in ranker.py
    }
    return {
        "parsed": parsed,
        "criteria": criteria,
        "core_coverage": round(core_coverage, 4),
        "preferred_coverage": round(preferred_coverage, 4),
        "features": features,
        "years": years,
        "min_years": min_years,
        "education_level": edu,
        "min_edu": min_edu,
        "profile_summary": profile.get("summary", ""),
    }


# ---------------------------------------------------------------------------
# Verdict, reasons, counterfactuals and feedback
# ---------------------------------------------------------------------------
def _normalise_weights(weights):
    w = {f: max(float((weights or DEFAULT_WEIGHTS).get(f, 0.0)), 0.0) for f in FEATURES}
    total = sum(w.values()) or 1.0
    return {f: v / total for f, v in w.items()}


def _score_from_features(features, weights):
    w = _normalise_weights(weights)
    return 100.0 * sum(w[f] * float(features.get(f, 0.0)) for f in FEATURES)


def build_verdict(evaluation, score, weights=None, role=None):
    """Create the transparent decision layer for one candidate."""
    parsed = evaluation["parsed"]
    criteria = evaluation["criteria"]
    core = [c for c in criteria if c["core"]]
    matched_core = [c for c in core if c["matched"]]
    missing_core = [c for c in core if not c["matched"]]
    weak_core = [c for c in core if c["matched"] and c["strength"] < 0.8]
    core_cov = evaluation["core_coverage"]
    years = evaluation["years"]
    min_years = evaluation["min_years"]

    # ---- decision band -------------------------------------------------
    if score >= 75 and core_cov >= 0.65:
        code, label = "recommend", "Strong match — recommend for shortlist review"
        tone = "positive"
    elif score >= 60 and core_cov >= 0.50:
        code, label = "review", "Good match — recommend for interview review"
        tone = "positive"
    elif score >= 45:
        code, label = "review", "Partial match — human review needed"
        tone = "caution"
    else:
        code, label = "hold", "Limited evidence — do not auto-reject; human review needed"
        tone = "caution"

    # ---- reasons FOR ---------------------------------------------------
    reasons_for = []
    for c in sorted(matched_core, key=lambda x: (-x["strength"], -x["weight"]))[:4]:
        snippet = c["evidence"][0]["snippet"] if c["evidence"] else ""
        reasons_for.append({
            "label": c["label"],
            "detail": f"Matched {len(c['terms'])} evidence term(s): {', '.join(c['terms'][:4])}.",
            "evidence": snippet,
            "strength": c["strength"],
        })
    if years > 0:
        if min_years > 0 and years >= min_years:
            reasons_for.append({"label": "Experience requirement met",
                                "detail": f"{years} year(s) detected against a {min_years}-year minimum.",
                                "evidence": "", "strength": 1.0})
        elif min_years == 0:
            reasons_for.append({"label": "Experience detected",
                                "detail": f"{years} year(s) of dated or stated experience found.",
                                "evidence": "", "strength": min(years / 3, 1.0)})
    if evaluation["education_level"] >= max(evaluation["min_edu"], 1):
        reasons_for.append({"label": "Education requirement met",
                            "detail": f"{parsed['education_label']} detected.",
                            "evidence": parsed["education"][0] if parsed["education"] else "", "strength": 1.0})
    if parsed["quantified"]:
        reasons_for.append({"label": "Measurable outcomes",
                            "detail": f"{len(parsed['quantified'])} achievement(s) include numbers, %, money or scale.",
                            "evidence": parsed["quantified"][0], "strength": 1.0})

    # ---- reasons AGAINST ----------------------------------------------
    reasons_against = []
    for c in sorted(missing_core, key=lambda x: -x["weight"])[:5]:
        reasons_against.append({
            "label": f"No evidence: {c['label']}",
            "detail": c["hint"] or "The resume does not contain a phrase that counts as evidence for this competency.",
        })
    for c in weak_core[:2]:
        reasons_against.append({
            "label": f"Thin evidence: {c['label']}",
            "detail": "Only one generic mention was found. A concrete example would make this stronger.",
        })
    if min_years > 0 and years < min_years:
        reasons_against.append({
            "label": "Below the stated experience minimum",
            "detail": f"{years} year(s) detected; the role asks for {min_years}. This is a role setting, not a legal requirement.",
        })
    if evaluation["education_level"] < evaluation["min_edu"]:
        reasons_against.append({
            "label": "Below the stated education level",
            "detail": f"{parsed['education_label']} detected; the role setting expects {education_label(evaluation['min_edu'])}.",
        })
    if not parsed["quantified"]:
        reasons_against.append({
            "label": "No quantified achievements",
            "detail": "No sentence with a number, percentage, budget or scale was found, so impact is hard to verify.",
        })
    if evaluation["features"].get("text_match", 0.5) < 0.35:
        reasons_against.append({
            "label": "Low language relevance to the role description",
            "detail": "The resume's wording overlaps little with this vacancy. This can be a wording problem rather than a skills problem.",
        })
    if parsed["word_count"] < 120:
        reasons_against.append({
            "label": "Very little text to assess",
            "detail": f"Only {parsed['word_count']} words were extracted. The file may be scanned or incomplete.",
        })

    # ---- counterfactuals ----------------------------------------------
    total_core_weight = sum(c["weight"] for c in core) or 1.0
    counterfactuals = []
    base_features = dict(evaluation["features"])
    for c in sorted(missing_core, key=lambda x: -x["weight"])[:3]:
        delta_cov = c["weight"] / total_core_weight
        projected = dict(base_features)
        projected["skill_match"] = min(1.0, base_features["skill_match"] + delta_cov)
        projected_score = _score_from_features(projected, weights)
        counterfactuals.append(
            f"If the resume showed concrete evidence of “{c['label']}”, core coverage would rise by "
            f"{delta_cov * 100:.0f} points and the score would move from {score:.1f} to about {projected_score:.1f}.")
    if min_years > 0 and years < min_years:
        projected = dict(base_features)
        projected["experience"] = 1.0
        projected_score = _score_from_features(projected, weights)
        counterfactuals.append(
            f"Meeting the {min_years}-year experience setting would move the score from {score:.1f} to about {projected_score:.1f}.")
    if not parsed["quantified"]:
        counterfactuals.append(
            "Adding two or three measurable outcomes (for example “reduced defects by 12%” or “managed a team of 4”) "
            "would not change the competency coverage, but it would give a reviewer verifiable proof of impact.")
    if not missing_core and matched_core:
        # Robustness check: how far would the score fall if the strongest
        # single piece of evidence were removed?
        drops = []
        for c in matched_core:
            lost = c["weight"] * c["strength"] / total_core_weight
            projected = dict(base_features)
            projected["skill_match"] = max(0.0, base_features["skill_match"] - lost)
            drops.append((_score_from_features(projected, weights), c["label"]))
        worst_score, worst_label = min(drops, key=lambda x: x[0])
        counterfactuals.append(
            f"This recommendation is robust: the largest single-evidence drop would come from removing "
            f"“{worst_label}”, which would still leave the score at about {worst_score:.1f}.")
    if weak_core:
        counterfactuals.append(
            "Strengthening the thin evidence for " + ", ".join(c["label"] for c in weak_core[:2]) +
            " with a concrete example would raise the score and make the decision easier to defend.")

    # ---- confidence ----------------------------------------------------
    sections_found = len([s for s in ("summary", "skills", "experience", "education") if s in parsed["sections"]])
    if parsed["word_count"] >= 250 and sections_found >= 3 and len(matched_core) >= 3:
        confidence, confidence_reason = "High", (
            f"{parsed['word_count']} words, {sections_found}/4 core sections and {len(matched_core)} core competencies with evidence.")
    elif parsed["word_count"] >= 100 and sections_found >= 2 and len(matched_core) >= 2:
        confidence, confidence_reason = "Medium", (
            f"{parsed['word_count']} words, {sections_found}/4 core sections and {len(matched_core)} core competencies with evidence.")
    else:
        confidence, confidence_reason = "Low", (
            f"Only {parsed['word_count']} words and {sections_found}/4 core sections were readable; treat this result cautiously.")

    # ---- plain-language summary ---------------------------------------
    matched_labels = [c["label"] for c in matched_core]
    missing_labels = [c["label"] for c in missing_core]
    if matched_labels:
        strength_text = "The strongest evidence is for " + ", ".join(matched_labels[:3]) + "."
    else:
        strength_text = "No core competency had clear evidence in the readable text."
    if missing_labels:
        gap_text = "We could not find evidence for " + ", ".join(missing_labels[:3]) + "."
    else:
        gap_text = "Every core competency had at least one piece of evidence."
    summary = (
        f"This resume scores {score:.1f}/100 for the {role or 'selected'} role. "
        f"{strength_text} {gap_text} "
        f"The system's suggestion is: {label}. This is decision support, not a hiring decision — "
        f"a human reviewer must check the evidence and the role criteria before acting."
    )

    return {
        "code": code,
        "label": label,
        "tone": tone,
        "score": round(float(score), 2),
        "core_coverage": round(core_cov, 4),
        "preferred_coverage": round(evaluation["preferred_coverage"], 4),
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "reasons_for": reasons_for,
        "reasons_against": reasons_against,
        "counterfactuals": counterfactuals,
        "summary": summary,
        "matched_core": [c["label"] for c in matched_core],
        "missing_core": [c["label"] for c in missing_core],
        "limitations": [
            "Evidence is phrase-based: a true skill described with unusual wording may be missed.",
            "Years of experience are estimated from dates and explicit statements, not payroll records.",
            "The score is a prototype heuristic and has not been validated against job performance.",
            "Name, gender, age, institution and location are not used as scoring features.",
        ],
    }


def build_feedback(evaluation, verdict):
    """Turn the analysis into concrete resume-improvement input."""
    parsed = evaluation["parsed"]
    criteria = evaluation["criteria"]
    core = [c for c in criteria if c["core"]]
    missing = [c for c in core if not c["matched"]]
    weak = [c for c in core if c["matched"] and c["strength"] < 0.8]
    nice_missing = [c for c in criteria if not c["core"] and not c["matched"]]

    strengths = []
    for c in sorted([c for c in core if c["matched"]], key=lambda x: -x["strength"])[:4]:
        snippet = c["evidence"][0]["snippet"] if c["evidence"] else ""
        strengths.append({"label": c["label"], "evidence": snippet})
    if parsed["quantified"]:
        strengths.append({"label": "Quantified impact", "evidence": parsed["quantified"][0]})
    if parsed["total_years"]:
        strengths.append({"label": "Experience", "evidence": f"{parsed['total_years']} year(s) detected."})
    if parsed["highest_education"]:
        strengths.append({"label": "Education", "evidence": parsed["education_label"]})

    gaps = [{"label": c["label"], "why": c["hint"]} for c in missing]
    if weak:
        gaps.append({"label": "Thin evidence in " + ", ".join(c["label"] for c in weak),
                     "why": "Only a generic mention was found; add a specific example."})

    suggestions = []
    for c in missing[:4]:
        suggestions.append(f"Add one bullet that proves “{c['label']}”. {c['hint']}")
    if not parsed["quantified"]:
        suggestions.append("Add measurable results to at least two bullets (%, money, time saved, volume, team size).")
    if parsed["word_count"] < 250:
        suggestions.append("The resume is short. Add 2–3 bullets per recent role describing the action, the tool and the result.")
    if parsed["word_count"] > 1000:
        suggestions.append("The resume is long. Move older or unrelated roles to a one-line summary and keep the top third focused.")
    if "summary" not in parsed["sections"]:
        suggestions.append("Add a 2–3 line summary at the top naming the target role and your strongest, most relevant evidence.")
    if "skills" not in parsed["sections"]:
        suggestions.append("Add a short skills section so both humans and applicant-tracking systems can find your tools quickly.")
    if not parsed["links"]:
        suggestions.append("Add a LinkedIn, GitHub or portfolio link so a reviewer can verify your work.")
    for check in parsed["ats"]:
        if not check["pass"] and check["check"] not in ("Email address found", "Phone number found"):
            suggestions.append(f"Fix: {check['check']}. {check['note']}")
    if nice_missing:
        suggestions.append("Optional boost: mention any genuine experience with " +
                           ", ".join(c["label"] for c in nice_missing[:3]) + ".")
    suggestions = list(dict.fromkeys(suggestions))[:10]

    return {
        "strengths": strengths,
        "gaps": gaps,
        "suggestions": suggestions,
        "ats_score": parsed["ats_score"],
        "ats": parsed["ats"],
        "readability": {
            "word_count": parsed["word_count"],
            "bullet_lines": parsed["bullet_lines"],
            "quantified_achievements": len(parsed["quantified"]),
            "dated_roles": len(parsed["experience"]),
            "action_verbs": parsed["action_verbs"],
        },
    }


# ---------------------------------------------------------------------------
# Role text similarity and single-resume analysis (used by the UI)
# ---------------------------------------------------------------------------
_STOPWORDS = set("""
a an the and or but if then than that this these those with without within for from into onto
of in on at to by as is are was were be been being has have had do does did will would can could
should may might must not no nor so such very more most other others our your their its it he she
they them we you i me my mine own same both each few many much some any all also just about across
over under between during before after above below up down out off again further once here there
when where why how what which who whom whose role roles job jobs work working experience experienced
years year plus etc using use used ability able strong good excellent required requirements preferred
knowledge understanding familiarity team teams candidate candidates applicant applicants company
""".split())


def _content_terms(text):
    """Lower-case content words, keeping technical tokens such as c++, ci/cd, scikit-learn."""
    words = re.findall(r"[a-z0-9][a-z0-9+#./-]{2,}", (text or "").lower())
    return {w.strip(".-/") for w in words if w.strip(".-/") not in _STOPWORDS}


def lexical_recall(query, document):
    """Fraction of the role's key terms that actually appear in the resume.

    This is deliberately simple and explainable: it answers "how much of the
    role's language shows up in this resume?"  It complements TF-IDF cosine,
    which is very low when the role description is short.
    """
    q = _content_terms(query)
    if not q:
        return 0.0
    return len(q & _content_terms(document)) / len(q)


def job_query(job):
    """Build the text representation of a role used for similarity scoring."""
    profile = get_profile(job.get("title") or job.get("category") or "Engineering")
    labels = [c["label"] for c in profile["competencies"]]
    aliases = []
    for c in profile["competencies"]:
        aliases.extend(c.get("aliases", [])[:3])
    return ("Vacancy: " + str(job.get("title", "")) +
            "\nRole description: " + str(job.get("description", "")) +
            "\nCore capabilities: " + ", ".join(labels) +
            "\nRelated tools and methods: " + ", ".join(dict.fromkeys(aliases)))


def analyze_single(text, job, weights=None):
    """Analyse one resume without a candidate pool (the HR 'Analyzer' tab).

    Returns the same shapes the ranker stores: evaluation, verdict, feedback
    and the final score, so the UI can render one consistent explanation.
    """
    from .similarity import text_similarity  # local import avoids a cycle

    evaluation = evaluate_candidate(text, job)
    similarity, engine = text_similarity(job_query(job), [text])
    evaluation["features"]["text_match"] = round(float(similarity[0]), 4)
    evaluation["matching_engine"] = engine
    score = _score_from_features(evaluation["features"], weights)
    verdict = build_verdict(evaluation, score, weights, role=job.get("title", ""))
    feedback = build_feedback(evaluation, verdict)
    return {
        "score": round(score, 2),
        "evaluation": evaluation,
        "verdict": verdict,
        "feedback": feedback,
        "features": evaluation["features"],
    }
