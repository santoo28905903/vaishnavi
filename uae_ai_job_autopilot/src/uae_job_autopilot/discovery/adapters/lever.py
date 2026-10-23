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

LEVER_URL = "https://api.lever.co/v0/postings/{site}?mode=json"


class LeverAdapter(SourceAdapter):
    name = "lever"

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

        sites = source_cfg.sites or source_cfg.boards or []
        if not sites:
            return skipped_result(
                source=self.name,
                access_mode=AccessMode.PUBLIC_API,
                status=SourceStatus.SKIPPED_NOT_CONFIGURED,
                detail="No Lever site tokens configured",
            )

        if dry_run:
            now = utcnow()
            return AdapterFetchResult(
                health=SourceHealth(
                    source=self.name,
                    access_mode=AccessMode.PUBLIC_API,
                    status=SourceStatus.SKIPPED_DISABLED,
                    attempted=False,
                    detail=f"dry_run: would query {len(sites)} Lever sites",
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
        sites_ok = 0

        for site in sites:
            url = LEVER_URL.format(site=site)
            try:
                status, payload = get_json(client, url)
                last_status = status
                if status != 200 or not isinstance(payload, list):
                    errors.append(f"{site}: HTTP {status}")
                    continue
                sites_ok += 1
                raw_count += len(payload)
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    job = self._map_job(item, site=site, profile=profile)
                    if job is not None:
                        jobs.append(job)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{site}: {exc}")
                logger.exception("Lever site %s failed", site)

        finished = utcnow()
        uae_jobs = [j for j in jobs if j.is_uae]
        if sites_ok == 0:
            status = SourceStatus.FAILED
            detail = "; ".join(errors) or "All Lever sites failed"
        elif not uae_jobs:
            status = SourceStatus.EMPTY
            detail = f"Queried {sites_ok}/{len(sites)} sites; {raw_count} raw; 0 UAE"
        else:
            status = SourceStatus.SUCCESS
            detail = f"Queried {sites_ok}/{len(sites)} sites; {raw_count} raw; {len(uae_jobs)} UAE"

        return AdapterFetchResult(
            health=SourceHealth(
                source=self.name,
                access_mode=AccessMode.PUBLIC_API,
                status=status,
                attempted=True,
                jobs_fetched_raw=raw_count,
                jobs_after_uae_filter=len(uae_jobs),
                error="; ".join(errors) if status == SourceStatus.FAILED else None,
                detail=detail + (f"; partial errors: {'; '.join(errors)}" if errors and status != SourceStatus.FAILED else ""),
                started_at=started,
                finished_at=finished,
                http_status=last_status,
            ),
            jobs=uae_jobs,
        )

    def _map_job(
        self, item: dict[str, Any], *, site: str, profile: SearchProfile
    ) -> JobPosting | None:
        title = str(item.get("text") or "").strip()
        if not title:
            return None
        cats = item.get("categories") or {}
        location = ""
        if isinstance(cats, dict):
            location = str(cats.get("location") or "")
            all_locs = cats.get("allLocations") or []
            if all_locs and isinstance(all_locs, list):
                location = ", ".join(str(x) for x in all_locs)
        if not location:
            location = str(item.get("country") or "")
        if not is_uae_location(location):
            return None
        if profile.title_keywords and not title_matches_profile(title, profile.title_keywords):
            return None

        published = parse_datetime(item.get("createdAt"))
        confidence = (
            PublicationTimeConfidence.VERIFIED
            if published is not None
            else PublicationTimeConfidence.UNKNOWN
        )
        url = str(item.get("hostedUrl") or item.get("applyUrl") or "").strip()
        if not url:
            return None
        desc = item.get("descriptionPlain") or item.get("description")
        return build_job(
            source=self.name,
            source_job_id=str(item.get("id")),
            title=title,
            employer=site,
            location_raw=location,
            application_url=url,
            published_at=published,
            publication_confidence=confidence,
            description_text=str(desc)[:5000] if desc else None,
            board_or_site=site,
            raw_provenance={
                "site": site,
                "lever_id": item.get("id"),
                "createdAt": item.get("createdAt"),
                "categories": cats,
            },
        )
