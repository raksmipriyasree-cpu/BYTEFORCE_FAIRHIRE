"""Unit tests for FairHire core logic; all applicant text here is test-only fixture data."""
import os
import sys
import unittest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fairhire import emailer, fairness
from fairhire.anonymizer import anonymize
from fairhire.db import Store
from fairhire.demo import rank_job
from fairhire.ranker import FEATURES, rank_candidates
from fairhire.skills import extract_education_level, extract_skills, extract_years_experience

RESUME = ("Priya Sharma\nEmail: priya.sharma@example.com | Phone: 9876543210\nLocation: Chennai\nGender: Female\n"
          "Summary: Priya is a developer. She has 5 years of experience in python, sql and C++. Her work is solid.\n"
          "Education: M.Tech in Computer Science, Anna University, graduated 2018.")
JOB = {"title":"Data Scientist", "category":"Data Science", "description":"Build machine learning models and analyse data with Python, SQL, pandas, scikit-learn and statistics.", "required":["python","sql","machine learning","pandas","scikit-learn","statistics"], "nice":["nlp","tensorflow","data visualization","deep learning"], "min_years":2,"min_edu":1}

class SkillTests(unittest.TestCase):
    def test_skills_and_symbols(self):
        found = extract_skills("Built apps in JavaScript and C++ with CI/CD on AWS")
        self.assertIn("javascript", found); self.assertIn("c++", found); self.assertIn("ci/cd", found); self.assertNotIn("java", found)
    def test_experience_and_education(self):
        self.assertEqual(extract_years_experience(RESUME), 5); self.assertEqual(extract_education_level(RESUME), 2); self.assertEqual(extract_education_level("PhD in physics"), 3)

class AnonymizerTests(unittest.TestCase):
    def test_identity_removed(self):
        out = anonymize(RESUME, "Priya Sharma")
        for leak in ["Priya", "Sharma", "@example.com", "9876543210", "Chennai", "Anna University", "2018", "Female", " She ", " Her "]:
            self.assertNotIn(leak, out, f"'{leak}' leaked through anonymisation")
        self.assertIn("python", out)

class RankerTests(unittest.TestCase):
    def setUp(self):
        texts = [RESUME,
                 "Alex Doe\nHe has 6 years of experience in python, sql, machine learning, pandas, scikit-learn, statistics. M.Sc.",
                 "Sam Roe\nShe has 0 years of experience in html and css."]
        self.df = pd.DataFrame([{"id":i+1,"name":t.splitlines()[0],"text":t} for i,t in enumerate(texts)])
    def test_explanations_add_up_to_score(self):
        ranked=rank_candidates(JOB,self.df)
        for _,r in ranked.iterrows(): self.assertAlmostEqual(r["base_value"]+sum(r["contribs"].values()),r["score"],delta=0.05)
        self.assertEqual(set(ranked.iloc[0]["contribs"]),set(FEATURES))
    def test_strong_candidate_beats_weak_one(self):
        ranked=rank_candidates(JOB,self.df)
        self.assertLess(ranked[ranked["id"]==2]["rank"].iloc[0],ranked[ranked["id"]==3]["rank"].iloc[0])

class FairnessTests(unittest.TestCase):
    def test_anonymisation_removes_twin_gap(self):
        df=pd.DataFrame([{"id":1,"name":"Alex Doe","text":"Alex Doe has python and SQL skills","gender":"male"},{"id":2,"name":"Priya Doe","text":"Priya Doe has python and SQL skills","gender":"female"}])
        result=fairness.before_after(JOB,df)
        self.assertEqual(result["after"]["mean_twin_rank_shift"],0.0)

    def test_identity_sensitivity_audit_returns_uploaded_pool_only(self):
        df=pd.DataFrame([{"id":11,"name":"Alex Doe","text":"Alex Doe has Python SQL and data analysis skills."},
                         {"id":12,"name":"Priya Doe","text":"Priya Doe has Python SQL machine learning and statistics skills."}])
        result=fairness.identity_sensitivity_audit(JOB,df)
        self.assertEqual(set(result["id"]),{11,12})
        self.assertIn("score_delta",result.columns)
        self.assertIn("rank_shift",result.columns)

class EmailTests(unittest.TestCase):
    def test_closure_has_feedback(self):
        d=emailer.build_draft("closure","Sam","Data Scientist",missing_skills=["sql","statistics"]); self.assertIn("sql",d["body"])
    def test_cannot_send_unconfirmed(self):
        with self.assertRaises(PermissionError): emailer.send("a@b.com","s","b",confirmed=False)

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(":memory:"); self.job_id=self.store.add_job(JOB)
        cid=self.store.add_candidate(self.job_id,"Priya Sharma","priya@example.com",RESUME,"","Data Science")
        rank_job(self.store,self.job_id); self.cid=cid
    def test_shortlist_drafts_email_but_does_not_send(self):
        eid=self.store.set_status(self.cid,"Shortlisted"); self.assertIsNotNone(eid); self.assertEqual(self.store.emails().iloc[0]["status"],"draft")
    def test_hr_acceptance_routes_to_head_and_rejection_is_recorded(self):
        self.store.set_status(self.cid, "Shortlisted")
        self.store.set_hr_decision(self.cid, "accepted")
        row = self.store.get_candidate(self.cid)
        self.assertEqual(row["hr_decision"], "accepted")
        self.assertEqual(row["head_decision"], "pending")
        self.store.head_decide(self.cid, "approved")
        self.assertEqual(self.store.get_candidate(self.cid)["head_decision"], "approved")
        self.store.set_hr_decision(self.cid, "rejected")
        self.assertEqual(self.store.get_candidate(self.cid)["hr_decision"], "rejected")
    def test_interview_needs_head_approval_and_filled_placeholders(self):
        self.store.set_status(self.cid,"Shortlisted")
        with self.assertRaises(PermissionError): self.store.set_status(self.cid,"Interview")
        self.store.head_decide(self.cid,"approved"); eid=self.store.set_status(self.cid,"Interview")
        with self.assertRaises(ValueError): self.store.confirm_email(eid)
        with self.assertRaises(PermissionError): self.store.send_email(eid)
        self.store.update_draft(eid,"Interview","Date: 5 Nov\nTime: 10am\nVenue: Zoom"); self.store.confirm_email(eid)
        self.assertEqual(self.store.send_email(eid),"simulated")

if __name__ == "__main__": unittest.main()
