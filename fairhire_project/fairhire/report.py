"""Standalone, accessible HTML analysis report.

The report is a single self-contained file (no external assets) so it can be
emailed, printed or archived as the evidence behind a screening decision.
Accessibility choices: semantic landmarks, real table headers, visible text
labels next to every colour cue, high-contrast palette, and print styles.
"""
from __future__ import annotations

from datetime import datetime
from html import escape


def _e(value):
    return escape(str(value if value is not None else ""))


def _item_html(item):
    """Reasons can be plain strings or structured {label, detail, evidence}."""
    if isinstance(item, dict):
        label = str(item.get("label", "")).strip()
        detail = str(item.get("detail", "")).strip()
        evidence = str(item.get("evidence", "") or "").strip()
        strength = item.get("strength")
        parts = []
        if label:
            parts.append(f"<b>{_e(label)}</b>")
        if detail:
            parts.append(_e(detail))
        out = " &mdash; ".join(parts) if parts else _e(str(item))
        if strength is not None:
            try:
                out += f" <span class='muted'>Evidence strength {float(strength) * 100:.0f}%.</span>"
            except (TypeError, ValueError):
                pass
        if evidence:
            snippet = evidence if len(evidence) <= 220 else evidence[:217].rstrip() + "\u2026"
            out += f"<br><span class='quote'>&ldquo;{_e(snippet)}&rdquo;</span>"
        return out
    return _e(str(item))


def _list(items, empty="None recorded."):
    if not items:
        return f"<p class='muted'>{_e(empty)}</p>"
    return "<ul>" + "".join(f"<li>{_item_html(i)}</li>" for i in items) + "</ul>"


def _pill(text, kind="neutral"):
    return f"<span class='pill {kind}'>{_e(text)}</span>"


def build_report_html(result, job, filename="resume", generated_at=None):
    """Render one analysis result (from analyzer.analyze_single) as HTML."""
    verdict = result["verdict"]
    feedback = result["feedback"]
    evaluation = result["evaluation"]
    parsed = evaluation["parsed"]
    features = result["features"]
    score = result["score"]
    role = job.get("title") or job.get("category") or "Selected role"
    stamp = generated_at or datetime.now().strftime("%d %B %Y, %H:%M")

    tone = verdict.get("tone", "neutral")
    tone_class = {"good": "good", "warn": "warn", "bad": "bad"}.get(tone, "neutral")

    # Feature rows ---------------------------------------------------------
    feature_rows = ""
    labels = {
        "skill_match": ("Core competency coverage", "Weighted evidence for the role's core capabilities"),
        "nice_skills": ("Preferred competency coverage", "Weighted evidence for optional capabilities"),
        "experience": ("Experience fit", "Years detected against the role requirement"),
        "education": ("Education fit", "Highest degree against the role requirement"),
        "text_match": ("Role language match", "Share of the role's key terms found in the resume"),
    }
    for key in ("skill_match", "nice_skills", "experience", "education", "text_match"):
        name, desc = labels[key]
        value = float(features.get(key, 0.0))
        feature_rows += (
            f"<tr><th scope='row'>{_e(name)}<span class='sub'>{_e(desc)}</span></th>"
            f"<td><div class='bar' role='img' aria-label='{_e(name)}: {value*100:.0f} percent'>"
            f"<span style='width:{max(0,min(100,value*100)):.1f}%'></span></div></td>"
            f"<td class='num'>{value*100:.0f}%</td></tr>"
        )

    # Competency evidence rows --------------------------------------------
    comp_rows = ""
    for c in evaluation["criteria"]:
        status = "Evidence found" if c["matched"] else "No evidence found"
        strength = f"{c['strength']*100:.0f}%"
        snippets = "; ".join(f"\u201c{e['snippet']}\u201d" for e in c["evidence"][:2]) or "\u2014"
        comp_rows += (
            f"<tr><th scope='row'>{_e(c['label'])}"
            f"<span class='sub'>{'Core' if c['core'] else 'Preferred'} \u00b7 weight {c['weight']:.2f}</span></th>"
            f"<td>{_pill(status, 'good' if c['matched'] else 'warn')}</td>"
            f"<td class='num'>{_e(strength)}</td>"
            f"<td class='quote'>{_e(snippets)}</td></tr>"
        )

    # ATS checks -----------------------------------------------------------
    ats_rows = "".join(
        f"<tr><th scope='row'>{_e(ch['check'])}</th>"
        f"<td>{_pill('Pass' if ch['pass'] else 'Fix', 'good' if ch['pass'] else 'warn')}</td>"
        f"<td>{_e(ch['note'])}</td></tr>"
        for ch in feedback.get("ats", [])
    )

    strengths = "".join(
        f"<li><strong>{_e(s['label'])}</strong>"
        + (f" \u2014 <span class='quote'>{_e(s['evidence'])}</span>" if s.get("evidence") else "")
        + "</li>"
        for s in feedback.get("strengths", [])
    ) or "<li class='muted'>No strengths recorded.</li>"

    gaps = "".join(
        f"<li><strong>{_e(g['label'])}</strong> \u2014 {_e(g.get('why',''))}</li>"
        for g in feedback.get("gaps", [])
    ) or "<li class='muted'>No core gaps detected.</li>"

    roles = "".join(
        f"<li><strong>{_e(r.get('title') or 'Role')}</strong> \u2014 {_e(r.get('dates') or '')}"
        + (f"<br><span class='muted'>{_e(r.get('snippet',''))}</span>" if r.get("snippet") else "")
        + "</li>"
        for r in parsed.get("experience", [])
    ) or "<li class='muted'>No dated roles detected.</li>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FairHire analysis \u2014 {_e(role)} \u2014 {_e(filename)}</title>
<style>
  :root {{
    --ink:#101512; --muted:#4a5a4f; --paper:#ffffff; --panel:#f3f6f2;
    --line:#c9d4ca; --green:#1f6b43; --green-bg:#e6f2ea;
    --amber:#8a4b00; --amber-bg:#fdf0dd; --red:#8c1d18; --red-bg:#fbe9e7;
    --accent:#1f6b43; --quote-bg:#eef4ef; --quote-fg:#25382c;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
    font: 17px/1.6 "Segoe UI", system-ui, -apple-system, Arial, sans-serif; }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 32px 24px 64px; }}
  a:focus-visible, summary:focus-visible {{ outline: 3px solid #0b57d0; outline-offset: 3px; }}
  header.report {{ border-bottom: 4px solid var(--green); padding-bottom: 18px; margin-bottom: 26px; }}
  .brand {{ font-size:.78rem; letter-spacing:.18em; text-transform:uppercase; font-weight:800; color:var(--green); }}
  h1 {{ font-size: 2rem; line-height:1.15; margin:.4rem 0 .3rem; letter-spacing:-.02em; }}
  h2 {{ font-size: 1.25rem; margin: 2rem 0 .7rem; padding-bottom:.35rem; border-bottom:1px solid var(--line); }}
  h3 {{ font-size: 1.02rem; margin: 1.2rem 0 .4rem; }}
  p {{ margin: .5rem 0; }}
  .muted, .sub {{ color: var(--muted); }}
  .quote {{ display:inline-block; margin-top:.35rem; padding:.15rem .55rem; border-left:3px solid var(--accent);
            background: var(--quote-bg); color: var(--quote-fg); font-style:italic; border-radius:0 6px 6px 0; }}
  .sub {{ display:block; font-size:.8rem; font-weight:400; margin-top:.15rem; }}
  .scorecard {{ display:grid; grid-template-columns: 190px 1fr; gap: 22px; align-items:center;
    background: var(--panel); border:1px solid var(--line); border-radius:14px; padding: 22px; }}
  .score {{ font-size: 3.2rem; font-weight: 800; line-height:1; letter-spacing:-.03em; }}
  .score small {{ font-size:1rem; font-weight:600; color:var(--muted); }}
  .verdict {{ font-size:1.15rem; font-weight:750; margin:0 0 .3rem; }}
  .pill {{ display:inline-block; padding:.2rem .6rem; border-radius:999px; font-size:.8rem;
    font-weight:700; border:1px solid currentColor; }}
  .pill.good {{ color:var(--green); background:var(--green-bg); }}
  .pill.warn {{ color:var(--amber); background:var(--amber-bg); }}
  .pill.bad {{ color:var(--red); background:var(--red-bg); }}
  .pill.neutral {{ color:var(--muted); background:var(--panel); }}
  .good-text {{ color:var(--green); }} .warn-text {{ color:var(--amber); }} .bad-text {{ color:var(--red); }}
  table {{ width:100%; border-collapse: collapse; margin: .6rem 0 1rem; font-size:.95rem; }}
  caption {{ text-align:left; font-weight:700; padding:.4rem 0; }}
  th, td {{ text-align:left; vertical-align:top; padding:.6rem .7rem; border-bottom:1px solid var(--line); }}
  thead th {{ background:var(--panel); font-size:.8rem; text-transform:uppercase; letter-spacing:.06em; }}
  td.num {{ text-align:right; font-variant-numeric: tabular-nums; white-space:nowrap; }}
  .bar {{ background:#e3e9e3; border-radius:6px; height:12px; min-width:120px; overflow:hidden; }}
  .bar span {{ display:block; height:100%; background:var(--green); }}
  .quote {{ color:#33443a; font-style:italic; }}
  .cols {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; }}
  .box {{ border:1px solid var(--line); border-radius:12px; padding:14px 18px; }}
  .box.for {{ border-left:6px solid var(--green); }}
  .box.against {{ border-left:6px solid var(--amber); }}
  ul {{ padding-left: 1.2rem; margin:.4rem 0; }}
  li {{ margin:.3rem 0; }}
  .note {{ background:var(--panel); border:1px solid var(--line); border-left:6px solid var(--green);
    border-radius:10px; padding:14px 18px; margin:1rem 0; }}
  footer {{ margin-top:2.4rem; border-top:1px solid var(--line); padding-top:14px; font-size:.85rem; color:var(--muted); }}
  @media (max-width: 760px) {{ .scorecard, .cols {{ grid-template-columns:1fr; }} .score {{ font-size:2.4rem; }} }}
  @media print {{
    body {{ font-size: 11pt; }} .wrap {{ padding: 0; max-width:none; }}
    h2 {{ page-break-after: avoid; }} table, .box, .note {{ page-break-inside: avoid; }}
    .bar span {{ background:#1f6b43 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
</head>
<body>
<div class="wrap">
<header class="report">
  <div class="brand">\u25c8 FairHire \u00b7 Explainable screening report</div>
  <h1>{_e(role)} \u2014 candidate analysis</h1>
  <p class="muted">Source file: {_e(filename)} \u00b7 Generated {_e(stamp)} \u00b7 Decision support only, not an automated hiring decision.</p>
</header>

<section aria-labelledby="outcome">
  <h2 id="outcome">1. Outcome at a glance</h2>
  <div class="scorecard">
    <div>
      <div class="score">{score:.1f}<small>/100</small></div>
      <div class="muted">Match score</div>
    </div>
    <div>
      <p class="verdict {tone_class}-text">{_pill(verdict['label'], tone_class)}</p>
      <p>{_e(verdict['summary'])}</p>
      <p class="muted">Confidence: <strong>{_e(verdict['confidence'])}</strong> \u2014 {_e(verdict['confidence_reason'])}</p>
      <p class="muted">Core coverage {verdict['core_coverage']*100:.0f}% \u00b7 Preferred coverage {verdict['preferred_coverage']*100:.0f}%</p>
    </div>
  </div>
</section>

<section aria-labelledby="why">
  <h2 id="why">2. Why this result</h2>
  <div class="cols">
    <div class="box for">
      <h3>Reasons for</h3>
      {_list(verdict['reasons_for'], 'No supporting evidence was found.')}
    </div>
    <div class="box against">
      <h3>Reasons against</h3>
      {_list(verdict['reasons_against'], 'No material gaps were found.')}
    </div>
  </div>
  <h3>What would change the decision</h3>
  {_list(verdict['counterfactuals'], 'No counterfactual could be computed.')}
</section>

<section aria-labelledby="score-parts">
  <h2 id="score-parts">3. How the score is built</h2>
  <table>
    <caption>Score components (0\u2013100% each, before weighting)</caption>
    <thead><tr><th scope="col">Component</th><th scope="col">Level</th><th scope="col">Value</th></tr></thead>
    <tbody>{feature_rows}</tbody>
  </table>
</section>

<section aria-labelledby="evidence">
  <h2 id="evidence">4. Competency evidence</h2>
  <table>
    <caption>Every core and preferred capability, with the sentence that triggered it</caption>
    <thead><tr><th scope="col">Competency</th><th scope="col">Status</th><th scope="col">Strength</th><th scope="col">Evidence from the resume</th></tr></thead>
    <tbody>{comp_rows}</tbody>
  </table>
</section>

<section aria-labelledby="feedback">
  <h2 id="feedback">5. Resume feedback and next steps</h2>
  <h3>Strengths to keep</h3>
  <ul>{strengths}</ul>
  <h3>Gaps a reviewer will look for</h3>
  <ul>{gaps}</ul>
  <h3>Concrete improvements</h3>
  {_list(feedback['suggestions'], 'No improvements suggested.')}
</section>

<section aria-labelledby="ats">
  <h2 id="ats">6. Applicant-tracking checks</h2>
  <p>ATS readiness score: <strong>{feedback['ats_score']}/100</strong></p>
  <table>
    <caption>Machine-readability checks</caption>
    <thead><tr><th scope="col">Check</th><th scope="col">Result</th><th scope="col">Note</th></tr></thead>
    <tbody>{ats_rows}</tbody>
  </table>
</section>

<section aria-labelledby="parsed">
  <h2 id="parsed">7. What the parser found</h2>
  <table>
    <caption>Extracted resume facts</caption>
    <tbody>
      <tr><th scope="row">Words</th><td>{parsed.get('word_count', 0)}</td></tr>
      <tr><th scope="row">Sections detected</th><td>{_e(', '.join(parsed.get('section_names', [])) or 'None')}</td></tr>
      <tr><th scope="row">Experience</th><td>{parsed.get('total_years', 0)} year(s) \u00b7 {len(parsed.get('experience', []))} dated role(s)</td></tr>
      <tr><th scope="row">Education</th><td>{_e(parsed.get('education_label', 'Not detected'))}</td></tr>
      <tr><th scope="row">Skills detected</th><td>{_e(', '.join(parsed.get('skills', [])) or 'None')}</td></tr>
      <tr><th scope="row">Quantified achievements</th><td>{len(parsed.get('quantified', []))}</td></tr>
    </tbody>
  </table>
  <h3>Dated roles</h3>
  <ul>{roles}</ul>
</section>

<section aria-labelledby="limits">
  <h2 id="limits">8. Limitations</h2>
  {_list(verdict['limitations'])}
  <div class="note">
    <strong>Human accountability.</strong> FairHire never rejects a candidate automatically. The weakest
    outcome is \u201climited evidence \u2014 human review needed\u201d. A reviewer must check the quoted evidence
    and the role criteria before acting. Identity signals (name, gender, age, institution, location) are
    not scoring features.
  </div>
</section>

<footer>
  Generated by FairHire \u00b7 Team ByteForce \u00b7 OlympAI Hackathon. This report contains candidate
  information; handle it according to your organisation's data protection policy.
</footer>
</div>
</body>
</html>"""
    return html
