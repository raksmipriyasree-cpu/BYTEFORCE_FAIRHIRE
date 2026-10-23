
"""SQLite persistence and recruitment workflow rules.

Tables: jobs, candidates, emails, audit_log.
Every change is written to audit_log for accountability.
"""
import json
import math
import sqlite3
from datetime import datetime

import pandas as pd

from . import emailer

STATUSES = ["Applied", "Screened", "Shortlisted", "Interview", "Offer", "Closed"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
    id INTEGER PRIMARY KEY,
    title TEXT,
    category TEXT,
    description TEXT,
    required TEXT,
    nice TEXT,
    min_years INTEGER,
    min_edu INTEGER
);

CREATE TABLE IF NOT EXISTS candidates(
    id INTEGER PRIMARY KEY,
    job_id INTEGER,
    name TEXT,
    email TEXT,
    text TEXT,
    gender TEXT,
    category TEXT,
    status TEXT DEFAULT 'Applied',
    score REAL,
    rank INTEGER,
    matched TEXT,
    missing TEXT,
    contribs TEXT,
    base_value REAL,
    notes TEXT DEFAULT '',
    head_decision TEXT DEFAULT 'pending',
    hr_decision TEXT DEFAULT 'pending',
    criteria TEXT,
    verdict TEXT,
    feedback TEXT,
    parsed TEXT,
    confidence TEXT,
    core_coverage REAL,
    preferred_coverage REAL,
    ats_score REAL
);

CREATE TABLE IF NOT EXISTS emails(
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER,
    kind TEXT,
    subject TEXT,
    body TEXT,
    status TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log(
    id INTEGER PRIMARY KEY,
    ts TEXT,
    actor TEXT,
    action TEXT,
    detail TEXT
);
"""

_JSON_COLUMNS = (
    "matched",
    "missing",
    "contribs",
    "criteria",
    "verdict",
    "feedback",
    "parsed",
)

_EXTRA_COLUMNS = {
    "criteria": "TEXT",
    "verdict": "TEXT",
    "feedback": "TEXT",
    "parsed": "TEXT",
    "confidence": "TEXT",
    "core_coverage": "REAL",
    "preferred_coverage": "REAL",
    "ats_score": "REAL",
    "hr_decision": "TEXT DEFAULT 'pending'",
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Store:
    """Thin wrapper around the SQLite database."""

    def __init__(self, path=":memory:", company="Our Company"):
        self.conn = sqlite3.connect(
            path,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.company = company

    def _migrate(self):
        """Add newer columns to databases created by earlier versions."""
        existing = {
            row["name"]
            for row in self.conn.execute(
                "PRAGMA table_info(candidates)"
            )
        }

        for column, column_type in _EXTRA_COLUMNS.items():
            if column not in existing:
                self.conn.execute(
                    f"ALTER TABLE candidates ADD COLUMN "
                    f"{column} {column_type}"
                )

        self.conn.commit()

    def _df(self, sql, params=()):
        return pd.read_sql_query(
            sql,
            self.conn,
            params=params,
        )

    def log(self, actor, action, detail=""):
        self.conn.execute(
            """
            INSERT INTO audit_log(ts, actor, action, detail)
            VALUES (?, ?, ?, ?)
            """,
            (_now(), actor, action, detail),
        )
        self.conn.commit()

    def add_job(self, job, actor="system"):
        cursor = self.conn.execute(
            """
            INSERT INTO jobs(
                title, category, description, required, nice,
                min_years, min_edu
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["title"],
                job.get("category", ""),
                job["description"],
                json.dumps(job["required"]),
                json.dumps(job.get("nice", [])),
                job.get("min_years", 1),
                job.get("min_edu", 1),
            ),
        )
        self.conn.commit()
        self.log(actor, "job_created", job["title"])
        return cursor.lastrowid

    def get_jobs(self):
        jobs = []

        for row in self.conn.execute(
            "SELECT * FROM jobs ORDER BY id"
        ):
            job = dict(row)
            job["required"] = self._decode_json(
                job.get("required"), []
            )
            job["nice"] = self._decode_json(
                job.get("nice"), []
            )
            jobs.append(job)

        return jobs

    def get_job(self, job_id):
        for job in self.get_jobs():
            if job["id"] == job_id:
                return job
        raise KeyError(f"Job {job_id} was not found.")

    def add_candidate(
        self,
        job_id,
        name,
        email,
        text,
        gender="",
        category="",
        actor="system",
    ):
        cursor = self.conn.execute(
            """
            INSERT INTO candidates(
                job_id, name, email, text, gender, category
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, name, email, text, gender, category),
        )
        self.conn.commit()
        self.log(
            actor,
            "candidate_added",
            f"{name} -> job {job_id}",
        )
        return cursor.lastrowid

    @staticmethod
    def _decode_json(value, default):
        """Safely decode JSON stored in SQLite or returned by pandas.

        Handles SQL NULL, pandas NaN/NA, empty strings, malformed legacy
        values, and values that are already Python dictionaries or lists.
        """
        if value is None:
            return default

        # Values can already be decoded.
        if isinstance(value, (dict, list)):
            return value

        # Handle pandas/numpy missing values without passing them to json.loads.
        try:
            missing = pd.isna(value)
            if isinstance(missing, bool) and missing:
                return default
            if getattr(missing, "ndim", 0) == 0 and bool(missing):
                return default
        except (TypeError, ValueError):
            pass

        if not isinstance(value, (str, bytes, bytearray)):
            return default

        if not value:
            return default

        try:
            return json.loads(value)
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            TypeError,
            ValueError,
        ):
            return default

    def candidates(self, job_id=None):
        """Return candidates with JSON columns decoded safely."""
        if job_id is None:
            df = self._df(
                "SELECT * FROM candidates ORDER BY id"
            )
        else:
            df = self._df(
                "SELECT * FROM candidates WHERE job_id = ? ORDER BY id",
                (job_id,),
            )

        defaults = {
            "matched": [],
            "missing": [],
            "contribs": {},
            "criteria": [],
            "verdict": {},
            "feedback": {},
            "parsed": {},
        }

        for column in _JSON_COLUMNS:
            if column not in df.columns:
                continue

            fallback = defaults[column]
            df[column] = df[column].apply(
                lambda value, default=fallback:
                self._decode_json(value, default)
            )

        return df

    def get_candidate(self, candidate_id):
        df = self.candidates()

        if df.empty:
            return None

        result = df[df["id"] == candidate_id]
        if result.empty:
            return None

        return result.iloc[0]

    def save_ranking(self, ranked, actor="system"):
        """Save scores and explanations from ranker.rank_candidates."""
        for _, row in ranked.iterrows():
            self.conn.execute(
                """
                UPDATE candidates
                SET score = ?, rank = ?, matched = ?, missing = ?,
                    contribs = ?, base_value = ?, criteria = ?,
                    verdict = ?, feedback = ?, parsed = ?,
                    confidence = ?, core_coverage = ?,
                    preferred_coverage = ?, ats_score = ?,
                    status = CASE
                        WHEN status = 'Applied' THEN 'Screened'
                        ELSE status
                    END
                WHERE id = ?
                """,
                (
                    float(row["score"]),
                    int(row["rank"]),
                    json.dumps(row.get("matched", [])),
                    json.dumps(row.get("missing", [])),
                    json.dumps({
                        key: float(value)
                        for key, value in row.get(
                            "contribs", {}
                        ).items()
                    }),
                    float(row.get("base_value", 0.0)),
                    json.dumps(row.get("criteria", [])),
                    json.dumps(row.get("verdict", {})),
                    json.dumps(row.get("feedback", {})),
                    json.dumps(row.get("parsed", {})),
                    str(row.get("confidence", "")),
                    float(row.get("core_coverage", 0.0)),
                    float(row.get("preferred_coverage", 0.0)),
                    float(row.get("ats_score", 0.0)),
                    int(row["id"]),
                ),
            )

        self.conn.commit()
        self.log(
            actor,
            "ranking_run",
            f"{len(ranked)} candidates scored with evidence",
        )

    def set_note(self, candidate_id, note, actor):
        self.conn.execute(
            "UPDATE candidates SET notes = ? WHERE id = ?",
            (note, candidate_id),
        )
        self.conn.commit()
        self.log(actor, "note_saved", f"candidate {candidate_id}")

    def set_status(self, candidate_id, new_status, actor="HR Recruiter"):
        """Update pipeline status and create an email draft when applicable.

        Interview and Offer require prior Company Head approval.
        Email drafts are not sent automatically.
        """
        if new_status not in STATUSES:
            raise ValueError(f"Unknown status: {new_status}")

        row = self.conn.execute(
            "SELECT * FROM candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()

        if row is None:
            raise KeyError(f"Candidate {candidate_id} was not found.")

        if (
            new_status in ("Interview", "Offer")
            and row["head_decision"] != "approved"
        ):
            raise PermissionError(
                "The Company Head must approve this candidate "
                "before interview or offer."
            )

        self.conn.execute(
            "UPDATE candidates SET status = ? WHERE id = ?",
            (new_status, candidate_id),
        )
        self.conn.commit()

        self.log(
            actor,
            "status_changed",
            f"{row['name']}: {row['status']} -> {new_status}",
        )

        kind = emailer.STATUS_EMAIL.get(new_status)
        if not kind:
            return None

        job = self.get_job(row["job_id"])
        missing = self._decode_json(row["missing"], [])

        draft = emailer.build_draft(
            kind,
            row["name"],
            job["title"],
            self.company,
            missing_skills=missing,
        )

        cursor = self.conn.execute(
            """
            INSERT INTO emails(
                candidate_id, kind, subject, body, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                kind,
                draft["subject"],
                draft["body"],
                "draft",
                _now(),
            ),
        )
        self.conn.commit()
        self.log(
            "FairHire AI",
            "email_drafted",
            f"{kind} email for {row['name']}",
        )
        return cursor.lastrowid

    def set_hr_decision(
        self,
        candidate_id,
        decision,
        actor="HR Recruiter",
    ):
        """Record HR's accepted, rejected, or pending decision."""
        if decision not in ("accepted", "rejected", "pending"):
            raise ValueError(
                "decision must be accepted, rejected, or pending"
            )

        row = self.conn.execute(
            "SELECT id FROM candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()

        if row is None:
            raise KeyError(f"Candidate {candidate_id} was not found.")

        # Any new HR decision resets the previous Head decision.
        self.conn.execute(
            """
            UPDATE candidates
            SET hr_decision = ?, head_decision = 'pending'
            WHERE id = ?
            """,
            (decision, candidate_id),
        )
        self.conn.commit()

        self.log(
            actor,
            "hr_decision",
            f"candidate {candidate_id}: {decision}",
        )

    def head_decide(
        self,
        candidate_id,
        decision,
        actor="Company Head",
    ):
        """Record the Head's decision: approved, sent back, or pending."""
        if decision not in ("approved", "sent back", "pending"):
            raise ValueError(
                "decision must be approved, sent back, or pending"
            )

        row = self.conn.execute(
            "SELECT id, hr_decision FROM candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()

        if row is None:
            raise KeyError(f"Candidate {candidate_id} was not found.")

        if decision == "approved" and row["hr_decision"] != "accepted":
            raise PermissionError(
                "The Company Head can approve only applicants "
                "accepted by HR."
            )

        self.conn.execute(
            "UPDATE candidates SET head_decision = ? WHERE id = ?",
            (decision, candidate_id),
        )
        self.conn.commit()

        self.log(
            actor,
            "head_decision",
            f"candidate {candidate_id}: {decision}",
        )

    def emails(self):
        return self._df(
            """
            SELECT e.*, c.name AS candidate, c.email AS address
            FROM emails e
            JOIN candidates c ON c.id = e.candidate_id
            ORDER BY e.id DESC
            """
        )

    def update_draft(self, email_id, subject, body):
        self.conn.execute(
            """
            UPDATE emails
            SET subject = ?, body = ?
            WHERE id = ? AND status = 'draft'
            """,
            (subject, body, email_id),
        )
        self.conn.commit()

    def confirm_email(self, email_id, actor="HR Recruiter"):
        row = self.conn.execute(
            "SELECT body FROM emails WHERE id = ?",
            (email_id,),
        ).fetchone()

        if row is None:
            raise KeyError(f"Email {email_id} was not found.")

        unresolved = emailer.unresolved_placeholders(row["body"])
        if unresolved:
            raise ValueError(
                "Fill in these placeholders first: "
                + ", ".join(unresolved)
            )

        self.conn.execute(
            "UPDATE emails SET status = 'confirmed' WHERE id = ?",
            (email_id,),
        )
        self.conn.commit()
        self.log(actor, "email_confirmed", f"email {email_id}")

    def send_email(self, email_id, actor="HR Recruiter"):
        row = self.conn.execute(
            """
            SELECT e.*, c.email AS address
            FROM emails e
            JOIN candidates c ON c.id = e.candidate_id
            WHERE e.id = ?
            """,
            (email_id,),
        ).fetchone()

        if row is None:
            raise KeyError(f"Email {email_id} was not found.")

        result = emailer.send(
            row["address"],
            row["subject"],
            row["body"],
            confirmed=(row["status"] == "confirmed"),
        )

        self.conn.execute(
            "UPDATE emails SET status = 'awaiting_reply' WHERE id = ?",
            (email_id,),
        )
        self.conn.commit()

        self.log(
            actor,
            "email_" + result,
            f"email {email_id} to {row['address']}",
        )
        return result

    def audit_log(self):
        return self._df(
            "SELECT ts, actor, action, detail "
            "FROM audit_log ORDER BY id DESC"
        )

    def funnel(self, job_id=None):
        """Return candidate counts by recruitment stage."""
        df = self.candidates(job_id)

        counts = (
            df["status"].value_counts()
            if len(df)
            else pd.Series(dtype=int)
        )

        return pd.Series({
            status: int(counts.get(status, 0))
            for status in STATUSES
        })
