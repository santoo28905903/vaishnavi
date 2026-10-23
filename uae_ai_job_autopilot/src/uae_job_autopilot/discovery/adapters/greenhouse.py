from __future__ import annotations

import logging
from typing import Any

import httpx

from uae_job_autopilot.config import SearchProfile, SourceConfig
from uae_job_autopilot.discovery.adapters.common import require_enabled
from uae_job_autopilot.discovery.base import SourceAdapter
from uae_job_autopilot.discovery.normalize import build_job, title_matches_profile
from uae_job_autopilot.domain.enums import AccessMode, PublicationTimeConfidence, SourceStatus
from uae_job_autopilot.domain.models import AdapterFetchResult, JobPosting, SourceHealth
from uae_job_autopilot.utils.http import get_json
from uae_job_autopilot.utils.location import is_uae_location
from uae_job_autopilot.utils.timeutil import parse_datetime, utcnow

logger = logging.getLogger(__name__)

GH_JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


class GreenhouseAdapter(SourceAdapter):
    name = "greenhouse"

    def fetch(
        self,
        *,
        client: httpx.Client,
        profile: SearchProfile,
        source_cfg: SourceConfig,
        dry_run: bool = False,
    ) -> AdapterFetchResult:
        skipped = require_enabled(
            source=self.name,
            access_mode=AccessMode.PUBLIC_API,
            source_cfg=source_cfg,
        )
        if skipped:
            return skipped

        boards = source_cfg.boards or []
        if not boards:
            return require_enabled(
                source=self.name,
                access_mode=AccessMode.PUBLIC_API,
                source_cfg=SourceConfig(enabled=False),
            ) or AdapterFetchResult(
                health=SourceHealth(
                    source=self.name,
                    access_mode=AccessMode.PUBLIC_API,
                    status=SourceStatus.SKIPPED_NOT_CONFIGURED,
                    attempted=False,
                    detail="No Greenhouse board tokens configured",
                    started_at=utcnow(),
                    finished_at=utcnow(),
                ),
                jobs=[],
            )

        if dry_run:
            now = utcnow()
            return AdapterFetchResult(
                health=SourceHealth(
                    source=self.name,
                    access_mode=AccessMode.PUBLIC_API,
                    status=SourceStatus.SKIPPED_DISABLED,
                    attempted=False,
                    detail=f"dry_run: would query {len(boards)} Greenhouse boards",
                    started_at=now,
                    finished_at=now,
                ),
                jobs=[],
            )

        started = utcnow()
        jobs: list[JobPosting] = []
        raw_count = 0
        errors: list[str] = []
        last_status: int | None = None
        boards_ok = 0

        for board in boards:
            url = GH_JOBS_URL.format(board=board)
            try:
                status, payload = get_json(client, url)
                last_status = status
                if status != 200:
                    errors.append(f"{board}: HTTP {status}")
                    logger.warning("Greenhouse board %s HTTP %s", board, status)
                    continue
                board_jobs = []
                if isinstance(payload, dict):
                    board_jobs = payload.get("jobs") or []
                if not isinstance(board_jobs, list):
                    errors.append(f"{board}: unexpected payload")
                    continue
                boards_ok += 1
                raw_count += len(board_jobs)
                for item in board_jobs:
                    job = self._map_job(item, board=board, profile=profile)
                    if job is not None:
                        jobs.append(job)
            except Exception as exc:  # noqa: BLE001 — surface in source health
                errors.append(f"{board}: {exc}")
                logger.exception("Greenhouse board %s failed", board)

        finished = utcnow()
        uae_jobs = [j for j in jobs if j.is_uae]
        if boards_ok == 0:
            status = SourceStatus.FAILED
            detail = "; ".join(errors) or "All Greenhouse boards failed"
        elif not uae_jobs:
            status = SourceStatus.EMPTY
            detail = (
                f"Queried {boards_ok}/{len(boards)} boards; "
                f"{raw_count} raw jobs; 0 UAE after filters"
                + (f"; partial errors: {'; '.join(errors)}" if errors else "")
            )
        else:
            status = SourceStatus.SUCCESS
            detail = (
                f"Queried {boards_ok}/{len(boards)} boards; "
                f"{raw_count} raw; {len(uae_jobs)} UAE AI/ML candidates"
                + (f"; partial errors: {'; '.join(errors)}" if errors else "")
            )

        return AdapterFetchResult(
            health=SourceHealth(
                source=self.name,
                access_mode=AccessMode.PUBLIC_API,
                status=status,
                attempted=True,
                jobs_fetched_raw=raw_count,
                jobs_after_uae_filter=len(uae_jobs),
                error="; ".join(errors) if status == SourceStatus.FAILED else None,
                detail=detail,
                started_at=started,
                finished_at=finished,
                http_status=last_status,
            ),
            jobs=uae_jobs,
        )

    def _map_job(
        self, item: dict[str, Any], *, board: str, profile: SearchProfile
    ) -> JobPosting | None:
        title = str(item.get("title") or "").strip()
        if not title:
            return None
        loc_obj = item.get("location") or {}
        location = loc_obj.get("name") if isinstance(loc_obj, dict) else str(loc_obj or "")
        if not is_uae_location(location):
            return None
        if profile.title_keywords and not title_matches_profile(title, profile.title_keywords):
            # Keep UAE jobs that clearly match; drop unrelated UAE roles on large boards.
            return None

        published = parse_datetime(item.get("first_published")) or parse_datetime(
            item.get("updated_at")
        )
        confidence = (
            PublicationTimeConfidence.VERIFIED
            if published is not None
            else PublicationTimeConfidence.UNKNOWN
        )
        # Prefer first_published as publication; if only updated_at, mark unverified.
        if item.get("first_published"):
            published = parse_datetime(item.get("first_published"))
            confidence = PublicationTimeConfidence.VERIFIED
        elif item.get("updated_at"):
            published = parse_datetime(item.get("updated_at"))
            confidence = PublicationTimeConfidence.UNVERIFIED

        employer = str(item.get("company_name") or board).strip()
        url = str(item.get("absolute_url") or "").strip()
        if not url:
            return None
        return build_job(
            source=self.name,
            source_job_id=str(item.get("id")),
            title=title,
            employer=employer,
            location_raw=location,
            application_url=url,
            published_at=published,
            publication_confidence=confidence,
            updated_at_source=parse_datetime(item.get("updated_at")),
            board_or_site=board,
            raw_provenance={
                "board": board,
                "greenhouse_id": item.get("id"),
                "first_published": item.get("first_published"),
                "updated_at": item.get("updated_at"),
                "requisition_id": item.get("requisition_id"),
            },
        )
