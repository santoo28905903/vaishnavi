from __future__ import annotations

import logging
from typing import Any

import httpx

from uae_job_autopilot.config import SearchProfile, SourceConfig
from uae_job_autopilot.discovery.adapters.common import require_enabled, skipped_result
from uae_job_autopilot.discovery.base import SourceAdapter
from uae_job_autopilot.discovery.normalize import build_job, title_matches_profile
from uae_job_autopilot.domain.enums import AccessMode, PublicationTimeConfidence, SourceStatus
from uae_job_autopilot.domain.models import AdapterFetchResult, JobPosting, SourceHealth
from uae_job_autopilot.utils.http import get_json
from uae_job_autopilot.utils.location import is_uae_location
from uae_job_autopilot.utils.timeutil import parse_datetime, utcnow

logger = logging.getLogger(__name__)

ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{board}"


class AshbyAdapter(SourceAdapter):
    name = "ashby"

    def fetch(
        self,
        *,
        client: httpx.Client,
        profile: SearchProfile,
        source_cfg: SourceConfig,
        dry_run: bool = False,
    ) -> AdapterFetchResult:
        skipped = require_enabled(
            source=self.name, access_mode=AccessMode.PUBLIC_API, source_cfg=source_cfg
        )
        if skipped:
            return skipped

        boards = source_cfg.boards or []
        if not boards:
            return skipped_result(
                source=self.name,
                access_mode=AccessMode.PUBLIC_API,
                status=SourceStatus.SKIPPED_NOT_CONFIGURED,
                detail="No Ashby board names configured",
            )

        if dry_run:
            now = utcnow()
            return AdapterFetchResult(
                health=SourceHealth(
                    source=self.name,
                    access_mode=AccessMode.PUBLIC_API,
                    status=SourceStatus.SKIPPED_DISABLED,
                    attempted=False,
                    detail=f"dry_run: would query {len(boards)} Ashby boards",
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
            url = ASHBY_URL.format(board=board)
            try:
                status, payload = get_json(client, url)
                last_status = status
                if status != 200 or not isinstance(payload, dict):
                    errors.append(f"{board}: HTTP {status}")
                    continue
                board_jobs = payload.get("jobs") or []
                if not isinstance(board_jobs, list):
                    errors.append(f"{board}: unexpected payload")
                    continue
                boards_ok += 1
                raw_count += len(board_jobs)
                for item in board_jobs:
                    if not isinstance(item, dict):
                        continue
                    job = self._map_job(item, board=board, profile=profile)
                    if job is not None:
                        jobs.append(job)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{board}: {exc}")
                logger.exception("Ashby board %s failed", board)

        finished = utcnow()
        uae_jobs = [j for j in jobs if j.is_uae]
        if boards_ok == 0:
            status = SourceStatus.FAILED
            detail = "; ".join(errors) or "All Ashby boards failed"
        elif not uae_jobs:
            status = SourceStatus.EMPTY
            detail = f"Queried {boards_ok}/{len(boards)} boards; {raw_count} raw; 0 UAE"
        else:
            status = SourceStatus.SUCCESS
            detail = f"Queried {boards_ok}/{len(boards)} boards; {raw_count} raw; {len(uae_jobs)} UAE"

        return AdapterFetchResult(
            health=SourceHealth(
                source=self.name,
                access_mode=AccessMode.PUBLIC_API,
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

    def _map_job(
        self, item: dict[str, Any], *, board: str, profile: SearchProfile
    ) -> JobPosting | None:
        if item.get("isListed") is False:
            return None
        title = str(item.get("title") or "").strip()
        if not title:
            return None
        location = str(item.get("location") or "")
        secondary = item.get("secondaryLocations") or []
        if secondary and isinstance(secondary, list):
            extra = []
            for s in secondary:
                if isinstance(s, dict):
                    extra.append(str(s.get("location") or s.get("name") or ""))
                else:
                    extra.append(str(s))
            location = ", ".join(x for x in [location, *extra] if x)
        if not is_uae_location(location):
            return None
        if profile.title_keywords and not title_matches_profile(title, profile.title_keywords):
            return None

        published = parse_datetime(item.get("publishedAt"))
        confidence = (
            PublicationTimeConfidence.VERIFIED
            if published is not None
            else PublicationTimeConfidence.UNKNOWN
        )
        url = str(item.get("jobUrl") or item.get("applyUrl") or "").strip()
        if not url:
            return None
        desc = item.get("descriptionPlain")
        return build_job(
            source=self.name,
            source_job_id=str(item.get("id")),
            title=title,
            employer=board,
            location_raw=location,
            application_url=url,
            published_at=published,
            publication_confidence=confidence,
            description_text=str(desc)[:5000] if desc else None,
            board_or_site=board,
            raw_provenance={
                "board": board,
                "ashby_id": item.get("id"),
                "publishedAt": item.get("publishedAt"),
                "department": item.get("department"),
                "isRemote": item.get("isRemote"),
            },
        )
