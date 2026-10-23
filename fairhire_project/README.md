# FairHire — Explainable & Bias-Audited Resume Screener

FairHire is a Streamlit prototype that reads a real resume, scores it against a role, and then **shows its working**: which competencies it found evidence for, which it did not, why that changed the score, what would change the decision, and what the candidate should fix in the resume.

It is built for the OlympAI hackathon (Team ByteForce). It is decision support, not an automated hiring decision.

## What Stage 2 adds

Stage 1 could rank resumes by keyword overlap, but it could not explain itself. Stage 2 closes that gap:

- **A real analysis engine.** `fairhire/taxonomy.py` defines five role profiles as weighted competencies with aliases and "what counts as evidence" hints. `fairhire/analyzer.py` parses the resume into sections, dated roles, education, contact details and quantified achievements, then matches every competency against quoted sentences from the resume.
- **A transparent verdict.** Every result carries reasons *for*, reasons *against*, counterfactuals ("if the resume showed X, the score would move from 77.6 to about 81.0"), a confidence level with the reason for that confidence, and a plain-language summary.
- **Resume feedback.** Strengths, gaps, ATS problems and concrete, prioritised rewrite suggestions — the "give it inputs" part of the brief.
- **A single-resume Analyser tab.** Paste or upload one resume, pick a role, and get the full rationale without adding the person to the applicant pool.
- **A shareable HTML report.** `fairhire/report.py` renders the whole analysis as one self-contained, accessible HTML file you can email or attach to a submission.
- **Accessibility as a first-class feature.** Skip link, larger-text toggle, high-contrast toggle, reduce-motion toggle, visible focus outlines, semantic landmarks, table captions and a text-table alternative for every chart.
- **One similarity function.** The Analyser and the Ranker now call the same `fairhire/similarity.py`, so the same resume cannot get two different scores from two screens.

## Five role categories

Engineering, Information Technology, Design, Banking and Digital Media. Each profile lists core and preferred competencies with weights, so the same resume can legitimately score differently for different roles — and the app explains which competencies drove that difference.

These are starter profiles, not validated job descriptions. Edit the role requirements in **Upload & pool → Edit this role's requirements** before using the tool for a real vacancy.

## The five scoring features

| Feature | Weight | What it measures |
|---|---|---|
| `skill_match` | 0.45 | Weighted coverage of the role's **core** competencies, where a competency only counts if the resume contains a real evidence phrase |
| `nice_skills` | 0.10 | Weighted coverage of **preferred** competencies |
| `experience` | 0.15 | Years detected (explicit statements and merged date ranges) against the role minimum |
| `education` | 0.10 | Highest detected qualification against the role expectation |
| `text_match` | 0.20 | 0.55 × lexical recall + 0.45 × TF-IDF cosine (or 0.45 × recall + 0.55 × sentence embeddings when the optional model is installed) |

Weights are adjustable in the sidebar and are re-normalised so the score stays on a 0–100 scale.

### Why the score is exactly explainable

The model is linear, so the contribution of feature *i* for one candidate is

```
contribution_i = weight_i × (x_i − mean_i) × 100
```

and `base_value + Σ contribution_i = score`, exactly. The UI shows this decomposition as a bar chart **and** as a table, because a chart alone is not accessible. This is an exact decomposition of our own linear formula — it is deliberately **not** described as SHAP. An optional `verify_with_shap` cross-check exists if the `shap` package is installed.

## Transparency rules the app follows

1. Nothing is auto-rejected. The weakest outcome is *"Limited evidence — do not auto-reject; human review needed."*
2. Every reason quotes the sentence it came from, so a reviewer can check it.
3. Every "no" is specific: *"No evidence: Safety, standards & compliance — the resume does not mention standards, compliance, audits or regulatory work."*
4. Confidence is stated with its basis, e.g. *"High — 915 words, 4/4 core sections and 5 core competencies with evidence."*
5. Counterfactuals are computed from the same linear model, not guessed.
6. Limitations are printed on the result itself, not buried in a footer.
7. Demographic fairness is **not** claimed. Without consented demographic data the app refuses to present parity metrics, and says so.

## Accessibility

- "Skip to main content" link as the first focusable element.
- Sidebar toggles: **Larger text** (19 px base), **High contrast** (white on black, brighter accents), **Reduce motion**.
- `:focus-visible` outlines on every control, 3 px, high-contrast yellow.
- Charts always ship with an expandable text table of the same numbers.
- Reports use `<section aria-labelledby>`, `<th scope>`, visible text pills next to colour, and print styles.
- Colour is never the only carrier of meaning: verdicts also carry words.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m streamlit run main.py
```

Optional semantic model (large download, falls back cleanly if absent):

```bash
python -m pip install -r requirements-ai.txt
```

Force the lightweight path:

```bash
FAIRHIRE_USE_EMBEDDINGS=0 python -m streamlit run main.py
```

## Using it

1. Open the app and choose **HR Recruiter**.
2. **Analyze a resume** — pick a role, upload a PDF/DOCX/TXT or paste text, press *Analyse resume*. You get the verdict, reasons for and against, the score decomposition, the competency evidence table, resume feedback, ATS checks, what the parser found, limitations, and two download buttons (HTML report and JSON).
3. **Upload & pool** — add several resumes to a role, then review them side by side.
4. **Review & ranking** — blind review, minimum-score filter, status filter, a rationale inspector for any candidate, reviewer notes and *Recommend for shortlist*.
5. **Pipeline & communication** — move a candidate through the stages and edit the email draft. Drafts are never sent automatically.
6. **Company Head workspace** — approve or return shortlisted recommendations, read the fairness safeguards, run the identity-masking sensitivity audit, and export the decision history.

## Privacy and limits

- Uploaded resume text and workflow data live in `fairhire_uploads.db` in the project folder. Delete that file to clear the workspace.
- The workspace selector demonstrates role-based workflow; it is **not** authentication.
- Scanned image-only PDFs need OCR before import.
- Do not commit the database or real resumes to GitHub.
- Never use the score as the sole basis for rejecting or selecting a person.

## Tests

```bash
python -m pytest -q
```

The suite checks score additivity, feature completeness, experience and education extraction, anonymiser leakage, and the head-approval workflow gate.

## Updated Stage 2 workflow (burgundy UI)

1. Open **Recruitment desk · Upload + Analyse**.
2. Select a vacancy and upload one or more real PDF, DOCX or TXT resumes.
3. Select **Analyse & add to applicant pool** to extract text, score each resume and show evidence/reasons.
4. HR can **Accept & send to Head**, **Reject applicant**, or **Keep pending**. An accepted applicant is placed in the shortlist and appears in the Company Head approval queue. Any candidate email is only drafted for HR review.
5. In **Company Head**, review the AI rationale and either approve the HR recommendation or return it to HR. Approval is logged.

The AI recommendation is triage support, not a final employment decision. Human reviewers must check job-related evidence and vacancy criteria. Scanned/image-only PDFs need OCR, which is not bundled in this build.

## Local run

```bash
py -m pip install -r requirements.txt
py -m pip install -r requirements-ai.txt
py -m streamlit run main.py
```
