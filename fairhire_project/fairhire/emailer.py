"""Applicant communication: templates, drafts and (human-confirmed) sending.

Safety rules baked in:
  * the AI only DRAFTS - nothing is sent until HR has reviewed and confirmed;
  * a draft that still contains an unfilled [PLACEHOLDER] cannot be confirmed;
  * with no SMTP settings the app runs in dry-run mode and only simulates sending.
"""
import os
import re
import smtplib
from email.message import EmailMessage

STATUS_EMAIL = {"Shortlisted": "shortlist", "Interview": "interview", "Offer": "offer", "Closed": "closure"}

TEMPLATES = {
    "shortlist": ("You have been shortlisted for {job}",
                  "Dear {name},\n\nThank you for applying for the {job} role at {company}. "
                  "We are pleased to let you know that your application has been shortlisted based on your skills "
                  "and experience. Our team will contact you shortly about the next steps.\n\nBest regards,\n{sender}"),
    "interview": ("Interview invitation: {job}",
                  "Dear {name},\n\nWe would like to invite you to an interview for the {job} role at {company}.\n\n"
                  "Date: [DATE]\nTime: [TIME]\nMeeting link / venue: [MEETING DETAILS]\n\n"
                  "Please reply to confirm your availability.\n\nBest regards,\n{sender}"),
    "offer": ("Job offer: {job} at {company}",
              "Dear {name},\n\nCongratulations! We are delighted to offer you the {job} position at {company}. "
              "Details of the offer: [OFFER DETAILS]\n\nPlease reply by [REPLY DEADLINE] to accept.\n\nBest regards,\n{sender}"),
    "closure": ("Update on your application for {job}",
                "Dear {name},\n\nThank you for your interest in the {job} role at {company}. After careful review "
                "we will not be moving forward with your application at this time.\n\n{feedback}\n\n"
                "We appreciate your effort and encourage you to apply again.\n\nBest regards,\n{sender}"),
}

_PLACEHOLDER = re.compile(r"\[[A-Z][A-Z /]+\]")

def build_draft(kind, name, job, company="Our Company", sender="The Hiring Team", missing_skills=None):
    """Create {subject, body} for template `kind`; closure emails include skill feedback."""
    if kind not in TEMPLATES:
        raise ValueError(f"Unknown email type: {kind}")
    feedback = ""
    if kind == "closure":
        if missing_skills:
            feedback = ("Feedback you may find useful: the role asked for skills such as "
                        + ", ".join(missing_skills[:4]) + ", which we could not see in your application.")
        else:
            feedback = "Your profile was strong; competition for this role was very high."
    subject, body = TEMPLATES[kind]
    fields = dict(name=name, job=job, company=company, sender=sender, feedback=feedback)
    return {"kind": kind, "subject": subject.format(**fields), "body": body.format(**fields)}

def unresolved_placeholders(body):
    """List [PLACEHOLDER] tokens HR still has to fill in."""
    return _PLACEHOLDER.findall(body)

def send(to_address, subject, body, confirmed):
    """Send an email.  Returns 'sent' (real SMTP) or 'simulated' (dry-run).

    Raises PermissionError unless HR confirmed the draft.
    """
    if not confirmed:
        raise PermissionError("Email not confirmed by HR - refusing to send.")
    host = os.environ.get("FAIRHIRE_SMTP_HOST")
    if not host:
        return "simulated"
    msg = EmailMessage()
    msg["From"] = os.environ.get("FAIRHIRE_SMTP_FROM", os.environ.get("FAIRHIRE_SMTP_USER", ""))
    msg["To"], msg["Subject"] = to_address, subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("FAIRHIRE_SMTP_PORT", "587"))) as server:
        server.starttls()
        server.login(os.environ["FAIRHIRE_SMTP_USER"], os.environ["FAIRHIRE_SMTP_PASSWORD"])
        server.send_message(msg)
    return "sent"
