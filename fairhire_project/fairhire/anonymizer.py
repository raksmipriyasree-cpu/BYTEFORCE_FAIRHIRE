"""Identity masking - the 'blind review' step.

Removes the signals the problem statement lists: names, gender pronouns,
graduation years, institutions and geographic locations (plus contact details).
Structured features (skills, experience, education) are extracted from the
ORIGINAL text by skills.py, because those rules never look at identity words.
This module protects the *text-similarity* feature and the blind-review view.
"""
import re

CITIES = ["Chennai", "Bengaluru", "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Pune",
          "Kolkata", "London", "Dubai", "Toronto", "New York", "Singapore"]

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s-]?)?\d{10}(?!\w)")
_URL = re.compile(r"(?:https?://|www\.|linkedin\.com|github\.com)\S+", re.I)
_YEAR = re.compile(r"\b(?:19[6-9]\d|20[0-3]\d)\b")
_TITLE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx)\.?\s+", re.I)
_GENDER_LINE = re.compile(r"^\s*(?:gender|sex)\s*:.*$", re.I | re.M)
_GENDER_WORDS = re.compile(r"\b(?:male|female|man|woman|men|women|gentleman|lady)\b", re.I)
_PRONOUNS = re.compile(r"\b(?:he|she|him|her|hers|his|himself|herself)\b", re.I)
_LOCATION_LINE = re.compile(r"^\s*(?:address|location|city)\s*:.*$", re.I | re.M)
_CITY = re.compile(r"\b(?:" + "|".join(CITIES) + r")\b")

_INSTITUTION = re.compile(
    r"\b(?:(?:[A-Z][\w&'-]*\s){0,3}(?:University|College|Institute|School)(?:\s+of\s+(?:[A-Z][\w&'-]*\s?){1,3})?"
    r"|(?:IIT|NIT|IIIT|BITS)\s+[A-Z][a-z]+)")

def anonymize(text, name=None):
    """Return `text` with identity indicators replaced by neutral tags."""
    out = text

    out = _EMAIL.sub("[EMAIL]", out)
    out = _URL.sub("[URL]", out)
    out = _PHONE.sub("[PHONE]", out)

    if name:
        for token in re.split(r"\s+", name.strip()):
            if len(token) > 1:
                out = re.sub(r"\b" + re.escape(token) + r"\b", "[CANDIDATE]", out, flags=re.I)
    lines = out.splitlines()
    if lines and re.fullmatch(r"[A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3}", lines[0].strip() or "x"):
        lines[0] = "[CANDIDATE]"
        out = "\n".join(lines)

    out = _GENDER_LINE.sub("Gender: [REMOVED]", out)
    out = _LOCATION_LINE.sub("Location: [REMOVED]", out)

    out = _INSTITUTION.sub("[INSTITUTION]", out)
    out = _CITY.sub("[LOCATION]", out)

    out = _YEAR.sub("[YEAR]", out)
    out = _TITLE.sub("", out)
    out = _GENDER_WORDS.sub("[GENDER]", out)
    out = _PRONOUNS.sub("they", out)
    return out
