from __future__ import annotations

import re
from typing import Any

from uae_job_autopilot.config import CandidateProfile, ModelsConfig
from uae_job_autopilot.domain.enums import SponsorshipLabel, VisaEvidenceLabel
from uae_job_autopilot.domain.models import JobPosting, VisaAssessment
from uae_job_autopilot.matching.hard_rules import NATIONALS_ONLY, NO_SPONSORSHIP

SPONSORS = re.compile(
    r"("
    r"visa\s+sponsorship\s+(?:is\s+)?(?:available|provided|offered)|"
    r"will\s+sponsor\s+(?:a\s+)?(?:work\s+)?visa|"
    r"employer\s+sponsored|"
    r"sponsorship\s+available|"
    r"relocation\s+(?:support|package)\s+(?:to\s+)?(?:the\s+)?uae|"
    r"work\s+authorization\s+sponsored"
    r")",
    re.IGNORECASE,
)

RELOCATION = re.compile(
    r"(relocation\s+(?:assistance|support|package)|relocate\s+to\s+(?:dubai|abu\s+dhabi|uae))",
    re.IGNORECASE,
)


def deterministic_visa_signals(job: JobPosting) -> tuple[float, SponsorshipLabel, list[str], VisaEvidenceLabel]:
    """
    Returns (score 0-100, sponsorship_label, signals, evidence_label).
    Unknown/unclear must never be treated as confirmed sponsorship.
    """
    blob = " ".join(
        filter(None, [job.title, job.employer, job.location_raw, job.description_text or ""])
    )
    signals: list[str] = []

    if NATIONALS_ONLY.search(blob):
        signals.append("nationals_only_language")
        return 0.0, SponsorshipLabel.NATIONALS_ONLY, signals, VisaEvidenceLabel.BLOCKER

    if NO_SPONSORSHIP.search(blob):
        signals.append("explicit_no_sponsorship")
        return 5.0, SponsorshipLabel.NO_SPONSORSHIP, signals, VisaEvidenceLabel.BLOCKER

    if SPONSORS.search(blob):
        signals.append("explicit_sponsorship_language")
        score = 90.0
        if RELOCATION.search(blob):
            signals.append("relocation_support")
            score = 95.0
        return score, SponsorshipLabel.SPONSORS, signals, VisaEvidenceLabel.STRONG_POSITIVE

    if RELOCATION.search(blob):
        signals.append("relocation_mention_without_explicit_sponsorship")
        # Weak positive — not confirmed sponsorship
        return 55.0, SponsorshipLabel.UNCLEAR, signals, VisaEvidenceLabel.WEAK_POSITIVE

    signals.append("sponsorship_not_stated")
    return 40.0, SponsorshipLabel.UNCLEAR, signals, VisaEvidenceLabel.NEUTRAL


def jev_visa_score(choice: str | None, confidence: float | None = None) -> tuple[float, SponsorshipLabel]:
    mapping = {
        "sponsors": (92.0, SponsorshipLabel.SPONSORS),
        "no_sponsorship": (5.0, SponsorshipLabel.NO_SPONSORSHIP),
        "nationals_only": (0.0, SponsorshipLabel.NATIONALS_ONLY),
        "unclear": (40.0, SponsorshipLabel.UNCLEAR),
    }
    if not choice or choice not in mapping:
        return 40.0, SponsorshipLabel.UNKNOWN
    score, label = mapping[choice]
    if confidence is not None and confidence < 0.45 and label == SponsorshipLabel.SPONSORS:
        # Low-confidence "sponsors" → treat as unclear; never confirm
        return 45.0, SponsorshipLabel.UNCLEAR
    return score, label


def combine_visa_assessment(
    job: JobPosting,
    profile: CandidateProfile,
    models: ModelsConfig,
    *,
    jev_answer: dict[str, Any] | None = None,
    hard_blocked: bool = False,
) -> VisaAssessment:
    det_score, det_label, signals, evidence = deterministic_visa_signals(job)
    notes: list[str] = []
    jev_score: float | None = None
    sponsorship = det_label
    jev_raw: dict[str, Any] = {}

    if hard_blocked:
        notes.append("Hard exclusion already blocked sponsorship/nationality")
        return VisaAssessment(
            deterministic_score=det_score,
            jev_score=None,
            combined_score=det_score,
            threshold=models.visa_threshold,
            passed=False,
            sponsorship_label=det_label
            if det_label != SponsorshipLabel.UNCLEAR
            else SponsorshipLabel.NO_SPONSORSHIP,
            evidence_label=VisaEvidenceLabel.BLOCKER,
            deterministic_signals=signals,
            notes=notes,
            sponsorship_confirmed=False,
        )

    if jev_answer:
        jev_raw = dict(jev_answer)
        choice = jev_answer.get("choice")
        conf = jev_answer.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf_f = None
        jev_score, jev_label = jev_visa_score(str(choice) if choice else None, conf_f)
        # Deterministic blockers / explicit labels win over Jev
        if det_label in {
            SponsorshipLabel.NATIONALS_ONLY,
            SponsorshipLabel.NO_SPONSORSHIP,
        }:
            sponsorship = det_label
            notes.append("Deterministic sponsorship blocker overrides Jev label")
        elif det_label == SponsorshipLabel.SPONSORS:
            sponsorship = SponsorshipLabel.SPONSORS
        else:
            sponsorship = jev_label
    else:
        notes.append("Jev visa assessment unavailable; deterministic signals only")

    if jev_score is None:
        combined = det_score
    else:
        combined = (
            models.visa_deterministic_weight * det_score
            + models.visa_jev_weight * jev_score
        )

    # Explicit blockers always fail visa gate
    if sponsorship in {SponsorshipLabel.NATIONALS_ONLY, SponsorshipLabel.NO_SPONSORSHIP}:
        passed = False
        evidence = VisaEvidenceLabel.BLOCKER
    else:
        passed = combined >= models.visa_threshold

    confirmed = sponsorship == SponsorshipLabel.SPONSORS and (
        "explicit_sponsorship_language" in signals
        or (jev_answer or {}).get("choice") == "sponsors"
    )
    # Never claim unclear/unknown as confirmed
    if sponsorship in {SponsorshipLabel.UNCLEAR, SponsorshipLabel.UNKNOWN}:
        confirmed = False
        notes.append("Sponsorship not confirmed (unknown/unclear ≠ sponsored)")

    if profile.requires_employer_sponsorship and not confirmed and passed:
        # Passing score with unclear sponsorship is allowed for ranking, but not confirmed
        notes.append(
            "Candidate requires sponsorship; posting does not confirm sponsorship"
        )

    return VisaAssessment(
        deterministic_score=det_score,
        jev_score=jev_score,
        combined_score=round(combined, 2),
        threshold=models.visa_threshold,
        passed=passed,
        sponsorship_label=sponsorship,
        evidence_label=evidence,
        deterministic_signals=signals,
        jev_raw=jev_raw,
        notes=notes,
        sponsorship_confirmed=confirmed,
    )
