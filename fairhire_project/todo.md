# FairHire Stage 2 — build plan
## 1. Analysis engine
- [x] Add role competency taxonomy with evidence phrases for all 5 roles
- [x] Build deep resume parser (sections, dates, experience, education, contact, ATS checks)
- [x] Build transparent decision engine: per-criterion evidence, reasons for/against, counterfactuals, confidence
- [x] Add resume feedback: strengths, gaps, specific improvement suggestions
- [x] Upgrade experience/education/skill extraction (word numbers, date ranges, bigger vocabulary)
## 2. Product integration
- [x] Update ranker to use evidence-backed analysis and store full rationale
- [x] Update database schema + migration for analysis payloads
- [x] Rebuild Streamlit UI: single-resume Analyzer, rationale panels, accessible theme + settings
- [x] Keep upload, ranking, pipeline, head approval, fairness audit working
- [x] Fix reason rendering (structured reasons with quoted evidence, not raw dicts)
- [x] Unify similarity so the Analyser and the Ranker agree on the same resume
## 3. Verification & delivery
- [x] Run engine on sample resume 12011623.pdf and verify output
- [x] Run test suite and fix regressions (11 passed)
- [x] Generate shareable HTML analysis report for the sample resume
- [x] Smoke-test every tab in both workspaces in the browser
- [x] Verify accessibility toggles change the UI (19px text, high-contrast palette)
- [x] Update README, ARCHITECTURE and CODE_GUIDE for Stage 2
- [x] Launch app, expose port, package updated project + report
