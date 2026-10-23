# FairHire — Explainable, Human-Led Recruitment Support

# Application Live Link: https://byteforcefairhire.streamlit.app/
# Github link: https://github.com/raksmipriyasree-cpu/BYTEFORCE_FAIRHIRE.git

FairHire is a Streamlit-based recruitment decision-support prototype that helps HR reviewers analyse resumes against role-related competencies. It extracts resume text, identifies evidence for relevant skills, calculates an explainable score, and provides practical resume feedback.

**FairHire supports human review; it does not make hiring decisions autonomously.** Reviewers should consider the full application and must never use the score as the sole basis for selecting or rejecting a candidate.

## Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [How It Works](#how-it-works)
- [Scoring and Explainability](#scoring-and-explainability)
- [Technology and Project Structure](#technology-and-project-structure)
- [Installation](#installation)
- [Running FairHire](#running-fairhire)
- [Suggested Demo](#suggested-demo)
- [Privacy, Fairness and Limitations](#privacy-fairness-and-limitations)
- [Testing](#testing)
- [Future Improvements](#future-improvements)

## Overview

FairHire follows an **evidence-before-score** approach. For each competency in a selected role profile, it looks for matching terms and connects the match to a sentence from the resume. The reviewer can inspect the evidence, the score breakdown, strengths, gaps and suggested improvements.

The application includes two workspaces:

- **HR Recruiter:** analyse a single resume, review a candidate pool, inspect rankings and rationales, add notes, and recommend candidates for a shortlist.
- **Company Head:** review shortlist recommendations and record the required approval in the workflow.

The application also provides an accessible HTML report, communication drafts for human review, an audit log and an identity-masking sensitivity audit.

## Key Features

- **Resume text extraction:** accepts supported PDF, DOCX and TXT files, or pasted resume text. Scanned image-only PDFs may require OCR before use.
- **Resume parsing:** identifies sections, dated roles, education, contact details, skills, quantified achievements and selected ATS-related checks.
- **Role-based competency matching:** compares resume evidence with weighted core and preferred competencies from the role taxonomy.
- **Explainable scoring:** displays five scoring features and their contributions to the final score.
- **Evidence-linked verdicts:** presents reasons for and against a match using resume evidence, along with counterfactuals and an evidence-based confidence label.
- **Actionable resume feedback:** highlights strengths, gaps, ATS-related fixes and prioritised rewrite suggestions.
- **Candidate-pool review:** ranks a pool of resumes and provides candidate-level explanations.
- **Blind-review support:** masks selected identity text during pool similarity analysis.
- **Human approval workflow:** records reviewer notes, shortlist recommendations and Company Head approval.
- **Audit trail:** stores workflow activity in SQLite.
- **Communication drafts:** prepares messages for a person to review; emails are not sent automatically.
- **Accessible interface:** includes larger-text, high-contrast and reduced-motion options, plus accessibility features for navigation and charts.
- **Standalone HTML report:** generates an accessible report that can be opened in a browser.

## How It Works

1. **Ingest:** extract selectable text from an uploaded resume or accept pasted text.
2. **Parse:** identify relevant sections, work history, education, skills, contact details and other resume features.
3. **Match evidence:** compare the resume with the selected role's competencies and retain quoted text supporting each match.
4. **Calculate features:** derive skill match, preferred-skill match, experience, education and text-similarity features.
5. **Score and explain:** calculate the weighted linear score, show feature contributions, and generate reasons for, reasons against, counterfactuals and a confidence label.
6. **Suggest improvements:** turn identified gaps into practical resume-writing feedback.
7. **Review and govern:** allow HR to inspect the evidence, add notes and recommend a shortlist. The Company Head approval gate and audit log support the workflow.
8. **Report:** generate a standalone HTML report of the analysis.

## Scoring and Explainability

FairHire uses five features:

- `skill_match`
- `nice_skills`
- `experience`
- `education`
- `text_match`

The text-similarity module combines lexical recall with TF-IDF or an optional sentence-embedding model. The same similarity module is used by the single-resume analyser and candidate-pool ranker.

The model is linear. Each feature's contribution is calculated as:

```text
contribution_i = weight_i × (x_i − mean_i) × 100
```

The score is decomposed as:

```text
score = base_value + sum(feature contributions)
```

The displayed contributions explain the app's own scoring formula. **This is not SHAP**, and the score should not be interpreted as an objective measure of a person's ability or future job performance.

### What confidence means

The confidence label describes the amount and coverage of evidence available in the resume, not the quality or worth of the candidate. The implementation considers resume length, the presence of core sections and the number of core competencies supported by evidence. The app displays a reason alongside the label.

## Technology and Project Structure

| File or module | Responsibility |
|---|---|
| `main.py` | Streamlit interface, HR and Company Head workspaces, tabs and display settings |
| `fairhire/taxonomy.py` | Role profiles, competency weights, aliases and evidence hints |
| `fairhire/analyzer.py` | Resume parsing, evidence matching, evaluation, verdicts and feedback |
| `fairhire/similarity.py` | Shared lexical and TF-IDF/embedding text similarity |
| `fairhire/ranker.py` | Candidate-pool scoring, ranking and feature contributions |
| `fairhire/skills.py` | Skill extraction, experience calculation and education-level extraction |
| `fairhire/data_loader.py` | Text extraction from uploaded documents |
| `fairhire/report.py` | Accessible standalone HTML report generation |
| `fairhire/anonymizer.py` | Identity-text masking for blind review and pool similarity |
| `fairhire/fairness.py` | Identity-masking sensitivity audit |
| `fairhire/db.py` | SQLite persistence, workflow rules, schema migration and audit log |
| `fairhire/emailer.py` | Communication draft generation |
| `fairhire/semantic.py` | Optional sentence-embedding model loader for inference |
| `tests/test_core.py` | Core unit tests, including scoring additivity and approval-gate checks |

## Installation

### Requirements

- Python installed on your computer
- The project source code
- Internet access if dependencies or the optional semantic model need to be downloaded

### 1. Clone or download the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_PROJECT_FOLDER>
```

Replace the placeholders with your repository URL and project folder name.

### 2. Install the dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Start the app

```bash
python -m streamlit run main.py
```

Streamlit will display a local URL in the terminal. Open that URL in your browser.

### Optional: Enable the semantic model

If you want to use the optional sentence-embedding support and the project includes `requirements-ai.txt`, install those dependencies:

```bash
python -m pip install -r requirements-ai.txt
```

The model is used for inference; FairHire does not train a custom model.

### Use the lightweight path

To disable embeddings and use the lightweight similarity path:

**Windows PowerShell**
```powershell
$env:FAIRHIRE_USE_EMBEDDINGS="0"
python -m streamlit run main.py
```

**Windows Command Prompt**
```cmd
set FAIRHIRE_USE_EMBEDDINGS=0
python -m streamlit run main.py
```

**macOS / Linux**
```bash
FAIRHIRE_USE_EMBEDDINGS=0 python -m streamlit run main.py
```

## Suggested Demo

1. Open **HR Recruiter → Analyse a resume**.
2. Select a role profile, upload a resume and run the analysis.
3. Inspect the verdict and the quoted evidence under **Reasons for** and **Reasons against**.
4. Open the counterfactual section to see how changing one feature affects the model's score.
5. Review the resume feedback and suggested improvements.
6. Download and open the HTML report in a browser.
7. Upload multiple resumes to **Upload & pool**, then inspect **Review & ranking**.
8. Add reviewer notes and make a shortlist recommendation.
9. Switch to **Company Head**, review the recommendation and record approval.
10. Inspect the decision history and run the identity-masking sensitivity audit.
11. Demonstrate the larger-text, high-contrast and reduced-motion settings.

Use sample resumes or resumes shared with permission. Do not use real applicants' personal information in a public demonstration.

## Privacy, Fairness and Limitations

FairHire is a prototype and should be used cautiously.

- **Human judgement remains essential.** Never use the score as the sole reason to shortlist, interview or reject someone.
- **Evidence may be missed.** Resume formats, wording, missing dates, parsing errors and keyword-based matching can affect results. Review quoted evidence and the original resume.
- **Scanned PDFs may need OCR.** Image-only PDFs may not provide extractable text.
- **Identity masking is imperfect.** It can miss identifying details and does not guarantee anonymous review.
- **The fairness audit is limited.** It compares results with identity masking enabled and disabled to reveal possible sensitivity. It does not measure demographic parity, prove fairness, certify legal compliance or infer protected characteristics.
- **Confidence is not candidate confidence.** It reflects the coverage of evidence found in the resume, not a probability that a hiring decision is correct.
- **Similarity is not job performance.** Text similarity and competency matches are signals for review, not proof of a candidate's actual ability.
- **Review communication drafts.** Messages are drafts and require human review before sending.
- **Workspace selection is not authentication.** The HR/Company Head selector does not, by itself, secure access or verify a user's identity.
- **Protect local data.** Do not commit `fairhire_uploads.db`, resumes, credentials, contact details or other private information to version control. Add sensitive files to `.gitignore` and use appropriate access controls for any deployment.
- **Check applicable requirements.** Before using the prototype in a real hiring process, assess privacy, accessibility, employment and AI-governance obligations for the relevant jurisdiction.

## Testing

Run the core test suite from the project root:

```bash
python -m pytest tests/test_core.py
```

The listed tests cover core behaviours such as score additivity, feature availability, experience and education extraction, anonymiser leakage and the approval gate. Passing tests does not establish that the system is fair, accurate for every resume, or suitable for making employment decisions.

## Team Name: ByteForce
Team Members: M. Raksmi Priyasree
Harini Priya Karthikeyan

Email ID: raksmi@jainvidyalaya.in / raksmipriyasree@gmail.com
harinipriya@jainviyalaya.in / hpk1908@gmail.com
Github Link: https://github.com/raksmipriyasree-cpu/BYTEFORCE_FAIRHIRE.git
