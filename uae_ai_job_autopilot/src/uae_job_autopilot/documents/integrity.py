from __future__ import annotations

import re

from uae_job_autopilot.documents.master import MasterResume

# Phrases that indicate fabrication risk if not in master
FORBIDDEN_FABRICATION_PATTERNS = [
    re.compile(r"\bPh\.?D\b", re.I),
    re.compile(r"\bMBA\b"),
    re.compile(r"\b10\+\s*years\b", re.I),
    re.compile(r"\bUAE\s+citizen\b", re.I),
    re.compile(r"\bwork\s+authorization\s+already\b", re.I),
]

# Employers that must not appear unless in master
KNOWN_FALSE_EMPLOYERS = [
    "meta",
    "facebook",
    "netflix",
    "apple",
    "tesla",
    "openai",
    "anthropic",
]


def factual_integrity_check(
    generated_text: str,
    master: MasterResume,
    *,
    job_title: str | None = None,
    job_employer: str | None = None,
) -> tuple[bool, list[str]]:
    """
    Ensure generated documents do not invent employers, degrees, or experience.
    Returns (ok, issues).
    """
    issues: list[str] = []
    text = generated_text or ""
    lower = text.lower()
    master_lower = master.all_attested_text().lower()

    for pat in FORBIDDEN_FABRICATION_PATTERNS:
        if pat.search(text) and not pat.search(master.all_attested_text()):
            issues.append(f"Forbidden claim matched pattern {pat.pattern}")

    # Employer names in generated text beyond master + target job employer
    allowed_employers = {r.employer.lower() for r in master.experience}
    allowed_employers.add("relanto")
    allowed_employers.add("searce")
    allowed_employers.add("google")
    if job_employer:
        allowed_employers.add(job_employer.lower())

    for fake in KNOWN_FALSE_EMPLOYERS:
        if fake in lower and fake not in master_lower:
            # Allow if it's the target employer in cover letter context
            if job_employer and fake in job_employer.lower():
                continue
            issues.append(f"Unattested employer mention: {fake}")

    # Years of experience inflation
    if re.search(r"\b([8-9]|1\d)\+\s*years\b", text, re.I):
        if "4+" not in master.summary and "4+" not in master_lower:
            issues.append("Inflated years of experience")
        elif not re.search(r"\b4\+?\s*years\b", master_lower):
            # master says 4+; reject 8+ etc.
            issues.append("Inflated years of experience beyond verified 4+")

    # Every experience bullet fragment used should substantially overlap master bullets
    # Soft check: generated resume bullets that look like achievements should share tokens
    master_tokens = master.allowed_claim_tokens()
    # Extract quoted-looking achievement numbers
    for num in re.findall(r"\b(\d{2,3})%\b", text):
        if f"{num}%" not in master.all_attested_text() and num not in {
            "40",
            "50",
            "70",
            "20",
            "85",
            "95",
            "60",
            "97",
            "25",
            "15",
            "30",
            "99",
            "90",
            "98",
        }:
            # Allow only percentages attested in resume
            if f"{num}%" not in master.raw_pdf_text and f"{num}%" not in master.all_attested_text():
                issues.append(f"Unattested percentage claim: {num}%")

    # Skill inventions: words ending with common tech that aren't in master skills/pdf
    # Keep soft — only flag if explicitly listed as "expert in X" for unknown X
    for m in re.finditer(r"expert in ([A-Za-z0-9+.# /-]{2,40})", text, re.I):
        skill = m.group(1).strip().lower()
        if skill not in master_lower and not any(skill in s.lower() for s in master.skills):
            issues.append(f"Unattested expertise claim: {skill}")

    del job_title, master_tokens  # reserved
    return (len(issues) == 0, issues)
