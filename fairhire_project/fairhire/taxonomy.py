"""Role competency taxonomy for FairHire.

Each role is described as a small set of *human-readable competencies* rather than
loose keywords.  Every competency has:
  key       stable identifier
  label     plain-language name shown in the UI
  aliases   phrases that count as evidence (case-insensitive)
  weight    relative importance inside the role (normalised at scoring time)
  core      True = required for the role, False = preferred / bonus
  hint      what a reviewer should look for

Why a hand-written taxonomy?  It is inspectable.  A recruiter can read exactly
which phrases count, edit them for a real vacancy, and see the sentence that
triggered every match.  Nothing is hidden inside a trained model.
"""

ROLE_PROFILES = {
    "Engineering": {
        "summary": "Designs, builds, tests and documents technical systems, products or processes.",
        "competencies": [
            {"key": "engineering_design", "label": "Engineering design & process development", "core": True, "weight": 1.35,
             "aliases": ["engineering design", "process development", "design and implement", "prototype", "cad",
                         "manufacturing", "production process", "mechanical design", "electrical design",
                         "structural", "schematics", "solidworks", "autocad", "product design", "engineering"],
             "hint": "Evidence of designing, building or improving a physical/technical system or process."},
            {"key": "testing_quality", "label": "Testing, quality assurance & defect analysis", "core": True, "weight": 1.30,
             "aliases": ["testing", "quality assurance", "quality control", "quality technician", "qa", "defect",
                         "validation", "verification", "inspection", "root cause", "test plan", "test case",
                         "quality tests", "product defects", "iso 9001", "six sigma"],
             "hint": "Evidence of testing, inspection, quality control or finding/fixing defects."},
            {"key": "problem_solving", "label": "Structured problem solving & analysis", "core": True, "weight": 1.20,
             "aliases": ["problem solving", "problem-solving", "root cause", "troubleshooting", "analytical",
                         "analysis", "optimisation", "optimization", "diagnose", "failure analysis", "troubleshoot"],
             "hint": "Evidence of diagnosing a problem and choosing a reasoned solution."},
            {"key": "documentation", "label": "Technical documentation & reporting", "core": True, "weight": 1.00,
             "aliases": ["documentation", "technical report", "technical documentation", "sop", "standard operating",
                         "specification", "procedures", "manual", "documented", "reporting", "prepared statements"],
             "hint": "Evidence of writing specifications, reports, procedures or documentation."},
            {"key": "engineering_data", "label": "Engineering data, measurement & tools", "core": True, "weight": 1.05,
             "aliases": ["sql", "python", "excel", "statistics", "statistical", "data analysis", "matlab", "jmp",
                         "spss", "tableau", "measurement", "sensor", "data visualization", "data visualisation",
                         "pandas", "r programming", "sas", "gis"],
             "hint": "Evidence of using data, measurement or technical software to support engineering work."},
            {"key": "project_delivery", "label": "Project delivery & collaboration", "core": False, "weight": 0.80,
             "aliases": ["project management", "project schedule", "managed projects", "cross-functional",
                         "stakeholder", "team", "budget", "agile", "scrum", "co-ordinated", "coordinated",
                         "managed small projects", "delivered"],
             "hint": "Evidence of delivering work on schedule with other people."},
            {"key": "safety_compliance", "label": "Safety, standards & compliance", "core": False, "weight": 0.55,
             "aliases": ["safety", "compliance", "regulatory", "iso", "osha", "environmental regulation",
                         "standard operating procedures", "risk assessment"],
             "hint": "Evidence of working to safety, quality or regulatory standards."},
        ],
    },
    "Information Technology": {
        "summary": "Keeps systems, networks, software and data working securely and reliably.",
        "competencies": [
            {"key": "troubleshooting_support", "label": "Troubleshooting & technical support", "core": True, "weight": 1.35,
             "aliases": ["troubleshooting", "technical support", "help desk", "helpdesk", "service desk", "incident",
                         "diagnose", "resolve", "ticket", "root cause", "desktop support"],
             "hint": "Evidence of diagnosing and resolving technical issues for users or systems."},
            {"key": "systems_networking", "label": "Systems, servers & networking", "core": True, "weight": 1.25,
             "aliases": ["networking", "network", "server", "windows server", "active directory", "tcp/ip", "dns",
                         "dhcp", "vpn", "firewall", "router", "switch", "linux", "system administration", "virtualisation",
                         "virtualization", "vmware"],
             "hint": "Evidence of administering systems, servers or networks."},
            {"key": "software_data", "label": "Software, scripting & data", "core": True, "weight": 1.15,
             "aliases": ["python", "sql", "java", "javascript", "scripting", "bash", "powershell", "database",
                         "api", "git", "software", "development", "automation"],
             "hint": "Evidence of building or automating with code, databases or APIs."},
            {"key": "security", "label": "Security & access control", "core": True, "weight": 1.10,
             "aliases": ["cybersecurity", "cyber security", "security", "access control", "encryption", "malware",
                         "vulnerability", "penetration testing", "siem", "splunk", "backup", "disaster recovery"],
             "hint": "Evidence of protecting systems, data or access."},
            {"key": "cloud", "label": "Cloud & infrastructure", "core": False, "weight": 0.80,
             "aliases": ["aws", "azure", "google cloud", "gcp", "cloud", "docker", "kubernetes", "terraform", "ci/cd"],
             "hint": "Evidence of deploying or running services in the cloud."},
            {"key": "communication", "label": "User communication & documentation", "core": True, "weight": 0.95,
             "aliases": ["communication", "documentation", "training", "stakeholder", "customer", "support",
                         "explained", "presented", "written"],
             "hint": "Evidence of explaining technical work clearly to users or colleagues."},
        ],
    },
    "Design": {
        "summary": "Turns user needs into clear, usable visual and interactive experiences.",
        "competencies": [
            {"key": "visual_design", "label": "Visual design & layout", "core": True, "weight": 1.30,
             "aliases": ["visual design", "graphic design", "layout", "typography", "colour", "color", "branding",
                         "illustration", "adobe", "photoshop", "illustrator", "indesign", "canva", "figma"],
             "hint": "Evidence of visual craft: layout, type, colour, branding or graphics."},
            {"key": "prototyping", "label": "Prototyping & design tools", "core": True, "weight": 1.25,
             "aliases": ["prototyping", "prototype", "figma", "sketch", "adobe xd", "wireframe", "mockup",
                         "design system", "interaction design", "ui", "ux", "ui/ux"],
             "hint": "Evidence of turning ideas into wireframes, prototypes or design systems."},
            {"key": "user_research", "label": "User research & usability", "core": True, "weight": 1.15,
             "aliases": ["user research", "usability", "user testing", "interview", "persona", "journey map",
                         "accessibility", "a/b test", "user-centred", "user-centered", "research"],
             "hint": "Evidence of learning from users and testing designs with them."},
            {"key": "creative_problem_solving", "label": "Creative problem solving", "core": True, "weight": 1.00,
             "aliases": ["creative", "concept", "ideation", "brainstorm", "problem solving", "problem-solving",
                         "storyboard", "campaign", "art direction"],
             "hint": "Evidence of developing concepts to solve a design problem."},
            {"key": "portfolio", "label": "Portfolio & delivered work", "core": True, "weight": 0.95,
             "aliases": ["portfolio", "behance", "dribbble", "case study", "showcase", "exhibition", "published work"],
             "hint": "Evidence of finished, shareable design work."},
            {"key": "collaboration", "label": "Collaboration & handoff", "core": False, "weight": 0.65,
             "aliases": ["collaboration", "stakeholder", "cross-functional", "developer handoff", "design review",
                         "team", "client", "brief"],
             "hint": "Evidence of working with clients, developers or product teams."},
        ],
    },
    "Banking": {
        "summary": "Handles money, risk and customer relationships accurately and compliantly.",
        "competencies": [
            {"key": "financial_analysis", "label": "Financial & numerical analysis", "core": True, "weight": 1.30,
             "aliases": ["financial analysis", "finance", "accounting", "financial modelling", "financial modeling",
                         "valuation", "budget", "forecast", "reconciliation", "ledger", "p&l", "balance sheet"],
             "hint": "Evidence of analysing financial information or accounts."},
            {"key": "accuracy_compliance", "label": "Accuracy & regulatory compliance", "core": True, "weight": 1.25,
             "aliases": ["accuracy", "attention to detail", "compliance", "regulatory", "kyc", "aml", "audit",
                         "reconciliation", "risk control", "policy", "data protection"],
             "hint": "Evidence of careful, compliant handling of records or transactions."},
            {"key": "customer_service", "label": "Customer service & relationships", "core": True, "weight": 1.15,
             "aliases": ["customer service", "client relationship", "customer", "client", "advisory", "sales",
                         "relationship management", "service", "complaint"],
             "hint": "Evidence of serving customers or managing client relationships."},
            {"key": "risk", "label": "Risk assessment & controls", "core": True, "weight": 1.05,
             "aliases": ["risk management", "risk assessment", "credit risk", "market risk", "operational risk",
                         "controls", "fraud", "portfolio risk"],
             "hint": "Evidence of identifying and managing financial risk."},
            {"key": "excel_data", "label": "Spreadsheets & data tools", "core": True, "weight": 0.95,
             "aliases": ["excel", "advanced excel", "sql", "python", "tableau", "power bi", "sas", "spss",
                         "data analysis", "pivot table", "vlookup"],
             "hint": "Evidence of using spreadsheets or data tools to do the work."},
            {"key": "communication", "label": "Clear communication & reporting", "core": False, "weight": 0.70,
             "aliases": ["communication", "reporting", "presentation", "stakeholder", "written", "explained"],
             "hint": "Evidence of explaining financial information clearly."},
        ],
    },
    "Digital Media": {
        "summary": "Creates and distributes content that grows an audience and tells a story.",
        "competencies": [
            {"key": "content_creation", "label": "Content creation & production", "core": True, "weight": 1.30,
             "aliases": ["content creation", "content", "copywriting", "writing", "blog", "article", "video editing",
                         "premiere", "after effects", "photography", "podcast", "graphic", "canva"],
             "hint": "Evidence of making content across formats."},
            {"key": "social_media", "label": "Social media & community", "core": True, "weight": 1.25,
             "aliases": ["social media", "instagram", "tiktok", "linkedin", "facebook", "youtube", "twitter",
                         "community management", "engagement", "influencer", "campaign"],
             "hint": "Evidence of running or growing social channels."},
            {"key": "storytelling", "label": "Storytelling & brand voice", "core": True, "weight": 1.10,
             "aliases": ["storytelling", "story", "narrative", "brand voice", "brand", "messaging", "creative",
                         "script", "audience"],
             "hint": "Evidence of shaping a narrative or brand voice."},
            {"key": "analytics_seo", "label": "Analytics, SEO & performance", "core": True, "weight": 1.05,
             "aliases": ["analytics", "seo", "search engine optimisation", "search engine optimization", "google analytics",
                         "metrics", "conversion", "a/b test", "reach", "impressions", "performance"],
             "hint": "Evidence of measuring and improving content performance."},
            {"key": "campaign_delivery", "label": "Campaign planning & delivery", "core": True, "weight": 0.95,
             "aliases": ["digital marketing", "campaign", "content calendar", "editorial calendar", "launch",
                         "strategy", "media plan", "paid social", "advertising"],
             "hint": "Evidence of planning and delivering campaigns."},
            {"key": "production_tools", "label": "Production tools", "core": False, "weight": 0.65,
             "aliases": ["adobe", "photoshop", "premiere", "after effects", "canva", "capcut", "figma", "hootsuite",
                         "buffer", "mailchimp"],
             "hint": "Evidence of fluency with content-production tools."},
        ],
    },
}

# Friendly names for the five role categories.
ROLE_ORDER = ["Engineering", "Information Technology", "Design", "Banking", "Digital Media"]


def get_profile(role_title):
    """Return the profile for a role title, falling back to Engineering."""
    if role_title in ROLE_PROFILES:
        return ROLE_PROFILES[role_title]
    for name, profile in ROLE_PROFILES.items():
        if name.lower() in str(role_title).lower():
            return profile
    return ROLE_PROFILES["Engineering"]


def competency_lookup(role_title):
    return {c["key"]: c for c in get_profile(role_title)["competencies"]}
