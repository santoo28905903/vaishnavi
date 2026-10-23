from __future__ import annotations

import hashlib
import re


def _norm(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s+/&.-]", "", text)
    return text


def job_fingerprint(
    *,
    employer: str,
    title: str,
    location: str,
    source_job_id: str | None = None,
    application_url: str | None = None,
) -> str:
    """Stable dedupe key preferring URL/job id, then employer+title+location."""
    if application_url:
        url = application_url.strip().lower().split("?")[0].rstrip("/")
        return "url:" + hashlib.sha256(url.encode()).hexdigest()[:24]
    if source_job_id:
        return "id:" + _norm(source_job_id)[:64]
    basis = "|".join([_norm(employer), _norm(title), _norm(location)])
    return "fp:" + hashlib.sha256(basis.encode()).hexdigest()[:24]


def soft_fingerprint(*, employer: str, title: str, location: str) -> str:
    basis = "|".join([_norm(employer), _norm(title), _norm(location)])
    return "soft:" + hashlib.sha256(basis.encode()).hexdigest()[:24]
