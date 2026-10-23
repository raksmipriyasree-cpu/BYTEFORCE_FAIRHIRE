"""FairHire — explainable, human-led resume screening.

Stage 2: real resume analysis, evidence-backed decisions, plain-language
reasons for and against, resume-improvement feedback, and an accessible UI.
"""
import hashlib
import json
import os
import re
from html import escape as h

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from fairhire import emailer, fairness
from fairhire.analyzer import DEFAULT_WEIGHTS, FEATURES, analyze_single
from fairhire.data_loader import read_resume_file
from fairhire.db import STATUSES, Store
from fairhire.demo import rank_job
from fairhire.report import build_report_html
from fairhire.taxonomy import ROLE_ORDER, ROLE_PROFILES, get_profile

PINS = {"HR Recruiter": os.environ.get("FAIRHIRE_HR_PIN", "hr123"),
        "Company Head": os.environ.get("FAIRHIRE_HEAD_PIN", "head123")}


def _role_jobs():
    """Build the five vacancy definitions from the competency taxonomy."""
    jobs = []
    for role in ROLE_ORDER:
        profile = ROLE_PROFILES[role]
        jobs.append({
            "title": role,
            "category": role,
            "description": profile["summary"],
            "required": [c["label"] for c in profile["competencies"] if c["core"]],
            "nice": [c["label"] for c in profile["competencies"] if not c["core"]],
            "min_years": 0,
            "min_edu": 1,
        })
    return jobs


CATEGORY_JOBS = _role_jobs()


def ensure_categories(store):
    """Create only the five vacancy/category definitions, never sample applicants."""
    existing = {j["category"].casefold() for j in store.get_jobs()}
    for job in CATEGORY_JOBS:
        if job["category"].casefold() not in existing:
            store.add_job(job, actor="FairHire setup")


# ---------------------------------------------------------------------------
# Accessible theme
# ---------------------------------------------------------------------------
def _theme_css(high_contrast, large_text, reduce_motion):
    if high_contrast:
        p = {"ink": "#ffffff", "muted": "#e8e8e8", "paper": "#000000", "panel": "#141414",
             "green": "#ffd0dc", "green2": "#6d1735", "clay": "#e8a6b8", "line": "#9a9a9a",
             "focus": "#ffd479"}
    else:
        p = {"ink": "#f8edf1", "muted": "#d0b9c1", "paper": "#170d12", "panel": "#28151e",
             "green": "#d58aa2", "green2": "#6d1735", "clay": "#e8a6b8", "line": "#583044",
             "focus": "#ffd479"}
    size = "19px" if large_text else "16px"
    root = (":root{--ink:%s;--muted:%s;--paper:%s;--panel:%s;--green:%s;--green2:%s;"
            "--clay:%s;--line:%s;--focus:%s;--accent:%s;--quote-bg:%s;--quote-fg:%s;}"
            % (p["ink"], p["muted"], p["paper"], p["panel"], p["green"], p["green2"], p["clay"],
               p["line"], p["focus"], p["green"], p["panel"], p["ink"]))
    css = """
html,body,.stApp{font-size:__SIZE__;background:var(--paper);color:var(--ink)}
.stApp{background:radial-gradient(ellipse at 80% 0%,#351324 0%,var(--paper) 54%)}
[data-testid="stHeader"]{background:rgba(0,0,0,.35)}
h1,h2,h3,h4{color:var(--ink)!important;letter-spacing:-.03em;line-height:1.2}
p,label,.stMarkdown,[data-testid="stCaptionContainer"]{color:var(--ink)}
[data-testid="stCaptionContainer"]{color:var(--muted)}
[data-testid="stMetric"]{background:linear-gradient(145deg,#38202b,#21121a);border:1px solid var(--line);padding:16px 18px;border-radius:15px}
[data-testid="stMetricLabel"]{color:var(--muted)!important;font-size:.9rem}
[data-testid="stMetricValue"]{color:#e6f2e6!important}
.stButton>button,.stDownloadButton>button{background:var(--green2);color:#ffffff;border:2px solid var(--clay);border-radius:10px;font-weight:700;min-height:2.9rem}
.stButton>button:hover,.stDownloadButton>button:hover{background:#8b3154;color:#fff;border-color:#f0c0cf}
.stButton>button:focus-visible,.stDownloadButton>button:focus-visible{outline:3px solid var(--focus)!important;outline-offset:3px!important}
.stTabs [data-baseweb="tab-list"]{gap:10px;border-bottom:2px solid var(--line);flex-wrap:wrap}
.stTabs [data-baseweb="tab"]{border-radius:9px 9px 0 0;color:var(--muted);font-weight:650;padding:.6rem .9rem}
.stTabs [aria-selected="true"]{color:var(--clay)!important;border-bottom:4px solid var(--clay)!important}
[data-testid="stExpander"]{background:rgba(29,41,33,.9);border:1px solid var(--line);border-radius:12px}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:12px;overflow:hidden}
div[data-baseweb="select"]>div,.stTextInput input,.stTextArea textarea{border:2px solid #5d7364;border-radius:9px;background:#1b261f;color:#f2f6ef;font-size:1rem}
div[data-baseweb="select"]>div:focus-within,.stTextInput input:focus,.stTextArea textarea:focus{outline:3px solid var(--focus)!important;outline-offset:2px!important;border-color:var(--focus)}
.fh-brand{font-size:.8rem;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:var(--clay);margin-bottom:.4rem}
.fh-hero{padding:2rem 2.1rem;border-radius:20px;background:linear-gradient(120deg,#24111a,#6d1735 68%,#8b3154);color:#fff;margin:.4rem 0 1.3rem;border:2px solid #a75b77}
.fh-hero h1,.fh-hero h2{color:#fff!important;margin:.2rem 0 .6rem;line-height:1.08}
.fh-hero p{color:#e2ece0!important;font-size:1.05rem;max-width:820px}
.fh-card{height:100%;background:linear-gradient(150deg,#38202b,#21121a);border:1px solid var(--line);border-radius:16px;padding:1.2rem 1.3rem;min-height:150px}
.fh-label{font-size:.76rem;font-weight:800;letter-spacing:.13em;text-transform:uppercase;color:var(--clay)}
.fh-small{color:var(--muted);font-size:.95rem}
.fh-quote{display:inline-block;margin-top:.35rem;padding:.15rem .55rem;border-left:3px solid var(--accent);background:var(--quote-bg);color:var(--quote-fg);font-style:italic;font-size:.95rem;border-radius:0 6px 6px 0}
.fh-note{padding:1rem 1.1rem;border-radius:12px;background:#351c29;border:1px solid #754057;color:#f8edf1;border-left:6px solid var(--green)}
.fh-stage{background:#28151e;border:1px solid var(--line);border-radius:12px;padding:.85rem 1rem;min-height:96px}
.fh-stage-num{color:var(--clay);font-size:.72rem;font-weight:800;letter-spacing:.15em}
.fh-stage-title{color:var(--ink);font-weight:750;margin:.2rem 0}
.fh-stage-copy{color:var(--muted);font-size:.82rem}
.fh-pill{display:inline-block;padding:.25rem .7rem;border-radius:999px;font-size:.85rem;font-weight:750;border:2px solid currentColor}
.fh-pill.good{color:#ffd0dc;background:#4a1930}
.fh-pill.warn{color:#ffe0a6;background:#4b2c1d}
.fh-pill.bad{color:#ffb4c0;background:#4b1726}
.fh-pill.neutral{color:var(--muted);background:var(--panel)}
.fh-verdict{border:2px solid var(--line);border-radius:16px;padding:1.1rem 1.3rem;background:var(--panel);margin:.4rem 0 1rem}
.fh-verdict .score{font-size:2.6rem;font-weight:850;line-height:1;letter-spacing:-.03em}
.fh-verdict .score small{font-size:1rem;color:var(--muted);font-weight:600}
.fh-for{border-left:6px solid #d58aa2;background:#261c25;border-radius:10px;padding:.9rem 1.1rem}
.fh-against{border-left:6px solid #e8a6b8;background:#35202a;border-radius:10px;padding:.9rem 1.1rem}
.fh-quote{font-style:italic;color:#d8e6d6}
.fh-skip{position:absolute;left:-9999px;top:0;background:#ffd479;color:#000;padding:.7rem 1rem;font-weight:800;border-radius:0 0 8px 0;z-index:99999}
.fh-skip:focus{left:0}
a:focus-visible,[role="tab"]:focus-visible,[role="button"]:focus-visible{outline:3px solid var(--focus)!important;outline-offset:3px!important}
hr{border-color:var(--line)!important}
[data-testid="stAlert"]{border:2px solid var(--line)}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}
@media (max-width:760px){.fh-hero{padding:1.3rem}.fh-verdict .score{font-size:2rem}}
"""
    css = css.replace("__SIZE__", size)
    if reduce_motion:
        css += "*{animation:none!important;transition:none!important;scroll-behavior:auto!important}"
    return "<style>" + root + css + "</style>"


# ---------------------------------------------------------------------------
# Small render helpers
# ---------------------------------------------------------------------------
def _pill(text, tone="neutral"):
    tone = tone if tone in ("good", "warn", "bad", "neutral") else "neutral"
    return f'<span class="fh-pill {tone}">{h(str(text))}</span>'


def _render_item(item):
    """Render one reason. Reasons may be plain strings or structured dicts
    with a short label, a sentence of detail and an optional quoted snippet."""
    if isinstance(item, dict):
        label = str(item.get("label", "")).strip()
        detail = str(item.get("detail", "")).strip()
        evidence = str(item.get("evidence", "") or "").strip()
        strength = item.get("strength")
        parts = []
        if label:
            parts.append(f"<b>{h(label)}</b>")
        if detail:
            parts.append(h(detail))
        text = " \u2014 ".join(parts) if parts else h(str(item))
        if strength is not None:
            try:
                text += f" <span class='fh-small'>Evidence strength {float(strength) * 100:.0f}%.</span>"
            except (TypeError, ValueError):
                pass
        if evidence:
            snippet = evidence if len(evidence) <= 220 else evidence[:217].rstrip() + "\u2026"
            text += f"<br><span class='fh-quote'>\u201c{h(snippet)}\u201d</span>"
        return text
    return h(str(item))


def _reason_text(item):
    """Plain-text version of a reason, for places that cannot use HTML."""
    if isinstance(item, dict):
        label = str(item.get("label", "")).strip()
        detail = str(item.get("detail", "")).strip()
        return " \u2014 ".join(p for p in (label, detail) if p)
    return str(item)


def _bullets(items, empty="None recorded."):
    if not items:
        return f"<p class='fh-small'>{h(empty)}</p>"
    return "<ul>" + "".join(f"<li>{_render_item(i)}</li>" for i in items) + "</ul>"


def _verdict_panel(st, verdict, score):
    tone = verdict.get("tone", "neutral")
    st.markdown(
        f"""<div class="fh-verdict">
        <div style="display:flex;gap:1.4rem;align-items:center;flex-wrap:wrap">
          <div><div class="score">{score:.1f}<small>/100</small></div>
          <div class="fh-small">Match score</div></div>
          <div style="flex:1;min-width:240px">
            <div style="margin-bottom:.35rem">{_pill(verdict.get('label', 'Pending review'), tone)}</div>
            <div class="fh-small">Confidence: <b>{h(verdict.get('confidence', '—'))}</b> &mdash; {h(verdict.get('confidence_reason', ''))}</div>
            <div class="fh-small">Core coverage {float(verdict.get('core_coverage', 0))*100:.0f}% &middot; Preferred coverage {float(verdict.get('preferred_coverage', 0))*100:.0f}%</div>
          </div>
        </div>
        <p style="margin:.8rem 0 0">{h(verdict.get('summary', ''))}</p>
        </div>""",
        unsafe_allow_html=True,
    )


def _reasons_panel(st, verdict):
    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown(
            '<div class="fh-for"><h4 style="margin-top:0">✔ Reasons for</h4>'
            + _bullets(verdict.get("reasons_for"), "No supporting evidence was found.")
            + "</div>", unsafe_allow_html=True)
    with right:
        st.markdown(
            '<div class="fh-against"><h4 style="margin-top:0">✖ Reasons against</h4>'
            + _bullets(verdict.get("reasons_against"), "No material gaps were found.")
            + "</div>", unsafe_allow_html=True)
    with st.expander("What would change this decision? (counterfactuals)", expanded=False):
        st.markdown(_bullets(verdict.get("counterfactuals"), "No counterfactual could be computed."),
                    unsafe_allow_html=True)


def _evidence_table(st, criteria):
    rows = []
    for c in criteria:
        rows.append({
            "Competency": c["label"],
            "Type": "Core" if c["core"] else "Preferred",
            "Status": "Evidence found" if c["matched"] else "No evidence found",
            "Strength": f"{c['strength']*100:.0f}%",
            "Weight": f"{c['weight']:.2f}",
            "Evidence from the resume": " | ".join(f"\u201c{e['snippet']}\u201d" for e in c["evidence"][:2]) or "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                 column_config={"Evidence from the resume": st.column_config.TextColumn(width="large")})


def _feedback_panel(st, feedback):
    st.markdown("#### What this resume does well")
    for s in feedback.get("strengths", []):
        ev = f" — <span class='fh-quote'>{h(s['evidence'])}</span>" if s.get("evidence") else ""
        st.markdown(f"- **{h(s['label'])}**{ev}", unsafe_allow_html=True)
    st.markdown("#### Gaps a reviewer will look for")
    if feedback.get("gaps"):
        for g in feedback["gaps"]:
            st.markdown(f"- **{h(g['label'])}** — {h(g.get('why',''))}")
    else:
        st.caption("No core gaps detected in the readable text.")
    st.markdown("#### Concrete improvements (inputs for the candidate)")
    for i, s in enumerate(feedback.get("suggestions", []), 1):
        st.markdown(f"{i}. {s}")
    if not feedback.get("suggestions"):
        st.caption("No improvements suggested.")
    txt = "\n".join([f"Strengths: {s['label']} - {s.get('evidence','')}" for s in feedback.get("strengths", [])]
                    + [f"Gap: {g['label']} - {g.get('why','')}" for g in feedback.get("gaps", [])]
                    + [f"Improvement {i}: {s}" for i, s in enumerate(feedback.get("suggestions", []), 1)])
    st.download_button("Download this feedback (.txt)", txt.encode("utf-8"),
                       "fairhire_resume_feedback.txt", "text/plain", key="dl_feedback")


def _ats_panel(st, feedback):
    st.markdown(f"**ATS readiness: {feedback.get('ats_score', 0)}/100**")
    rows = [{"Check": c["check"], "Result": "Pass" if c["pass"] else "Fix", "Note": c["note"]}
            for c in feedback.get("ats", [])]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _parsed_panel(st, parsed):
    a, b, c = st.columns(3)
    a.metric("Words", parsed.get("word_count", 0))
    b.metric("Years detected", parsed.get("total_years", 0))
    c.metric("Dated roles", len(parsed.get("experience", [])))
    st.markdown(f"**Sections detected:** {', '.join(parsed.get('section_names', [])) or 'None'}")
    st.markdown(f"**Education:** {h(parsed.get('education_label', 'Not detected'))}")
    st.markdown(f"**Skills detected:** {', '.join(parsed.get('skills', [])) or 'None'}")
    if parsed.get("experience"):
        st.markdown("**Dated roles**")
        for r in parsed["experience"]:
            st.markdown(f"- **{h(r.get('title') or 'Role')}** — {h(r.get('dates') or '')}")
    st.caption("Identity details (name, email, phone, links) are parsed for contact only and are never scoring features.")


def _feature_chart(st, features, weights, key):
    w = {f: max(float((weights or DEFAULT_WEIGHTS).get(f, 0.0)), 0.0) for f in FEATURES}
    total = sum(w.values()) or 1.0
    w = {f: v / total for f, v in w.items()}
    points = {f: w[f] * float(features.get(f, 0.0)) * 100 for f in FEATURES}
    labels = {"skill_match": "Core competencies", "nice_skills": "Preferred competencies",
              "experience": "Experience", "education": "Education", "text_match": "Role language"}
    df = pd.DataFrame({"Component": [labels[f] for f in FEATURES],
                       "Points": [round(points[f], 2) for f in FEATURES],
                       "Level": [f"{float(features.get(f,0))*100:.0f}%" for f in FEATURES],
                       "Weight": [f"{w[f]*100:.0f}%" for f in FEATURES]})
    fig = px.bar(df, x="Points", y="Component", orientation="h", text="Points",
                 color="Component", color_discrete_sequence=["#7fb08b", "#a8c4ad", "#d0b184", "#8fb0bd", "#c2a6c9"])
    fig.update_layout(template="plotly_dark", height=280, showlegend=False,
                      margin=dict(l=8, r=12, t=10, b=8), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#eef3ec", size=13),
                      xaxis_title="Points contributed (out of 100)")
    fig.update_traces(texttemplate="%{text:.1f}", textposition="outside", cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=key)
    st.caption("Chart alternative: the same values are listed in the table below.")
    with st.expander("View score components as a table"):
        st.dataframe(df, use_container_width=True, hide_index=True)


def _waterfall(st, row, key):
    contribution_values = [float(row["contribs"].get(f, 0.0)) for f in FEATURES]
    fig = go.Figure(go.Waterfall(
        name="Score decomposition", orientation="v",
        measure=["absolute"] + ["relative"] * len(FEATURES) + ["total"],
        x=["Pool baseline"] + [f.replace("_", " ").title() for f in FEATURES] + ["Final score"],
        y=[float(row["base_value"])] + contribution_values + [float(row["score"])],
        connector={"line": {"color": "#8a9b8d"}},
        increasing={"marker": {"color": "#7fb08b"}},
        decreasing={"marker": {"color": "#e3a184"}},
        totals={"marker": {"color": "#e2d9c8"}},
    ))
    fig.update_layout(template="plotly_dark", height=340, margin=dict(l=8, r=8, t=24, b=8),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      yaxis_title="Score points", showlegend=False, font=dict(color="#eef3ec", size=13))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=key)
    st.caption("Chart alternative: baseline plus each contribution equals the final score exactly.")
    with st.expander("View score decomposition as a table"):
        tbl = pd.DataFrame({"Component": ["Pool baseline"] + [f.replace("_", " ").title() for f in FEATURES] + ["Final score"],
                            "Points": [round(float(row["base_value"]), 2)] + [round(v, 2) for v in contribution_values] + [round(float(row["score"]), 2)]})
        st.dataframe(tbl, use_container_width=True, hide_index=True)


def _report_button(st, result, job, filename, key):
    html = build_report_html(result, job, filename)
    st.download_button("Download full analysis report (HTML)", html.encode("utf-8"),
                       f"FairHire_analysis_{re.sub(r'[^A-Za-z0-9_-]+', '_', filename)}.html",
                       "text/html", key=key)


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------
def run_app():
    import streamlit as st

    st.set_page_config(page_title="FairHire | Fair recruitment", page_icon="◈",
                       layout="wide", initial_sidebar_state="expanded")

    if "a11y" not in st.session_state:
        st.session_state.a11y = {"high_contrast": False, "large_text": False, "reduce_motion": False}
    a11y = st.session_state.a11y

    with st.sidebar:
        st.markdown("### Accessibility")
        a11y["large_text"] = st.toggle("Larger text", value=a11y["large_text"], help="Increase the base font size across the app.")
        a11y["high_contrast"] = st.toggle("High contrast", value=a11y["high_contrast"], help="Black background with bright, high-contrast text and borders.")
        a11y["reduce_motion"] = st.toggle("Reduce motion", value=a11y["reduce_motion"], help="Turn off animations and transitions.")
        st.caption("Tip: use Tab to move between controls and Enter to activate them. Every chart has a text-table alternative.")

    st.markdown(_theme_css(a11y["high_contrast"], a11y["large_text"], a11y["reduce_motion"]), unsafe_allow_html=True)
    st.markdown('<a class="fh-skip" href="#fh-main">Skip to main content</a>', unsafe_allow_html=True)
    st.markdown('<div id="fh-main" tabindex="-1"></div>', unsafe_allow_html=True)

    @st.cache_resource
    def get_store():
        store = Store("fairhire_uploads.db")
        ensure_categories(store)
        return store

    store = get_store()
    if "workspace" not in st.session_state:
        st.session_state.workspace = None

    if st.session_state.workspace is None:
        _home(st, store)
        return

    role = st.session_state.workspace
    top_l, top_r = st.columns([5, 1])
    top_l.markdown(f'<div class="fh-brand">◈ FAIRHIRE / {h(role.upper())}</div>', unsafe_allow_html=True)
    if top_r.button("← Home", use_container_width=True):
        st.session_state.workspace = None
        st.rerun()

    weights = {}
    with st.sidebar.expander("Scoring settings", expanded=False):
        st.caption("Weights are normalised to 100%. Changing them re-scores every candidate.")
        for f in FEATURES:
            weights[f] = st.slider(f.replace("_", " ").title(), 0.0, 1.0,
                                   float(DEFAULT_WEIGHTS[f]), 0.05, key="weight_" + f)
    with st.sidebar.expander("How scoring works", expanded=False):
        st.markdown(
            "**Score = 100 × Σ (weight × feature)**\n\n"
            "- **Core competencies** — weighted evidence coverage\n"
            "- **Preferred competencies** — optional capability coverage\n"
            "- **Experience** — years detected vs. role requirement\n"
            "- **Education** — highest degree vs. role requirement\n"
            "- **Role language** — share of the role's key terms present\n\n"
            "The model is linear, so each contribution is exact. This is **not** SHAP; "
            "it is a direct decomposition that adds up to the score.")

    if role == "HR Recruiter":
        hr_view(st, store, weights)
    else:
        head_view(st, store)


def _home(st, store):
    st.markdown('<div class="fh-brand">◈ FairHire / Recruitment intelligence</div>', unsafe_allow_html=True)
    st.markdown('''<div class="fh-hero"><div class="fh-brand" style="color:#f0c3a8">EXPLAINABLE · BIAS-AWARE · HUMAN-LED</div>
    <h1>Welcome to FairHire.</h1><p>Upload real resumes, understand every match, see exactly why a candidate is recommended or not, and keep hiring decisions in human hands.</p></div>''', unsafe_allow_html=True)
    total = len(store.candidates())
    st.markdown("""<div class='fh-brand'>SYSTEM OVERVIEW / PIPELINE STATUS</div>
    <div style='display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:.4rem 0 1.2rem 0'>
      <div class='fh-stage'><div class='fh-stage-num'>01 / INGEST</div><div class='fh-stage-title'>Document intake</div><div class='fh-stage-copy'>PDF validation · text extraction</div></div>
      <div class='fh-stage'><div class='fh-stage-num'>02 / UNDERSTAND</div><div class='fh-stage-title'>Evidence engine</div><div class='fh-stage-copy'>Sections · dates · competencies</div></div>
      <div class='fh-stage'><div class='fh-stage-num'>03 / EXPLAIN</div><div class='fh-stage-title'>Decision support</div><div class='fh-stage-copy'>Reasons for · against · counterfactuals</div></div>
      <div class='fh-stage'><div class='fh-stage-num'>04 / GOVERN</div><div class='fh-stage-title'>Human approval</div><div class='fh-stage-copy'>Review states · traceable actions</div></div>
    </div>""", unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.metric("Applications in this workspace", total)
    b.metric("Role categories", len(CATEGORY_JOBS))
    c.metric("Auto-sent decisions", "0")
    st.markdown("### Choose your workspace")
    st.caption("No demo applicants are preloaded — the applicant list stays empty until you upload resumes.")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown('<div class="fh-card"><div class="fh-label">01 / Recruitment</div><h3>HR Recruiter</h3><p class="fh-small">Analyse a single resume, upload a pool, review match explanations, manage the shortlist and prepare candidate communication.</p></div>', unsafe_allow_html=True)
        if st.button("Enter HR workspace  →", key="home_hr", use_container_width=True):
            st.session_state.workspace = "HR Recruiter"
            st.rerun()
    with right:
        st.markdown('<div class="fh-card"><div class="fh-label">02 / Leadership</div><h3>Company Head</h3><p class="fh-small">Review HR recommendations, approve or return shortlist decisions, and inspect decision history and fairness limitations.</p></div>', unsafe_allow_html=True)
        if st.button("Enter Company Head workspace  →", key="home_head", use_container_width=True):
            st.session_state.workspace = "Company Head"
            st.rerun()
    st.markdown("<div class='fh-note'><b>FairHire principle:</b> the score is a decision-support signal, not an automatic hiring decision. A human reviewer remains responsible for every outcome.</div>", unsafe_allow_html=True)


def job_picker(st, store, key, label="Role category"):
    jobs = store.get_jobs()
    return st.selectbox(label, jobs, key=key, format_func=lambda j: j["title"])


def _resume_name(text, filename):
    for line in (text or "").splitlines()[:8]:
        line = line.strip()
        if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,48}", line) and len(line.split()) <= 5:
            if not re.search(r"resume|curriculum|vitae|profile|contact|email|phone", line, re.I):
                return line
    return os.path.splitext(os.path.basename(filename))[0].replace("_", " ").replace("-", " ").strip() or "Unnamed applicant"


# ---------------------------------------------------------------------------
# HR workspace
# ---------------------------------------------------------------------------
def hr_view(st, store, weights):
    st.markdown('<div class="fh-hero"><div class="fh-brand" style="color:#f0c3a8">HR WORKSPACE</div><h2>Applications, reviewed with evidence.</h2><p>Analyse one resume in depth, or upload a pool and compare candidates. Every result states why it was reached and what would change it.</p></div>', unsafe_allow_html=True)
    all_candidates = store.candidates()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Uploaded applications", len(all_candidates))
    m2.metric("Role categories", len(store.get_jobs()))
    m3.metric("Awaiting head approval", int(((all_candidates["hr_decision"] == "accepted") & (all_candidates["head_decision"] != "approved")).sum()) if len(all_candidates) else 0)
    mails = store.emails()
    m4.metric("Email drafts", int(mails["status"].isin(["draft", "confirmed"]).sum()) if len(mails) else 0)

    tab_desk, tab_review, tab_pipeline = st.tabs(
        ["Recruitment desk · Upload + Analyse", "Review & ranking", "Pipeline & communication"])

    with tab_desk:
        _recruitment_desk(st, store, weights)
    with tab_review:
        _review_tab(st, store, weights)
    with tab_pipeline:
        _pipeline_tab(st, store)


def _recruitment_desk(st, store, weights):
    """One combined intake, analysis, recommendation and HR-decision workspace."""
    st.subheader("Upload, analyse and decide — in one workspace")
    st.write("Select a vacancy and upload one or more real resumes. FairHire extracts text, scores job-related evidence, explains gaps and suggests a review action. HR controls the next step.")
    job = job_picker(st, store, "desk_role", "Vacancy / role")
    files = st.file_uploader("Upload resume(s) · PDF, DOCX or TXT", type=["pdf", "docx", "txt"],
                             accept_multiple_files=True, key="desk_resume_upload")
    st.caption("Text-based PDFs work best. Scanned/image-only PDFs need OCR. Only files you upload become applicant records.")
    if files and st.button("Analyse & add to applicant pool", type="primary", use_container_width=True, key="desk_import"):
        added, skipped, failed = 0, 0, []
        for file in files:
            try:
                raw = file.getvalue()
                if not raw:
                    failed.append(f"{file.name}: empty file")
                    continue
                text = read_resume_file(file.name, raw).strip()
                if len(text) < 30:
                    failed.append(f"{file.name}: too little selectable text; this may be a scanned PDF")
                    continue
                existing = store.candidates(job["id"])
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if not existing.empty and any(hashlib.sha256(str(t).encode("utf-8")).hexdigest() == digest for t in existing["text"].tolist()):
                    skipped += 1
                    continue
                mail = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
                name = _resume_name(text, file.name)
                store.add_candidate(job["id"], name, mail.group(0) if mail else "", text, "", job["category"], "HR Recruiter")
                added += 1
            except Exception as exc:
                failed.append(f"{file.name}: {exc}")
        if added:
            rank_job(store, job["id"], weights, "HR Recruiter")
            st.success(f"Analysed and added {added} resume(s) for {job['title']}.")
        if skipped:
            st.info(f"Skipped {skipped} duplicate resume(s).")
        if failed:
            st.warning("Some files could not be processed: " + "; ".join(failed))
        st.rerun()

    cands = store.candidates(job["id"])
    st.markdown("### Live results for this vacancy")
    if cands.empty:
        st.info("No resumes yet. Upload files above to populate this table.")
    else:
        if st.button("Refresh analysis", key="desk_refresh"):
            rank_job(store, job["id"], weights, "HR Recruiter")
            st.rerun()
        rows=[]
        for _, r in cands.sort_values("rank", na_position="last").iterrows():
            v = r["verdict"] if isinstance(r["verdict"], dict) else {}
            rows.append({"ID": int(r["id"]), "Applicant": r["name"], "Match": round(float(r["score"] or 0),1),
                         "AI review suggestion": v.get("label", "Needs review"), "HR decision": r.get("hr_decision", "pending"),
                         "Head approval": r.get("head_decision", "pending"), "Pipeline": r["status"]})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        ids = cands["id"].astype(int).tolist()
        chosen = st.selectbox("Open applicant review", ids, key="desk_chosen",
                              format_func=lambda i: f"Application #{i} · {cands.loc[cands['id']==i, 'name'].iloc[0]}")
        row = cands[cands["id"] == chosen].iloc[0]
        verdict = row["verdict"] if isinstance(row["verdict"], dict) else {}
        st.markdown("#### AI-assisted recommendation")
        _verdict_panel(st, verdict, float(row["score"] or 0))
        _reasons_panel(st, verdict)
        criteria = row["criteria"] if isinstance(row["criteria"], list) else []
        if criteria:
            st.markdown("#### Evidence found against each requirement")
            _evidence_table(st, criteria)
        st.markdown("#### HR decision")
        st.caption("AI suggests; HR accepts, rejects, or leaves the applicant pending. Accepting sends the recommendation to the Company Head for approval. No applicant is automatically rejected.")
        note = st.text_area("HR review note", value=str(row.get("notes", "") or ""), key=f"desk_note_{chosen}")
        d1, d2, d3 = st.columns(3)
        if d1.button("Accept & send to Head", type="primary", key=f"desk_accept_{chosen}", use_container_width=True):
            store.set_note(int(chosen), note, "HR Recruiter")
            store.set_status(int(chosen), "Shortlisted", "HR Recruiter")
            store.set_hr_decision(int(chosen), "accepted", "HR Recruiter")
            st.success("HR recommendation sent to Company Head for approval. Any candidate email remains a draft for HR review.")
            st.rerun()
        if d2.button("Reject applicant", key=f"desk_reject_{chosen}", use_container_width=True):
            store.set_note(int(chosen), note, "HR Recruiter")
            store.set_hr_decision(int(chosen), "rejected", "HR Recruiter")
            st.success("HR rejection recorded. This is a human decision; confirm vacancy criteria and evidence before communicating an outcome.")
            st.rerun()
        if d3.button("Keep pending", key=f"desk_pending_{chosen}", use_container_width=True):
            store.set_note(int(chosen), note, "HR Recruiter")
            store.set_hr_decision(int(chosen), "pending", "HR Recruiter")
            st.info("Applicant remains pending for further human review.")
            st.rerun()

    with st.expander("Vacancy criteria and role profile"):
        profile = get_profile(job["title"])
        st.write(profile.get("summary", job["description"]))
        comp = pd.DataFrame([{"Competency": c["label"], "Type": "Core" if c["core"] else "Preferred",
                              "Weight": c["weight"], "Evidence guidance": c["hint"]} for c in profile["competencies"]])
        st.dataframe(comp, use_container_width=True, hide_index=True)
        st.caption("Review and tailor role criteria before using the score for any real hiring decision.")


def _analyzer_tab(st, store, weights):
    st.subheader("Analyse one resume")
    st.write("Choose a role, then upload a resume or paste its text. You will get a score, the evidence behind it, "
             "reasons for and against, what would change the decision, and concrete resume improvements.")
    jobs = store.get_jobs()
    role_titles = [j["title"] for j in jobs]
    c1, c2 = st.columns([1, 2])
    with c1:
        role_title = st.selectbox("Role to assess against", role_titles, key="an_role")
        job = next(j for j in jobs if j["title"] == role_title)
        method = st.radio("Resume input", ["Upload a file", "Paste text"], key="an_method", horizontal=True)
    with c2:
        text, filename = "", "pasted_resume"
        if method == "Upload a file":
            up = st.file_uploader("Resume file (PDF, DOCX or TXT)", type=["pdf", "docx", "txt"], key="an_file")
            if up is not None:
                filename = up.name
                try:
                    text = read_resume_file(up.name, up.getvalue()).strip()
                except Exception as exc:
                    st.error(f"Could not read this file: {exc}")
            st.caption("Text-based PDFs work best. Scanned image-only PDFs need OCR.")
        else:
            text = st.text_area("Paste resume text", height=240, key="an_text",
                                placeholder="Paste the full resume text here…")

    run = st.button("Analyse resume", type="primary", use_container_width=True, key="an_run")
    if run:
        if not text or len(text.strip()) < 40:
            st.warning("Please upload a resume or paste at least a few lines of text.")
        else:
            with st.spinner("Parsing the resume and checking evidence for each competency…"):
                result = analyze_single(text, job, weights)
            st.session_state["an_result"] = {"result": result, "job": job, "filename": filename}

    saved = st.session_state.get("an_result")
    if not saved:
        st.markdown("<div class='fh-note'>Nothing analysed yet. Pick a role and add a resume above. "
                    "The analysis never auto-rejects: the weakest outcome is “limited evidence — human review needed”.</div>",
                    unsafe_allow_html=True)
        return

    result, job, filename = saved["result"], saved["job"], saved["filename"]
    verdict, feedback, evaluation = result["verdict"], result["feedback"], result["evaluation"]
    st.markdown("---")
    st.markdown(f"### Result for **{h(job['title'])}** · `{h(filename)}`")
    _verdict_panel(st, verdict, result["score"])
    _reasons_panel(st, verdict)

    st.markdown("### How the score is built")
    _feature_chart(st, result["features"], weights, "an_feature_chart")

    st.markdown("### Competency evidence")
    st.caption("Each row shows the sentence in the resume that triggered the match. “No evidence found” means the wording was not detected — not that the person lacks the skill.")
    _evidence_table(st, evaluation["criteria"])

    st.markdown("### Resume feedback")
    _feedback_panel(st, feedback)

    f1, f2 = st.columns(2)
    with f1:
        st.markdown("### ATS checks")
        _ats_panel(st, feedback)
    with f2:
        st.markdown("### What the parser found")
        _parsed_panel(st, evaluation["parsed"])

    st.markdown("### Limitations and accountability")
    st.markdown(_bullets(verdict.get("limitations")), unsafe_allow_html=True)
    st.markdown("<div class='fh-note'><b>Human accountability.</b> This is decision support, not a hiring decision. "
                "Check the quoted evidence and the role criteria before acting. Identity signals are not scoring features.</div>",
                unsafe_allow_html=True)
    _report_button(st, result, job, filename, "an_report")


def _upload_tab(st, store, weights):
    st.subheader("Add applications to a pool")
    st.write("Choose the role that best matches the application. Only files you upload are added as applicants.")
    job = job_picker(st, store, "upload_role")
    st.markdown("**Available role profiles**")
    cats = st.columns(5)
    for col, item in zip(cats, CATEGORY_JOBS):
        col.markdown(f'<div class="fh-card" style="padding:.8rem;min-height:100px"><div class="fh-label">ROLE</div><b>{h(item["title"])}</b></div>', unsafe_allow_html=True)

    st.markdown("#### Upload resumes")
    files = st.file_uploader("Select one or more resume files", type=["pdf", "docx", "txt"],
                             accept_multiple_files=True, key="resume_upload")
    st.caption("PDF, DOCX and TXT are supported. Text-based PDFs work best; scanned image-only PDFs need OCR.")
    if files and st.button("Import uploaded resumes", type="primary", use_container_width=True):
        added, skipped, failed = 0, 0, []
        for file in files:
            content = file.getvalue()
            if not content:
                failed.append(f"{file.name}: empty file")
                continue
            try:
                text = read_resume_file(file.name, content).strip()
                if len(text) < 30:
                    failed.append(f"{file.name}: little or no selectable text found; this may be a scanned PDF")
                    continue
                existing = store.candidates(job["id"])
                if not existing.empty and any(
                        hashlib.sha256(str(t).encode("utf-8")).hexdigest() == hashlib.sha256(text.encode("utf-8")).hexdigest()
                        for t in existing["text"].tolist()):
                    skipped += 1
                    continue
                mail = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
                name = _resume_name(text, file.name)
                store.add_candidate(job["id"], name, mail.group(0) if mail else "", text, "", job["category"], "HR Recruiter")
                added += 1
            except Exception as exc:
                failed.append(f"{file.name}: {exc}")
        if added:
            rank_job(store, job["id"], weights, "HR Recruiter")
            st.success(f"Added {added} uploaded resume(s) to {job['title']}; rankings and explanations refreshed.")
        if skipped:
            st.info(f"Skipped {skipped} duplicate resume(s) in this category.")
        if failed:
            st.warning("Some files could not be imported: " + "; ".join(failed))
        st.rerun()

    st.markdown("#### Current role profile")
    profile = get_profile(job["title"])
    st.write(profile.get("summary", job["description"]))
    comp = pd.DataFrame([{
        "Competency": c["label"], "Type": "Core" if c["core"] else "Preferred",
        "Weight": c["weight"], "What counts as evidence": c["hint"],
    } for c in profile["competencies"]])
    st.dataframe(comp, use_container_width=True, hide_index=True)

    with st.expander("Edit this role's requirements"):
        desc = st.text_area("Role description", value=job["description"], key="edit_desc_" + str(job["id"]))
        a, b = st.columns(2)
        min_years = a.number_input("Minimum years of experience", 0, 40, int(job.get("min_years") or 0), key="edit_years_" + str(job["id"]))
        min_edu = b.selectbox("Minimum education", [0, 1, 2, 3], index=int(job.get("min_edu") or 0),
                              format_func=lambda x: {0: "No requirement", 1: "Bachelor's", 2: "Master's", 3: "Doctorate"}[x],
                              key="edit_edu_" + str(job["id"]))
        if st.button("Save role requirements", key="save_job_" + str(job["id"])):
            store.conn.execute("UPDATE jobs SET description=?, min_years=?, min_edu=? WHERE id=?",
                               (desc, int(min_years), int(min_edu), job["id"]))
            store.conn.commit()
            store.log("HR Recruiter", "role_criteria_updated", job["title"])
            rank_job(store, job["id"], weights, "HR Recruiter")
            st.success("Requirements saved and rankings refreshed.")
            st.rerun()
        st.caption("Competency definitions and weights come from the shared taxonomy so every role is assessed consistently.")


def _review_tab(st, store, weights):
    job = job_picker(st, store, "review_role")
    cands = store.candidates(job["id"])
    if cands.empty:
        st.info("No resumes uploaded for this category yet. Open **Upload & pool** to add PDF, DOCX or TXT files, or use **Analyze a resume** for a one-off check.")
        return

    a, b, c = st.columns(3)
    blind = a.checkbox("Blind review (hide names)", value=True)
    minimum = b.slider("Minimum match score", 0, 100, 0)
    statuses = c.multiselect("Application status", STATUSES, default=STATUSES)
    if st.button("Refresh rankings", type="primary"):
        rank_job(store, job["id"], weights, "HR Recruiter")
        st.rerun()

    shown = cands[(cands["score"].fillna(0) >= minimum) & cands["status"].isin(statuses)].sort_values("rank")
    out = pd.DataFrame({
        "Rank": shown["rank"],
        "Applicant": [f"Applicant #{r['id']}" if blind else r["name"] for _, r in shown.iterrows()],
        "Match score": shown["score"].round(1),
        "Decision support": shown["verdict"].apply(
            lambda v: (v or {}).get("label", "") if isinstance(v, dict) else ""),
        "Confidence": shown["confidence"],
        "Status": shown["status"],
        "HR decision": shown["hr_decision"],
        "Head decision": shown["head_decision"],
        "Core matched": shown["matched"].apply(lambda x: ", ".join(x) or "—"),
        "Core missing": shown["missing"].apply(lambda x: ", ".join(x) or "—"),
    })
    st.dataframe(out, use_container_width=True, hide_index=True)
    st.caption("Pool scores use identity-masked resume text (names and contact details removed before similarity is "
               "computed), so a score here can differ by a point or two from the single-resume Analyser, which reads "
               "the raw text. The difference is the masking effect, and it is shown deliberately rather than hidden.")
    st.download_button("Export this view (CSV)", out.to_csv(index=False).encode("utf-8"),
                       "fairhire_uploaded_applications.csv", "text/csv")

    if shown.empty:
        return

    choices = shown["id"].tolist()
    chosen = st.selectbox("Inspect a candidate's full rationale", choices,
                          format_func=lambda i: f"Applicant #{i}" if blind else str(shown.loc[shown["id"] == i, "name"].iloc[0]))
    row = shown[shown["id"] == chosen].iloc[0]
    verdict = row["verdict"] if isinstance(row["verdict"], dict) else {}
    feedback = row["feedback"] if isinstance(row["feedback"], dict) else {}
    criteria = row["criteria"] if isinstance(row["criteria"], list) else []

    st.markdown("---")
    _verdict_panel(st, verdict, float(row["score"]))
    _reasons_panel(st, verdict)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Score decomposition")
        _waterfall(st, row, f"wf_{chosen}")
    with right:
        st.markdown("#### At a glance")
        st.metric("Core coverage", f"{float(row['core_coverage'] or 0)*100:.0f}%")
        st.metric("Preferred coverage", f"{float(row['preferred_coverage'] or 0)*100:.0f}%")
        st.metric("ATS readiness", f"{int(row['ats_score'] or 0)}/100")
        st.caption(f"Matching engine: {row.get('matching_engine', 'TF-IDF')}")

    st.markdown("#### Competency evidence")
    if criteria:
        _evidence_table(st, criteria)
    else:
        st.caption("Re-run the ranking to generate evidence for this candidate.")

    if feedback:
        with st.expander("Resume feedback and improvements", expanded=False):
            _feedback_panel(st, feedback)
        with st.expander("ATS checks", expanded=False):
            _ats_panel(st, feedback)

    st.markdown("#### Human decision")
    note = st.text_area("Human reviewer notes", value=row["notes"] or "", key=f"note_{chosen}")
    x, y = st.columns(2)
    if x.button("Save reviewer notes", key=f"note_save_{chosen}"):
        store.set_note(int(chosen), note, "HR Recruiter")
        st.success("Notes saved.")
    if y.button("Recommend for shortlist", key=f"shortlist_{chosen}"):
        store.set_status(int(chosen), "Shortlisted", "HR Recruiter")
        st.success("Recommendation recorded. Company Head approval is still required.")
        st.rerun()
    st.caption("This is a review aid, not an automatic hiring decision. HR and the Company Head remain responsible.")


def _pipeline_tab(st, store):
    st.subheader("Application pipeline")
    cands = store.candidates()
    if cands.empty:
        st.info("The pipeline will appear here after resumes are uploaded.")
    else:
        names = dict(zip(cands["id"], [f"#{r['id']} · {r['name']} · {r['status']}" for _, r in cands.iterrows()]))
        cid = st.selectbox("Application", cands["id"].tolist(), format_func=lambda i: names[i])
        new_status = st.selectbox("Update status", STATUSES)
        if st.button("Save status", type="primary"):
            try:
                eid = store.set_status(int(cid), new_status, "HR Recruiter")
                st.success("Status updated." + (" An email draft is ready for review." if eid else ""))
                st.rerun()
            except PermissionError as exc:
                st.error(str(exc))

    st.subheader("Candidate communication")
    mails = store.emails()
    if mails.empty:
        st.caption("No communication drafts have been created.")
        return
    for _, m in mails.iterrows():
        with st.expander(f"{m['kind'].title()} draft · {m['candidate']} · {m['status']}"):
            if not m["address"]:
                st.warning("No email address was found in this uploaded resume. Do not send until HR verifies the candidate's contact details.")
            subj = st.text_input("Subject", m["subject"], key=f"subj_{m['id']}")
            body = st.text_area("Message", m["body"], key=f"body_{m['id']}", height=180)
            a, b = st.columns(2)
            if a.button("Save draft", key=f"save_mail_{m['id']}"):
                store.update_draft(int(m["id"]), subj, body)
                st.success("Draft saved.")
                st.rerun()
            if b.button("Confirm draft", key=f"confirm_mail_{m['id']}"):
                store.update_draft(int(m["id"]), subj, body)
                try:
                    store.confirm_email(int(m["id"]))
                    st.success("Draft confirmed.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    st.dataframe(mails[["id", "candidate", "kind", "status", "created_at"]], use_container_width=True, hide_index=True)
    st.download_button("Export communication log",
                       mails[["id", "candidate", "kind", "status", "created_at"]].to_csv(index=False).encode("utf-8"),
                       "fairhire_communication_log.csv", "text/csv")


# ---------------------------------------------------------------------------
# Company Head workspace
# ---------------------------------------------------------------------------
def head_view(st, store):
    st.markdown('<div class="fh-hero"><div class="fh-brand" style="color:#f0c3a8">COMPANY HEAD WORKSPACE</div><h2>Oversight before outcomes.</h2><p>Review HR recommendations, see the reasoning behind each one, record approval decisions and keep the process accountable.</p></div>', unsafe_allow_html=True)
    cands = store.candidates()
    a, b, c = st.columns(3)
    a.metric("Uploaded applications", len(cands))
    b.metric("Awaiting approval", int(((cands["hr_decision"] == "accepted") & (cands["head_decision"] != "approved")).sum()) if len(cands) else 0)
    c.metric("Role categories", len(store.get_jobs()))
    tab_over, tab_approval, tab_fair, tab_log = st.tabs(["Overview", "Approval queue", "Fairness & safeguards", "Decision history"])

    with tab_over:
        st.subheader("Recruitment by category")
        rows = []
        for job in store.get_jobs():
            group = store.candidates(job["id"])
            rows.append({"Category": job["title"], "Uploaded resumes": len(group),
                         "HR accepted": int((group["hr_decision"] == "accepted").sum()) if len(group) else 0,
                         "HR rejected": int((group["hr_decision"] == "rejected").sum()) if len(group) else 0,
                         "HR pending": int((group["hr_decision"] == "pending").sum()) if len(group) else 0,
                         "Interview / offer": int(group["status"].isin(["Interview", "Offer"]).sum()) if len(group) else 0})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if len(cands):
            status_counts = cands["status"].value_counts().rename_axis("Status").reset_index(name="Applications")
            fig = px.bar(status_counts, x="Status", y="Applications", color="Status", text="Applications",
                         title="Live application pipeline",
                         color_discrete_sequence=["#83A78A", "#D18B69", "#C9B57A", "#7899A6", "#A5A0C2", "#718477"])
            fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              margin=dict(l=8, r=8, t=45, b=8), showlegend=False, font=dict(color="#eef3ec", size=13))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.caption("Chart alternative: the same counts are listed below.")
            with st.expander("View pipeline counts as a table"):
                st.dataframe(status_counts, use_container_width=True, hide_index=True)
        else:
            st.info("No applicant data yet. The overview updates only after HR uploads actual resumes.")

    with tab_approval:
        st.subheader("HR-accepted applicants awaiting your approval")
        st.caption("Only applicants explicitly accepted by HR are routed here. Approve or return each recommendation; the decision is recorded in the audit log.")
        pending = cands[(cands["hr_decision"] == "accepted") & (cands["head_decision"] != "approved")] if len(cands) else cands
        if pending.empty:
            st.info("No applications are waiting for a decision.")
        for _, r in pending.iterrows():
            with st.container(border=True):
                x, y, z = st.columns([3, 2, 2])
                verdict = r["verdict"] if isinstance(r["verdict"], dict) else {}
                x.markdown(f"**Application #{r['id']} · {r['name']}**")
                x.caption(f"Role: {store.get_job(int(r['job_id']))['title']} · Match score: {r['score']:.1f}/100 · Confidence: {r.get('confidence', '—')}")
                x.markdown(f"Decision support: {_pill(verdict.get('label', 'Not scored yet'), verdict.get('tone', 'neutral'))}", unsafe_allow_html=True)
                if verdict.get("reasons_for"):
                    x.markdown("**For:** " + "; ".join(_reason_text(i) for i in verdict["reasons_for"][:3]))
                if verdict.get("reasons_against"):
                    x.markdown("**Against:** " + "; ".join(_reason_text(i) for i in verdict["reasons_against"][:3]))
                if y.button("Approve HR recommendation", key=f"approve_{r['id']}"):
                    store.head_decide(int(r["id"]), "approved")
                    st.success("Approval recorded.")
                    st.rerun()
                if z.button("Return to HR", key=f"return_{r['id']}"):
                    store.head_decide(int(r["id"]), "sent back")
                    store.set_hr_decision(int(r["id"]), "pending", "Company Head")
                    st.rerun()

    with tab_fair:
        st.subheader("Fairness safeguards")
        st.markdown("""<div class="fh-note"><b>Important data limitation</b><br>FairHire does not fabricate applicant records or demographic labels. Uploaded resumes alone do not provide a reliable, consented dataset for demographic-parity or disparate-impact calculations. Those metrics are therefore not presented as measured results.</div>""", unsafe_allow_html=True)
        st.write("Current safeguards in this prototype:")
        st.markdown("- Blind review can hide applicant names during HR screening.\n"
                    "- Every score is accompanied by evidence, reasons for and reasons against.\n"
                    "- The weakest outcome is “limited evidence — human review needed”; nothing is auto-rejected.\n"
                    "- HR makes shortlist recommendations; the Company Head records approval.\n"
                    "- Communication is drafted for review and is not sent automatically.\n"
                    "- Role criteria should be validated for each real vacancy before use.")
        st.warning("The match score is a prototype decision-support tool, not a validated hiring prediction. Do not use it as the sole basis for rejection or selection.")
        st.markdown("#### Identity-masking sensitivity test")
        st.caption("Compares the same uploaded resume pool with identity masking enabled and disabled. This measures sensitivity to identity text; it is not proof of demographic fairness.")
        audit_job = job_picker(st, store, "fairness_audit_role", "Role to audit")
        audit_cands = store.candidates(audit_job["id"])
        if audit_cands.empty:
            st.info("Upload actual resumes in this category to run the audit.")
        elif st.button("Run identity sensitivity audit", type="primary", key="run_identity_audit"):
            with st.spinner("Comparing masked and unmasked ranking runs..."):
                audit_result = fairness.identity_sensitivity_audit(audit_job, audit_cands[["id", "name", "text"]])
            st.session_state["fairhire_last_audit"] = audit_result
            st.session_state["fairhire_last_audit_role"] = audit_job["title"]
        if "fairhire_last_audit" in st.session_state and st.session_state.get("fairhire_last_audit_role") == audit_job["title"]:
            audit_result = st.session_state["fairhire_last_audit"]
            q1, q2, q3 = st.columns(3)
            q1.metric("Mean absolute score change", f"{audit_result['score_delta'].abs().mean():.2f}")
            q2.metric("Mean rank movement", f"{audit_result['rank_shift'].mean():.2f}")
            q3.metric("Largest rank movement", int(audit_result["rank_shift"].max()))
            st.dataframe(audit_result, use_container_width=True, hide_index=True)
            st.download_button("Export sensitivity audit", audit_result.to_csv(index=False).encode("utf-8"),
                               "fairhire_identity_sensitivity_audit.csv", "text/csv")

    with tab_log:
        history = store.audit_log()
        if history.empty:
            st.info("Decision history will appear after actions are recorded.")
        else:
            st.dataframe(history, use_container_width=True, hide_index=True)
            st.download_button("Download decision history", history.to_csv(index=False).encode("utf-8"),
                               "fairhire_decision_history.csv", "text/csv")


def _inside_streamlit():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


if __name__ == "__main__":
    if _inside_streamlit():
        run_app()
    else:
        print("Run the dashboard with: streamlit run main.py")
