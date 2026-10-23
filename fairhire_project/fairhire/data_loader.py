"""Load role definitions and extract text from files explicitly uploaded by HR."""
import io
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def load_jobs(path=None):
    with open(path or os.path.join(DATA_DIR, "jobs.json"), encoding="utf-8") as f:
        return json.load(f)


def read_resume_file(filename, data):
    """Extract text from an uploaded PDF, DOCX or TXT file's bytes."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    if ext == ".docx":
        import docx
        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    if ext == ".txt":
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Supported resume formats are PDF, DOCX and TXT")
