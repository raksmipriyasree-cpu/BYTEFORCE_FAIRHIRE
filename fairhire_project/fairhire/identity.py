"""Gender-coded name pairs used to build synthetic 'twin' applicants.

FEMALE_FIRST[i] and MALE_FIRST[i] are counterparts: swapping one for the other
(keeping the surname) changes the gender signal and nothing else.
"""
import re
import zlib

FEMALE_FIRST = ["Priya", "Ananya", "Meera", "Kavya", "Sneha", "Aisha", "Emily", "Sophia",
                "Fatima", "Lakshmi", "Olivia", "Zara", "Nisha", "Divya", "Maria"]
MALE_FIRST = ["Rahul", "Arjun", "Vikram", "Karthik", "Rohan", "Imran", "James", "Daniel",
              "Ahmed", "Suresh", "Liam", "Omar", "Nikhil", "Aditya", "Carlos"]
SURNAMES = ["Sharma", "Iyer", "Reddy", "Khan", "Nair", "Patel", "Singh", "Das", "Menon", "Gupta",
            "Smith", "Johnson", "Rao", "Joshi", "Verma", "Kumar", "Mehta", "Bose", "Pillai", "Chopra"]

_PRONOUN_SWAP = {"she": "he", "he": "she", "her": "his", "his": "her", "hers": "his",
                 "him": "her", "himself": "herself", "herself": "himself"}
_PRON_RE = re.compile(r"\b(" + "|".join(_PRONOUN_SWAP) + r")\b", re.I)

def swap_pronouns(text):
    """Flip gendered pronouns while keeping capitalisation ('She' -> 'He')."""
    def repl(m):
        word = m.group(1)
        new = _PRONOUN_SWAP[word.lower()]
        return new.capitalize() if word[0].isupper() else new
    return _PRON_RE.sub(repl, text)

def infer_gender(text, name=""):
    """Best-effort gender label ('female'/'male'/'unknown') from first name or pronouns."""
    first = name.split()[0] if name.split() else ""
    if first in FEMALE_FIRST:
        return "female"
    if first in MALE_FIRST:
        return "male"
    fem = len(re.findall(r"\b(?:she|her|hers|herself)\b", text, re.I))
    mal = len(re.findall(r"\b(?:he|him|his|himself)\b", text, re.I))
    return "female" if fem > mal else "male" if mal > fem else "unknown"

def counterpart_name(name, gender):
    """Opposite-gender counterpart of `name` (same surname, aligned first-name list)."""
    parts = name.split()
    first, rest = (parts[0], parts[1:]) if parts else ("", [])
    if first in FEMALE_FIRST:
        new_first = MALE_FIRST[FEMALE_FIRST.index(first)]
    elif first in MALE_FIRST:
        new_first = FEMALE_FIRST[MALE_FIRST.index(first)]
    else:
        pool = MALE_FIRST if gender == "female" else FEMALE_FIRST
        new_first = pool[zlib.crc32(name.encode()) % len(pool)]
    return " ".join([new_first] + rest)
