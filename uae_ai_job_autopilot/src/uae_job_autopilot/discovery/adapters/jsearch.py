from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from uae_job_autopilot.config import SearchProfile, SourceConfig, get_settings
from uae_job_autopilot.discovery.adapters.common import require_enabled
from uae_job_autopilot.discovery.base import SourceAdapter
from uae_job_autopilot.discovery.normalize import build_job
from uae_job_autopilot.domain.enums import AccessMode, PublicationTimeConfidence, SourceStatus
from uae_job_autopilot.domain.models import AdapterFetchResult, JobPosting, SourceHealth
from uae_job_autopilot.utils.http import get_json
from uae_job_autopilot.utils.location import is_uae_location
from uae_job_autopilot.utils.money import salary_from_jsearch
from uae_job_autopilot.utils.timeutil import parse_datetime, utcnow

logger = logging.getLogger(__name__)


class JSearchAdapter(SourceAdapter):
    name = "jsearch"

    def fetch(
        self,
        *,
        client: httpx.Client,
        profile: SearchProfile,
        source_cfg: SourceConfig,
        dry_run: bool = False,
    ) -> AdapterFetchResult:
        settings = get_settings()
        skipped = require_enabled(
            source=self.name,
            access_mode=AccessMode.LICENSED_API,
            source_cfg=source_cfg,
            env_value=settings.jsearch_api_key,
            requires_env="JSEARCH_API_KEY",
        )
        if skipped:
            return skipped

        if dry_run:
            now = utcnow()
            return AdapterFetchResult(
                health=SourceHealth(
                    source=self.name,
                    access_mode=AccessMode.LICENSED_API,
                    status=SourceStatus.SKIPPED_DISABLED,
                    attempted=False,
                    detail="dry_run: would query JSearch RapidAPI for UAE AI/ML roles",
                    started_at=now,
                    finished_at=now,
                ),
                jobs=[],
            )

        started = utcnow()
        assert settings.jsearch_api_key
        headers = {
            "X-RapidAPI-Key": settings.jsearch_api_key,
            "X-RapidAPI-Host": settings.jsearch_api_host,
        }
        queries = [
            "AI Engineer UAE",
            "Machine Learning Engineer Dubai",
            "Data Scientist Abu Dhabi",
            "Generative AI Dubai",
            "LLM Engineer United Arab Emirates",
        ]
        # Prefer configured titles if present
        if profile.target_titles:
            queries = [
                f"{profile.target_titles[0]} Dubai",
                f"{profile.target_titles[min(1, len(profile.target_titles)-1)]} UAE",
                "Machine Learning Engineer Dubai",
                "AI Engineer Abu Dhabi",
            ]

        jobs: list[JobPosting] = []
        raw_count = 0
        errors: list[str] = []
        last_status: int | None = None
        seen_ids: set[str] = set()
        queries_ok = 0

        for q in queries:
            params = {
                "query": q,
                "page": "1",
                "num_pages": "1",
                "date_posted": "today",
                "country": "ae",
            }
            url = f"https://{settings.jsearch_api_host}/search?{urlencode(params)}"
            try:
                status, payload = get_json(client, url, headers=headers)
                last_status = status
                if status == 429:
                    return AdapterFetchResult(
                        health=SourceHealth(
                            source=self.name,
                            access_mode=AccessMode.LICENSED_API,
                            status=SourceStatus.QUOTA_EXHAUSTED,
                            attempted=True,
                            jobs_fetched_raw=raw_count,
                            jobs_after_uae_filter=len(jobs),
                            error="HTTP 429 quota exhausted",
                            detail="JSearch rate/quota limit hit; partial results retained",
                            started_at=started,
                            finished_at=utcnow(),
                            http_status=429,
                        ),
                        jobs=[j for j in jobs if j.is_uae],
                    )
                if status != 200 or not isinstance(payload, dict):
                    errors.append(f"query={q!r} HTTP {status}")
                    continue
                data = payload.get("data") or []
                if not isinstance(data, list):
                    errors.append(f"query={q!r} unexpected payload")
                    continue
                queries_ok += 1
                raw_count += len(data)
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    jid = str(item.get("job_id") or "")
                    if jid and jid in seen_ids:
                        continue
                    if jid:
                        seen_ids.add(jid)
                    job = self._map_job(item)
                    if job is not None:
                        jobs.append(job)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"query={q!r}: {exc}")
                logger.exception("JSearch query failed: %s", q)

        finished = utcnow()
        uae_jobs = [j for j in jobs if j.is_uae]
        if queries_ok == 0:
            status = SourceStatus.FAILED
            detail = "; ".join(errors) or "All JSearch queries failed"
        elif not uae_jobs:
            status = SourceStatus.EMPTY
            detail = f"Ran {queries_ok} queries; {raw_count} raw; 0 UAE"
        else:
            status = SourceStatus.SUCCESS
            detail = f"Ran {queries_ok} queries; {raw_count} raw; {len(uae_jobs)} UAE"

        return AdapterFetchResult(
            health=SourceHealth(
                source=self.name,
                access_mode=AccessMode.LICENSED_API,
                status=status,
                attempted=True,
                jobs_fetched_raw=raw_count,
                jobs_after_uae_filter=len(uae_jobs),
                error="; ".join(errors) if status == SourceStatus.FAILED else None,
                detail=detail
                + (
                    f"; partial errors: {'; '.join(errors)}"
                    if errors and status != SourceStatus.FAILED
                    else ""
                ),
                started_at=started,
                finished_at=finished,
                http_status=last_status,
            ),
            jobs=uae_jobs,
        )

    def _map_job(self, item: dict[str, Any]) -> JobPosting | None:
        title = str(item.get("job_title") or "").strip()
        if not title:
            return None
        location_bits = [
            str(item.get("job_city") or ""),
            str(item.get("job_state") or ""),
            str(item.get("job_country") or ""),
        ]
        location = ", ".join(x for x in location_bits if x)
        # Also check job_location / publisher location fields
        if item.get("job_city") is None and item.get("job_location"):
            location = str(item.get("job_location"))
        country = str(item.get("job_country") or "").upper()
        if country in {"AE", "ARE"} or is_uae_location(location):
            pass
        else:
            # JSearch country=ae should usually filter; still enforce UAE.
            if not is_uae_location(location) and country not in {"AE", "ARE"}:
                return None
            if country in {"AE", "ARE"} and not location:
                location = "United Arab Emirates"

        published = parse_datetime(item.get("job_posted_at_datetime_utc")) or parse_datetime(
            item.get("job_posted_at_timestamp")
        )
        confidence = (
            PublicationTimeConfidence.VERIFIED
            if published is not None
            else PublicationTimeConfidence.UNKNOWN
        )
        url = str(
            item.get("job_apply_link")
            or item.get("job_google_link")
            or item.get("job_offer_expiration_datetime_utc")
            or ""
        ).strip()
        # Prefer apply link; fall back to google link
        if not item.get("job_apply_link") and item.get("job_google_link"):
            url = str(item.get("job_google_link")).strip()
        if not url:
            return None
        salary_raw, lo, hi = salary_from_jsearch(item)
        employer = str(item.get("employer_name") or "Unknown").strip()
        return build_job(
            source=self.name,
            source_job_id=str(item.get("job_id") or url),
            title=title,
            employer=employer,
            location_raw=location or "United Arab Emirates",
            application_url=url,
            published_at=published,
            publication_confidence=confidence,
            description_text=str(item.get("job_description") or "")[:5000] or None,
            salary_raw=salary_raw,
            salary_monthly_aed_min=lo,
            salary_monthly_aed_max=hi,
            raw_provenance={
                "job_id": item.get("job_id"),
                "job_posted_at_datetime_utc": item.get("job_posted_at_datetime_utc"),
                "job_posted_at_timestamp": item.get("job_posted_at_timestamp"),
                "employer_name": employer,
                "publisher": item.get("job_publisher"),
            },
        )
