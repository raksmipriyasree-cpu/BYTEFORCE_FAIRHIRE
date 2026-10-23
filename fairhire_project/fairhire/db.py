"""SQLite persistence and the recruitment workflow rules.

Tables: jobs, candidates, emails, audit_log.  Every change is written to
audit_log so the Company Head can see who did what (human accountability).

The candidates table stores the full analysis payload (criteria, verdict,
feedback, parsed facts) so the "why" survives a page reload and is auditable.
"""
import json
import sqlite3
from datetime import datetime

import pandas as pd

from . import emailer

STATUSES = ["Applied", "Screened", "Shortlisted", "Interview", "Offer", "Closed"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, title TEXT, category TEXT, description TEXT,
    required TEXT, nice TEXT, min_years INTEGER, min_edu INTEGER);
CREATE TABLE IF NOT EXISTS candidates(id INTEGER PRIMARY KEY, job_id INTEGER, name TEXT, email TEXT,
    text TEXT, gender TEXT, category TEXT, status TEXT DEFAULT 'Applied', score REAL, rank INTEGER,
    matched TEXT, missing TEXT, contribs TEXT, base_value REAL, notes TEXT DEFAULT '',
    head_decision TEXT DEFAULT 'pending', hr_decision TEXT DEFAULT 'pending', criteria TEXT, verdict TEXT, feedback TEXT, parsed TEXT,
    confidence TEXT, core_coverage REAL, preferred_coverage REAL, ats_score REAL);
CREATE TABLE IF NOT EXISTS emails(id INTEGER PRIMARY KEY, candidate_id INTEGER, kind TEXT, subject TEXT,
    body TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, action TEXT, detail TEXT);
"""

_JSON_COLUMNS = ("matched", "missing", "contribs", "criteria", "verdict", "feedback", "parsed")
_EXTRA_COLUMNS = {
    "criteria": "TEXT", "verdict": "TEXT", "feedback": "TEXT", "parsed": "TEXT",
    "confidence": "TEXT", "core_coverage": "REAL", "preferred_coverage": "REAL", "ats_score": "REAL",
    "hr_decision": "TEXT DEFAULT 'pending'",
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Store:
    """Thin wrapper around the SQLite database."""

    def __init__(self, path=":memory:", company="Our Company"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.company = company

    def _migrate(self):
        """Add new analysis columns to databases created by an earlier build."""
        existing = {r["name"] for r in self.conn.execute("PRAGMA table_info(candidates)")}
        for col, typ in _EXTRA_COLUMNS.items():
            if col not in existing:
                self.conn.execute(f"ALTER TABLE candidates ADD COLUMN {col} {typ}")
        self.conn.commit()

    def _df(self, sql, params=()):
        return pd.read_sql_query(sql, self.conn, params=params)

    def log(self, actor, action, detail=""):
        self.conn.execute("INSERT INTO audit_log(ts, actor, action, detail) VALUES (?,?,?,?)",
                          (_now(), actor, action, detail))
        self.conn.commit()

    def add_job(self, job, actor="system"):
        cur = self.conn.execute(
            "INSERT INTO jobs(title, category, description, required, nice, min_years, min_edu) VALUES (?,?,?,?,?,?,?)",
            (job["title"], job.get("category", ""), job["description"], json.dumps(job["required"]),
             json.dumps(job.get("nice", [])), job.get("min_years", 1), job.get("min_edu", 1)))
        self.conn.commit()
        self.log(actor, "job_created", job["title"])
        return cur.lastrowid

    def get_jobs(self):
        jobs = []
        for r in self.conn.execute("SELECT * FROM jobs ORDER BY id"):
            d = dict(r)
            d["required"], d["nice"] = json.loads(d["required"]), json.loads(d["nice"])
            jobs.append(d)
        return jobs

    def get_job(self, job_id):
        return next(j for j in self.get_jobs() if j["id"] == job_id)

    def add_candidate(self, job_id, name, email, text, gender="", category="", actor="system"):
        cur = self.conn.execute(
            "INSERT INTO candidates(job_id, name, email, text, gender, category) VALUES (?,?,?,?,?,?)",
            (job_id, name, email, text, gender, category))
        self.conn.commit()
        self.log(actor, "candidate_added", f"{name} -> job {job_id}")
        return cur.lastrowid

    def candidates(self, job_id=None):
        df = self._df("SELECT * FROM candidates" + (" WHERE job_id = ?" if job_id else ""),
                      (job_id,) if job_id else ())
        for col in _JSON_COLUMNS:
            if col not in df.columns:
                continue
            if col == "contribs":
                df[col] = df[col].apply(lambda v: json.loads(v) if v else {})
            elif col in ("criteria", "verdict", "feedback", "parsed"):
                df[col] = df[col].apply(lambda v: json.loads(v) if v else ([] if col == "criteria" else {}))
            else:
                df[col] = df[col].apply(lambda v: json.loads(v) if v else [])
        return df

    def get_candidate(self, cid):
        df = self.candidates()
        if df.empty:
            return None
        row = df[df["id"] == cid]
        return None if row.empty else row.iloc[0]

    def save_ranking(self, ranked, actor="system"):
        """Store scores + full explanations from ranker.rank_candidates."""
        for _, r in ranked.iterrows():
            self.conn.execute(
                "UPDATE candidates SET score=?, rank=?, matched=?, missing=?, contribs=?, base_value=?, "
                "criteria=?, verdict=?, feedback=?, parsed=?, confidence=?, core_coverage=?, "
                "preferred_coverage=?, ats_score=?, "
                "status=CASE WHEN status='Applied' THEN 'Screened' ELSE status END WHERE id=?",
                (float(r["score"]), int(r["rank"]), json.dumps(r["matched"]), json.dumps(r["missing"]),
                 json.dumps({k: float(v) for k, v in r["contribs"].items()}), float(r["base_value"]),
                 json.dumps(r.get("criteria", [])), json.dumps(r.get("verdict", {})),
                 json.dumps(r.get("feedback", {})), json.dumps(r.get("parsed", {})),
                 str(r.get("confidence", "")), float(r.get("core_coverage", 0.0)),
                 float(r.get("preferred_coverage", 0.0)), float(r.get("ats_score", 0.0)),
                 int(r["id"])))
        self.conn.commit()
        self.log(actor, "ranking_run", f"{len(ranked)} candidates scored with evidence")

    def set_note(self, cid, note, actor):
        self.conn.execute("UPDATE candidates SET notes=? WHERE id=?", (note, cid))
        self.conn.commit()
        self.log(actor, "note_saved", f"candidate {cid}")

    def set_status(self, cid, new_status, actor="HR Recruiter"):
        """Move a candidate along the pipeline.

        Rules: an interview needs the Company Head's approval of the shortlist.
        Moving to Shortlisted / Interview / Offer / Closed auto-drafts the matching
        email (status 'draft') for HR to review - it is never sent automatically.
        Returns the new email id or None.
        """
        if new_status not in STATUSES:
            raise ValueError(f"Unknown status {new_status}")
        row = self.conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
        if new_status in ("Interview", "Offer") and row["head_decision"] != "approved":
            raise PermissionError("The Company Head must approve this candidate before interview or offer.")
        self.conn.execute("UPDATE candidates SET status=? WHERE id=?", (new_status, cid))
        self.conn.commit()
        self.log(actor, "status_changed", f"{row['name']}: {row['status']} -> {new_status}")
        kind = emailer.STATUS_EMAIL.get(new_status)
        if not kind:
            return None
        job = self.get_job(row["job_id"])
        missing = json.loads(row["missing"]) if row["missing"] else []
        draft = emailer.build_draft(kind, row["name"], job["title"], self.company, missing_skills=missing)
        cur = self.conn.execute(
            "INSERT INTO emails(candidate_id, kind, subject, body, status, created_at) VALUES (?,?,?,?,?,?)",
            (cid, kind, draft["subject"], draft["body"], "draft", _now()))
        self.conn.commit()
        self.log("FairHire AI", "email_drafted", f"{kind} email for {row['name']}")
        return cur.lastrowid

    def set_hr_decision(self, cid, decision, actor="HR Recruiter"):
        """Record the HR triage decision. Accepted applicants enter the Head queue."""
        if decision not in ("accepted", "rejected", "pending"):
            raise ValueError("decision must be accepted / rejected / pending")
        if decision != "accepted":
            self.conn.execute("UPDATE candidates SET hr_decision=?, head_decision='pending' WHERE id=?", (decision, cid))
        else:
            self.conn.execute("UPDATE candidates SET hr_decision=?, head_decision='pending' WHERE id=?", (decision, cid))
        self.conn.commit()
        self.log(actor, "hr_decision", f"candidate {cid}: {decision}")

    def head_decide(self, cid, decision, actor="Company Head"):
        """decision: 'approved' or 'sent back'."""
        if decision not in ("approved", "sent back", "pending"):
            raise ValueError("decision must be approved / sent back / pending")
        self.conn.execute("UPDATE candidates SET head_decision=? WHERE id=?", (decision, cid))
        self.conn.commit()
        self.log(actor, "head_decision", f"candidate {cid}: {decision}")

    def emails(self):
        return self._df("SELECT e.*, c.name AS candidate, c.email AS address FROM emails e "
                        "JOIN candidates c ON c.id = e.candidate_id ORDER BY e.id DESC")

    def update_draft(self, eid, subject, body):
        self.conn.execute("UPDATE emails SET subject=?, body=? WHERE id=? AND status='draft'", (subject, body, eid))
        self.conn.commit()

    def confirm_email(self, eid, actor="HR Recruiter"):
        body = self.conn.execute("SELECT body FROM emails WHERE id=?", (eid,)).fetchone()["body"]
        left = emailer.unresolved_placeholders(body)
        if left:
            raise ValueError("Fill in these placeholders first: " + ", ".join(left))
        self.conn.execute("UPDATE emails SET status='confirmed' WHERE id=?", (eid,))
        self.conn.commit()
        self.log(actor, "email_confirmed", f"email {eid}")

    def send_email(self, eid, actor="HR Recruiter"):
        e = self.conn.execute("SELECT e.*, c.email AS address FROM emails e JOIN candidates c "
                              "ON c.id=e.candidate_id WHERE e.id=?", (eid,)).fetchone()
        result = emailer.send(e["address"], e["subject"], e["body"], confirmed=(e["status"] == "confirmed"))
        self.conn.execute("UPDATE emails SET status='awaiting_reply' WHERE id=?", (eid,))
        self.conn.commit()
        self.log(actor, "email_" + result, f"email {eid} to {e['address']}")
        return result

    def audit_log(self):
        return self._df("SELECT ts, actor, action, detail FROM audit_log ORDER BY id DESC")

    def funnel(self, job_id=None):
        """Candidates per pipeline stage (current status)."""
        df = self.candidates(job_id)
        counts = df["status"].value_counts() if len(df) else pd.Series(dtype=int)
        return pd.Series({s: int(counts.get(s, 0)) for s in STATUSES})
