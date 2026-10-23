from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from uae_job_autopilot.matching.resume import extract_pdf_text


REQUIRED_HEADINGS = [
    "professional summary",
    "skills",
    "work experience",
    "education",
]


class ATSAssessment(BaseModel):
    structure_score: float
    keyword_score: float
    combined_score: float
    threshold: float = 80.0
    passed: bool
    structure_weight: float = 0.40
    keyword_weight: float = 0.60
    headings_found: list[str] = Field(default_factory=list)
    keywords_hit: list[str] = Field(default_factory=list)
    keywords_missed: list[str] = Field(default_factory=list)
    reparsed_chars: int = 0
    notes: list[str] = Field(default_factory=list)


def extract_job_keywords(job_title: str, job_description: str | None, limit: int = 25) -> list[str]:
    blob = f"{job_title} {job_description or ''}".lower()
    # Prefer AI/ML-relevant tokens
    priority = [
        "python",
        "sql",
        "rag",
        "llm",
        "langchain",
        "langgraph",
        "fastapi",
        "docker",
        "vertex",
        "gcp",
        "aws",
        "mlops",
        "embeddings",
        "nlp",
        "generative",
        "agentic",
        "machine learning",
        "data scientist",
        "fastapi",
        "bigquery",
        "bedrock",
    ]
    hits = [k for k in priority if k in blob]
    # Add significant title tokens
    for tok in re.findall(r"[a-z]{4,}", job_title.lower()):
        if tok not in hits and tok not in {"senior", "engineer", "united", "arab", "emirates"}:
            hits.append(tok)
    return hits[:limit]


def score_structure(text: str) -> tuple[float, list[str]]:
    lower = text.lower()
    found = [h for h in REQUIRED_HEADINGS if h in lower]
    # Contact signals
    contact_points = 0
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        contact_points += 1
    if re.search(r"\+?\d[\d\s-]{8,}", text):
        contact_points += 1
    heading_score = (len(found) / len(REQUIRED_HEADINGS)) * 85.0
    contact_score = (contact_points / 2) * 15.0
    return min(100.0, heading_score + contact_score), found


def score_keywords(text: str, keywords: list[str]) -> tuple[float, list[str], list[str]]:
    if not keywords:
        return 100.0, [], []
    lower = text.lower()
    hit = [k for k in keywords if k.lower() in lower]
    miss = [k for k in keywords if k.lower() not in lower]
    return (len(hit) / len(keywords)) * 100.0, hit, miss


def assess_ats_pdf(
    pdf_path: Path,
    *,
    job_title: str,
    job_description: str | None = None,
    threshold: float = 80.0,
    structure_weight: float = 0.40,
    keyword_weight: float = 0.60,
) -> ATSAssessment:
    text = extract_pdf_text(pdf_path)
    structure, headings = score_structure(text)
    keywords = extract_job_keywords(job_title, job_description)
    kw_score, hit, miss = score_keywords(text, keywords)
    combined = structure_weight * structure + keyword_weight * kw_score
    notes = []
    if len(text) < 200:
        notes.append("Reparsed PDF text unusually short — possible render issue")
    return ATSAssessment(
        structure_score=round(structure, 2),
        keyword_score=round(kw_score, 2),
        combined_score=round(combined, 2),
        threshold=threshold,
        passed=combined >= threshold,
        structure_weight=structure_weight,
        keyword_weight=keyword_weight,
        headings_found=headings,
        keywords_hit=hit,
        keywords_missed=miss,
        reparsed_chars=len(text),
        notes=notes,
    )
