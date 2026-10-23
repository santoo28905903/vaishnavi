from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

from uae_job_autopilot.config import (
    DEFAULT_CONFIG_DIR,
    PACKAGE_ROOT,
    CandidateProfile,
    load_candidate_profile,
)
from uae_job_autopilot.models.cache import JsonFileCache

logger = logging.getLogger(__name__)

# Skills attested on the verified resume PDF / candidate brief — do not invent extras.
KNOWN_SKILLS = [
    "Python",
    "SQL",
    "LangGraph",
    "LangChain",
    "Google ADK",
    "MCP",
    "RAG",
    "Generative AI",
    "Agentic AI",
    "LLMs",
    "FastAPI",
    "Flask",
    "Docker",
    "Vertex AI",
    "Document AI",
    "Cloud Run",
    "BigQuery",
    "AWS",
    "Bedrock",
    "MLOps",
    "semantic search",
    "embeddings",
    "vector databases",
    "computer vision",
    "document intelligence",
    "NLP",
    "PyTorch",
    "TensorFlow",
    "GCP",
]


def extract_pdf_text(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        chunks.append(text)
    return "\n".join(chunks).strip()


def _resolve_resume_path(relative: str) -> Path:
    p = Path(relative)
    if p.is_absolute() and p.exists():
        return p
    cand = PACKAGE_ROOT / relative
    if cand.exists():
        return cand
    return PACKAGE_ROOT / "data" / "resume" / Path(relative).name


def skills_mentioned_in_text(text: str) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for skill in KNOWN_SKILLS:
        if skill.lower() in lower:
            found.append(skill)
    return found


@lru_cache(maxsize=4)
def _cached_parse(pdf_str: str, mtime_ns: int) -> str:
    del mtime_ns
    return extract_pdf_text(Path(pdf_str))


def load_parsed_resume(
    *,
    config_dir: Path | None = None,
    cache: JsonFileCache | None = None,
) -> CandidateProfile:
    """
    Merge candidate.yaml with truthful PDF text extraction.
    Never invents employment history or skills beyond resume evidence + config.
    """
    profile = load_candidate_profile(config_dir or DEFAULT_CONFIG_DIR)
    pdf_path = _resolve_resume_path(profile.resume_pdf)
    cache = cache or JsonFileCache("parsed_resume")

    if not pdf_path.exists():
        logger.warning("Resume PDF missing at %s — using YAML profile only", pdf_path)
        profile.skills = list(KNOWN_SKILLS)
        return profile

    key = JsonFileCache.key_for(str(pdf_path), pdf_path.stat().st_mtime_ns)
    cached = cache.get_json(key)
    if cached and cached.get("text"):
        text = str(cached["text"])
    else:
        text = _cached_parse(str(pdf_path), pdf_path.stat().st_mtime_ns)
        cache.set_json(key, {"text": text, "pdf": str(pdf_path)})

    profile.resume_text = text
    profile.skills = skills_mentioned_in_text(text) or list(KNOWN_SKILLS)
    # Summary: first paragraph-ish from PDF if present
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        # Skip name/header lines; grab professional summary block when present
        joined = " ".join(lines)
        m = re.search(
            r"PROFESSIONAL SUMMARY(.+?)CORE COMPETENCIES",
            joined,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m:
            profile.summary = re.sub(r"\s+", " ", m.group(1)).strip()[:1200]
        else:
            profile.summary = " ".join(lines[:8])[:1200]
    return profile


def candidate_state_for_jev(profile: CandidateProfile) -> dict:
    return {
        "full_name": profile.full_name,
        "location": f"{profile.current_city}, {profile.current_country}",
        "experience_years_approx": profile.total_experience_years_approx,
        "current_title": profile.current_title,
        "current_employer": profile.current_employer,
        "previous_employers": profile.previous_employers,
        "skills": profile.skills,
        "requires_employer_sponsorship": profile.requires_employer_sponsorship,
        "relocation_willing": profile.relocation_willing,
        "notice_period_days": profile.notice_period_days,
        "expected_monthly_aed": profile.expected_monthly_aed_default,
        "summary": profile.summary[:1500],
        "resume_excerpt": profile.resume_text[:4000],
    }


def resume_embedding_document(profile: CandidateProfile) -> str:
    parts = [
        profile.current_title,
        profile.summary,
        "Skills: " + ", ".join(profile.skills),
        profile.resume_text[:6000],
    ]
    return "\n".join(p for p in parts if p)
