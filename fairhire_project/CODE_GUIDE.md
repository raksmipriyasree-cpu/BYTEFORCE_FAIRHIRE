# FairHire code guide — beginner-friendly walkthrough

## The big picture

FairHire is a **human-led recruitment decision-support prototype**. It reads only the resumes you give it, explains every score, and leaves the decision to a person.

The pipeline has five stages:

1. **Ingest** — validate the file and extract selectable text. Scanned image-only PDFs need OCR first.
2. **Understand** — parse the resume into sections, dated roles, education, contact details, skills and quantified achievements.
3. **Explain** — match the role's competencies against quoted sentences, combine five features into a score, and derive reasons for, reasons against, counterfactuals and confidence from the same model.
4. **Improve** — turn the gaps into concrete resume feedback: what to add, where, and why it would change the result.
5. **Govern** — reviewer notes, shortlist recommendation, Company Head approval, draft communication and an audit log, all in SQLite.

## Files and what they do

| File | Purpose |
|---|---|
| `main.py` | Streamlit interface: welcome screen, HR workspace (4 tabs), Company Head workspace (4 tabs), accessible theme, all rendering helpers. |
| `fairhire/taxonomy.py` | The five role profiles. Each competency has a key, label, core flag, weight, aliases and a hint describing what counts as evidence. |
| `fairhire/analyzer.py` | The engine: `parse_resume`, `competency_evidence`, `evaluate_candidate`, `build_verdict`, `build_feedback`, `analyze_single`, `lexical_recall`, `job_query`. |
| `fairhire/similarity.py` | `text_similarity(query, documents)` — the single blend of lexical recall and TF-IDF/embeddings used everywhere. |
| `fairhire/ranker.py` | Pool scoring: builds features, computes exact additive contributions, ranks candidates, attaches verdicts and feedback. |
| `fairhire/skills.py` | Skill vocabulary and extraction, years of experience from explicit statements and merged date intervals, education level. |
| `fairhire/report.py` | `build_report_html(...)` — one self-contained accessible HTML report with eight sections. |
| `fairhire/anonymizer.py` | Masks identity text for blind review and for pool similarity. Masking is imperfect and must be reviewed. |
| `fairhire/fairness.py` | Identity-masking sensitivity audit. Diagnostics, not certification. |
| `fairhire/data_loader.py` | Extracts text from uploaded documents. |
| `fairhire/db.py` | SQLite storage, schema migration, workflow rules, audit log. |
| `fairhire/emailer.py` | Creates communication drafts for a human to review. Sending is not automatic. |
| `fairhire/semantic.py` | Optional sentence-embedding loader. Inference only, no training. |
| `tests/test_core.py` | Unit tests: additivity, feature set, experience/education extraction, anonymiser leakage, approval gate. |

## How one resume becomes a verdict

1. **Parse.** `parse_resume(text)` returns word count, sections found, dated roles, education lines and level, contact details, skills, quantified achievements, bullet and action-verb counts, and ATS checks.
2. **Match evidence.** For each competency in the role profile, every alias is searched with word-boundary regex. A hit stores the alias and a quoted sentence around it. Strength rises with the number of distinct aliases found.
3. **Score.** `skill_match` is the weight-normalised share of core competencies with evidence; `nice_skills` is the same for preferred ones; experience and education are ratios against the role settings; `text_match` comes from `similarity.text_similarity`.
4. **Verdict.** `build_verdict` sorts matched core competencies by strength and weight to produce reasons for, lists missing and thin core competencies as reasons against, and computes counterfactuals by re-scoring the model with one feature raised.
5. **Feedback.** `build_feedback` turns the same evidence into strengths, gaps, ATS fixes and prioritised rewrite suggestions.
6. **Report.** `build_report_html` renders all of it as a standalone accessible HTML file.

## Why the score is exactly explainable

The model is linear, so the contribution of feature *i* is

```
contribution_i = weight_i × (x_i − mean_i) × 100
```

and `base_value + Σ contribution_i = score`, exactly. The UI shows this as a bar chart and as a table. This is an exact decomposition of our own formula; it is **not** SHAP, and we do not claim it is.

## What "confidence" means

Confidence is about the *evidence*, not about the candidate. It is High when the resume has at least 250 words, at least three of the four core sections, and at least three core competencies with evidence. It drops to Medium or Low as those conditions fail, and the reason is always printed next to the label.

## What the fairness audit means

The audit ranks the same pool twice, with identity masking on and off, and reports score change and rank movement. It can reveal sensitivity to identity text. It cannot measure demographic parity, and it does not infer protected characteristics.

## Install and run

```bash
python -m pip install -r requirements.txt
python -m streamlit run main.py
```

Optional semantic model:

```bash
python -m pip install -r requirements-ai.txt
```

Force the lightweight path:

```bash
FAIRHIRE_USE_EMBEDDINGS=0 python -m streamlit run main.py
```

## Suggested demonstration

1. Choose **HR Recruiter → Analyze a resume**, pick Engineering, upload a resume, press *Analyse resume*.
2. Point at the verdict, then at *Reasons for* and *Reasons against* — each one quotes the sentence it came from.
3. Open *What would change this decision?* and read a counterfactual.
4. Scroll to *Resume feedback and improvements* — this is the advice the candidate would receive.
5. Download the HTML report and open it in a browser.
6. Upload two or three resumes into **Upload & pool**, then open **Review & ranking** and inspect a candidate's full rationale.
7. Recommend one for shortlist, switch to **Company Head**, approve it, and show the decision history.
8. Run the identity-masking audit and explain what it does and does not prove.
9. Toggle **Larger text**, **High contrast** and **Reduce motion** to show the accessibility work.

## Safety and privacy

- Do not upload personal information without permission.
- Do not commit `fairhire_uploads.db`, resumes, credentials or contact details.
- The workspace selector is **not** authentication.
- Email drafts require human review before sending.
- Never use the score as the sole basis for rejecting or selecting an applicant.
