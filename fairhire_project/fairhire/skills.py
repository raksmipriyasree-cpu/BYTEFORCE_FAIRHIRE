"""Rule-based extraction of skills, years of experience and education level.

Why rules and not a black-box model?  These features are the *verified
technical competencies* the problem statement asks us to score on.  Rules are
deterministic, auditable and cannot pick up names, gender or other identity
signals.  If spaCy is installed we use its PhraseMatcher (faster on big pools);
otherwise a regex fallback with identical behaviour is used.
"""
import re

SKILL_ALIASES = {
    # programming
    "python": ["python"], "java": ["java"], "javascript": ["javascript", "js", "ecmascript"],
    "typescript": ["typescript"], "c++": ["c++"], "c#": ["c#", "c sharp"], "r": ["r programming", "r language"],
    "sql": ["sql", "mysql", "postgresql", "sqlite", "microsoft sql", "oracle sql"],
    "bash": ["bash", "shell scripting"], "powershell": ["powershell"], "matlab": ["matlab"],
    "vba": ["vba", "visual basic"],
    # data / ml
    "machine learning": ["machine learning", "ml"], "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"], "pandas": ["pandas"], "numpy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn"], "tensorflow": ["tensorflow"], "pytorch": ["pytorch"],
    "statistics": ["statistics", "statistical analysis", "statistical modelling", "statistical modeling"],
    "data analysis": ["data analysis", "data analytics", "analytical skills"],
    "data mining": ["data mining"], "predictive modelling": ["predictive modelling", "predictive modeling"],
    "data visualization": ["data visualization", "data visualisation", "tableau", "power bi", "ggplot"],
    "excel": ["excel", "advanced excel", "spreadsheet"], "sas": ["sas"], "spss": ["spss"],
    "jmp": ["jmp"], "gis": ["gis", "arcgis"], "beautiful soup": ["beautiful soup", "beautifulsoup"],
    "web scraping": ["web scraping", "web scraping"], "big data": ["big data", "hadoop", "spark"],
    # web / software
    "html": ["html", "html5"], "css": ["css", "css3"], "react": ["react", "reactjs", "react.js"],
    "node.js": ["node.js", "nodejs"], "django": ["django"], "flask": ["flask"], "asp.net": ["asp.net", "asp net"],
    "rest api": ["rest api", "rest apis", "restful"], "mongodb": ["mongodb"],
    "git": ["git", "github", "gitlab"], "docker": ["docker"], "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"], "azure": ["azure"], "google cloud": ["google cloud", "gcp"],
    "linux": ["linux", "ubuntu"], "ci/cd": ["ci/cd", "continuous integration", "jenkins"],
    "terraform": ["terraform"], "monitoring": ["monitoring", "prometheus", "grafana"],
    "agile": ["agile", "scrum"], "api": ["api", "apis"],
    # it / security
    "networking": ["networking", "network administration", "tcp/ip", "dns", "dhcp", "vpn", "router", "switch"],
    "active directory": ["active directory"], "windows server": ["windows server"],
    "technical support": ["technical support", "help desk", "helpdesk", "service desk", "desktop support"],
    "troubleshooting": ["troubleshooting", "troubleshoot", "diagnose", "root cause"],
    "cybersecurity": ["cybersecurity", "cyber security", "network security", "information security"],
    "penetration testing": ["penetration testing", "pentesting"], "cryptography": ["cryptography"],
    "siem": ["siem", "splunk"], "firewalls": ["firewall", "firewalls"],
    "incident response": ["incident response"], "vulnerability assessment": ["vulnerability assessment"],
    "wireshark": ["wireshark"], "backup": ["backup", "disaster recovery"],
    # engineering / quality
    "engineering design": ["engineering design", "mechanical design", "electrical design", "product design"],
    "cad": ["cad", "solidworks", "autocad", "catia"], "manufacturing": ["manufacturing", "production process"],
    "quality assurance": ["quality assurance", "quality control", "quality technician", "qa"],
    "testing": ["testing", "test plan", "test case", "validation", "verification", "inspection"],
    "six sigma": ["six sigma", "lean manufacturing"], "iso 9001": ["iso 9001", "iso"],
    "project management": ["project management", "project schedule", "managed projects"],
    "documentation": ["documentation", "technical report", "standard operating procedure", "sop"],
    "safety": ["safety", "osha", "risk assessment"],
    # design
    "figma": ["figma"], "adobe": ["adobe", "photoshop", "illustrator", "indesign"],
    "ui/ux": ["ui/ux", "ui", "ux", "user experience", "user interface"],
    "prototyping": ["prototyping", "prototype", "wireframe", "mockup"],
    "user research": ["user research", "usability", "user testing", "persona", "journey map"],
    "graphic design": ["graphic design", "visual design", "typography", "branding"],
    "canva": ["canva"], "portfolio": ["portfolio", "behance", "dribbble"],
    # banking
    "finance": ["finance", "financial analysis", "financial modelling", "financial modeling"],
    "accounting": ["accounting", "ledger", "reconciliation", "balance sheet", "p&l"],
    "risk management": ["risk management", "risk assessment", "credit risk", "operational risk"],
    "compliance": ["compliance", "regulatory", "kyc", "aml", "audit"],
    "customer service": ["customer service", "client relationship", "relationship management"],
    # digital media
    "content creation": ["content creation", "content", "copywriting", "blog", "article"],
    "social media": ["social media", "instagram", "tiktok", "facebook", "youtube", "linkedin"],
    "storytelling": ["storytelling", "narrative", "brand voice", "script"],
    "seo": ["seo", "search engine optimisation", "search engine optimization"],
    "digital marketing": ["digital marketing", "campaign", "content calendar", "paid social"],
    "video editing": ["video editing", "premiere", "after effects", "capcut"],
    "analytics": ["analytics", "google analytics", "metrics", "conversion"],
}

_PATTERNS = {
    skill: re.compile(r"(?<![\w+#.])(?:" + "|".join(re.escape(a) for a in aliases) + r")(?![\w+#])", re.I)
    for skill, aliases in SKILL_ALIASES.items()
}

try:
    import spacy
    from spacy.matcher import PhraseMatcher
    _NLP = spacy.blank("en")
    _MATCHER = PhraseMatcher(_NLP.vocab, attr="LOWER")
    for _skill, _aliases in SKILL_ALIASES.items():
        _MATCHER.add(_skill, [_NLP.make_doc(a) for a in _aliases])
    HAVE_SPACY = True
except Exception:
    HAVE_SPACY = False

def extract_skills(text):
    """Return the sorted list of canonical skills mentioned in `text`."""
    if HAVE_SPACY:
        doc = _NLP.make_doc(text)
        found = {_NLP.vocab.strings[m_id] for m_id, _, _ in _MATCHER(doc)}

        found |= {s for s, p in _PATTERNS.items() if p.search(text)}
        return sorted(found)
    return sorted(s for s, p in _PATTERNS.items() if p.search(text))

# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}
_NUM = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
_EXP = re.compile(_NUM + r"\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:[\w/-]+\s+){0,4}experience", re.I)

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

# 01/2013 to 01/2016, 2013-2016, Jan 2013 – Present
_DATE_RANGE = re.compile(
    r"(?:(?P<m1>0?[1-9]|1[0-2])[/-](?P<y1>(?:19|20)\d{2})|"
    r"(?P<mon1>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(?P<y1b>(?:19|20)\d{2})|"
    r"(?P<y1c>(?:19|20)\d{2}))"
    r"\s*(?:to|until|through|–|—|-)\s*"
    r"(?:(?P<m2>0?[1-9]|1[0-2])[/-](?P<y2>(?:19|20)\d{2})|"
    r"(?P<mon2>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(?P<y2b>(?:19|20)\d{2})|"
    r"(?P<y2c>(?:19|20)\d{2})|present|current|now|today)",
    re.I,
)


def _to_num(value):
    if value is None:
        return None
    value = str(value).strip().lower()
    if value in _WORD_NUMBERS:
        return _WORD_NUMBERS[value]
    try:
        return int(value)
    except ValueError:
        return None


def _month_year(match, side):
    """Return (year, month) for one side of a date-range match."""
    if side == 1:
        y = match.group("y1") or match.group("y1b") or match.group("y1c")
        m = match.group("m1")
        mon = match.group("mon1")
    else:
        y = match.group("y2") or match.group("y2b") or match.group("y2c")
        m = match.group("m2")
        mon = match.group("mon2")
    if not y:
        return None
    year = int(y)
    if m:
        month = int(m)
    elif mon:
        month = _MONTHS.get(mon.lower()[:3], 1)
    else:
        month = 1
    return year, month


def experience_intervals(text):
    """Return merged (start_month_index, end_month_index) work intervals.

    Month index = year*12 + (month-1).  Overlapping roles are merged so a
    candidate is not credited twice for concurrent work.
    """
    intervals = []
    for match in _DATE_RANGE.finditer(text or ""):
        start = _month_year(match, 1)
        end_raw = match.group("y2") or match.group("y2b") or match.group("y2c")
        if not end_raw:
            # 'Present' / 'current' / 'now'
            end = (2026, 1)
        else:
            end = _month_year(match, 2)
        if not start or not end:
            continue
        s = start[0] * 12 + (start[1] - 1)
        e = end[0] * 12 + (end[1] - 1)
        if e < s:
            s, e = e, s
        if e - s > 0:
            intervals.append((s, e))
    intervals.sort()
    merged = []
    for s, e in intervals:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def extract_years_experience(text):
    """Best estimate of total years of experience (0 if none).

    Takes the larger of (a) an explicit 'N years ... experience' statement and
    (b) the merged duration of dated roles.  Word numbers ('six years') count.
    """
    explicit = 0
    for m in _EXP.finditer(text or ""):
        value = _to_num(m.group(1))
        if value is not None:
            explicit = max(explicit, value)
    months = sum(e - s for s, e in experience_intervals(text))
    dated = months / 12.0
    return int(round(max(explicit, dated)))

# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------
_EDU = [
    (3, re.compile(r"(?<!\w)(?:ph\.?\s?d|doctorate|doctor of philosophy|doctoral)(?!\w)", re.I)),
    (2, re.compile(r"(?<!\w)(?:master'?s?|master of|m\.?\s?tech|m\.?\s?sc|m\.?\s?s\.?|mba|m\.?b\.?a|postgraduate|pgdm)(?!\w)", re.I)),
    (1, re.compile(r"(?<!\w)(?:bachelor'?s?|bachelor of|b\.?\s?tech|b\.?\s?e\.?|b\.?\s?sc|b\.?\s?s\.?|bca|b\.?com|undergraduate)(?!\w)", re.I)),
]

def extract_education_level(text):
    """Highest degree level mentioned (0-3)."""
    for level, pattern in _EDU:
        if pattern.search(text or ""):
            return level
    return 0

def education_label(level):
    return {3: "Doctorate", 2: "Master's degree", 1: "Bachelor's degree", 0: "Not detected"}.get(level, "Not detected")
