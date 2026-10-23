from __future__ import annotations

from typing import Any

from uae_job_autopilot.config import CandidateProfile, ModelsConfig
from uae_job_autopilot.domain.models import JobPosting, ResumeFitAssessment
from uae_job_autopilot.matching.resume import resume_embedding_document
from uae_job_autopilot.models.embeddings import EmbeddingService
from uae_job_autopilot.models.jev import noul_to_100, score_answer_to_100


def job_embedding_document(job: JobPosting) -> str:
    parts = [
        job.title,
        job.employer,
        job.location_raw,
        (job.description_text or "")[:6000],
    ]
    return "\n".join(parts)


def rubric_from_jev_answers(answers: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """
    Rubric = weighted blend of relevance, skill alignment, seniority compatibility.
    All on 0..100.
    """
    rel = score_answer_to_100(answers.get("job_relevance"))
    skills = score_answer_to_100(answers.get("skill_alignment"))
    seniority = noul_to_100(answers.get("seniority_ok"))
    parts = [p for p in (rel, skills, seniority) if p is not None]
    if not parts:
        return None, {"job_relevance": rel, "skill_alignment": skills, "seniority_ok": seniority}
    # Equal weight among available components
    rubric = sum(parts) / len(parts)
    return rubric, {
        "job_relevance": rel,
        "skill_alignment": skills,
        "seniority_ok": seniority,
        "components_used": len(parts),
    }


def combine_resume_fit(
    *,
    embedding_score: float,
    rubric_score: float | None,
    models: ModelsConfig,
    jev_raw: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> ResumeFitAssessment:
    notes = list(notes or [])
    if rubric_score is None:
        # Deterministic-insufficient path without Jev: embedding alone is not enough
        # to pass the 75 threshold policy — mark combined as embedding-only and fail
        # unless embedding is extremely high? Spec: 40% emb + 60% rubric.
        # Without rubric, do not invent rubric; report needs_model via caller.
        combined = embedding_score
        notes.append("Rubric (Jev) unavailable; combined score is embedding-only")
        passed = False
    else:
        combined = (
            models.resume_embedding_weight * embedding_score
            + models.resume_rubric_weight * rubric_score
        )
        passed = combined >= models.resume_threshold

    return ResumeFitAssessment(
        embedding_score=round(embedding_score, 2),
        rubric_score=None if rubric_score is None else round(rubric_score, 2),
        combined_score=round(combined, 2),
        threshold=models.resume_threshold,
        passed=passed,
        embedding_weight=models.resume_embedding_weight,
        rubric_weight=models.resume_rubric_weight,
        jev_raw=jev_raw or {},
        notes=notes,
    )


def compute_embedding_score(
    profile: CandidateProfile,
    job: JobPosting,
    embeddings: EmbeddingService,
) -> float:
    return embeddings.similarity_0_100(
        resume_embedding_document(profile),
        job_embedding_document(job),
    )
