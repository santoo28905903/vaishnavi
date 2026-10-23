from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from uae_job_autopilot.config import DEFAULT_DATA_DIR, SearchProfile, SourceConfig
from uae_job_autopilot.discovery.adapters.common import require_enabled, skipped_result
from uae_job_autopilot.discovery.base import SourceAdapter
from uae_job_autopilot.discovery.normalize import build_job
from uae_job_autopilot.domain.enums import AccessMode, PublicationTimeConfidence, SourceStatus
from uae_job_autopilot.domain.models import AdapterFetchResult, JobPosting, SourceHealth
from uae_job_autopilot.utils.location import is_uae_location
from uae_job_autopilot.utils.money import parse_salary_to_aed_monthly
from uae_job_autopilot.utils.timeutil import parse_datetime, utcnow

logger = logging.getLogger(__name__)


class AlertIngestionAdapter(SourceAdapter):
    """
    Permitted path for boards without an authorized search API.

    Reads candidate-supplied job-alert exports from:
      data/alerts/<source_name>/*.json

    Each JSON file is either a list of job objects or {"jobs": [...]}.
    Required job fields: title, employer (or company), application_url (or url),
    location. Optional: published_at, source_job_id, description, salary_raw.

    This adapter never scrapes LinkedIn/NaukriGulf/Indeed/Bayt/GulfTalent/Michael Page.
    If the alert directory is missing or empty, status is SKIPPED_NOT_CONFIGURED
    and the source is explicitly reported as not searched for live listings.
    """

    def __init__(self, name: str, *, default_alert_subdir: str | None = None) -> None:
        self.name = name
        self.default_alert_subdir = default_alert_subdir or name

    def fetch(
        self,
        *,
        client: httpx.Client,
        profile: SearchProfile,
        source_cfg: SourceConfig,
        dry_run: bool = False,
    ) -> AdapterFetchResult:
        del client, profile  # alert path is filesystem-only
        skipped = require_enabled(
            source=self.name,
            access_mode=AccessMode.ALERT_INGESTION,
            source_cfg=source_cfg,
        )
        if skipped:
            # Distinguish unsupported scrape vs disabled
            if source_cfg.status and "unsupported" in source_cfg.status:
                return skipped_result(
                    source=self.name,
                    access_mode=AccessMode.UNSUPPORTED,
                    status=SourceStatus.SKIPPED_UNSUPPORTED,
                    detail=source_cfg.detail
                    or "No authorized programmatic search API; use alert exports",
                    source_cfg=source_cfg,
                )
            return skipped

        alert_dir = self._resolve_alert_dir(source_cfg)
        if dry_run:
            now = utcnow()
            n_files = len(list(alert_dir.glob("*.json"))) if alert_dir.exists() else 0
            return AdapterFetchResult(
                health=SourceHealth(
                    source=self.name,
                    access_mode=AccessMode.ALERT_INGESTION,
                    status=SourceStatus.SKIPPED_DISABLED,
                    attempted=False,
                    detail=f"dry_run: would ingest {n_files} JSON alert files from {alert_dir}",
                    started_at=now,
                    finished_at=now,
                ),
                jobs=[],
            )

        if not alert_dir.exists():
            return skipped_result(
                source=self.name,
                access_mode=AccessMode.ALERT_INGESTION,
                status=SourceStatus.SKIPPED_NOT_CONFIGURED,
                detail=(
                    f"Alert directory missing: {alert_dir}. "
                    "No authorized live API for this board; source was not searched. "
                    "Drop job-alert JSON exports here to enable ingestion."
                ),
                source_cfg=source_cfg,
            )

        started = utcnow()
        files = sorted(alert_dir.glob("*.json"))
        if not files:
            return AdapterFetchResult(
                health=SourceHealth(
                    source=self.name,
                    access_mode=AccessMode.ALERT_INGESTION,
                    status=SourceStatus.SKIPPED_NOT_CONFIGURED,
                    attempted=False,
                    detail=(
                        f"No JSON alert files in {alert_dir}; "
                        "source was not searched via live API"
                    ),
                    started_at=started,
                    finished_at=utcnow(),
                ),
                jobs=[],
            )

        jobs: list[JobPosting] = []
        raw_count = 0
        errors: list[str] = []
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                items = self._extract_items(payload)
                raw_count += len(items)
                for idx, item in enumerate(items):
                    job = self._map_item(item, path=path, idx=idx)
                    if job is not None:
                        jobs.append(job)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path.name}: {exc}")
                logger.exception("Failed reading alert file %s", path)

        uae_jobs = [j for j in jobs if j.is_uae]
        if errors and not jobs:
            status = SourceStatus.FAILED
            detail = "; ".join(errors)
        elif not uae_jobs:
            status = SourceStatus.EMPTY
            detail = f"Ingested {len(files)} files; {raw_count} raw; 0 UAE"
        else:
            status = SourceStatus.SUCCESS
            detail = f"Ingested {len(files)} files; {raw_count} raw; {len(uae_jobs)} UAE"

        return AdapterFetchResult(
            health=SourceHealth(
                source=self.name,
                access_mode=AccessMode.ALERT_INGESTION,
                status=status,
                attempted=True,
                jobs_fetched_raw=raw_count,
                jobs_after_uae_filter=len(uae_jobs),
                error="; ".join(errors) if status == SourceStatus.FAILED else None,
                detail=detail,
                started_at=started,
                finished_at=utcnow(),
            ),
            jobs=uae_jobs,
        )

    def _resolve_alert_dir(self, source_cfg: SourceConfig) -> Path:
        if source_cfg.alert_dir:
            p = Path(source_cfg.alert_dir)
            return p if p.is_absolute() else DEFAULT_DATA_DIR.parent / p
        return DEFAULT_DATA_DIR / "alerts" / self.default_alert_subdir

    def _extract_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("jobs"), list):
                return [x for x in payload["jobs"] if isinstance(x, dict)]
            if payload.get("title"):
                return [payload]
        return []

    def _map_item(self, item: dict[str, Any], *, path: Path, idx: int) -> JobPosting | None:
        title = str(item.get("title") or "").strip()
        employer = str(item.get("employer") or item.get("company") or "").strip()
        url = str(item.get("application_url") or item.get("url") or item.get("link") or "").strip()
        location = str(item.get("location") or "").strip()
        if not title or not url:
            return None
        if location and not is_uae_location(location):
            return None
        if not location:
            # Require location for UAE filter honesty
            return None

        published = parse_datetime(item.get("published_at") or item.get("posted_at"))
        if published is not None:
            confidence = PublicationTimeConfidence.VERIFIED
        else:
            confidence = PublicationTimeConfidence.UNKNOWN

        salary_raw = item.get("salary_raw") or item.get("salary")
        lo = hi = None
        if salary_raw:
            lo, hi = parse_salary_to_aed_monthly(str(salary_raw))

        source_job_id = str(item.get("source_job_id") or item.get("id") or f"{path.stem}-{idx}")
        return build_job(
            source=self.name,
            source_job_id=source_job_id,
            title=title,
            employer=employer or self.name,
            location_raw=location,
            application_url=url,
            published_at=published,
            publication_confidence=confidence,
            description_text=str(item.get("description") or "")[:5000] or None,
            salary_raw=str(salary_raw) if salary_raw else None,
            salary_monthly_aed_min=lo,
            salary_monthly_aed_max=hi,
            board_or_site=str(path.name),
            raw_provenance={
                "alert_file": str(path),
                "ingestion": "job_alert_export",
                "original": {k: item.get(k) for k in ("title", "employer", "company", "published_at")},
            },
        )


def linkedin_adapter() -> AlertIngestionAdapter:
    return AlertIngestionAdapter("linkedin_jobs", default_alert_subdir="linkedin_jobs")


def naukrigulf_adapter() -> AlertIngestionAdapter:
    return AlertIngestionAdapter("naukrigulf", default_alert_subdir="naukrigulf")


def indeed_uae_adapter() -> AlertIngestionAdapter:
    return AlertIngestionAdapter("indeed_uae", default_alert_subdir="indeed_uae")


def bayt_adapter() -> AlertIngestionAdapter:
    return AlertIngestionAdapter("bayt", default_alert_subdir="bayt")


def gulftalent_adapter() -> AlertIngestionAdapter:
    return AlertIngestionAdapter("gulftalent", default_alert_subdir="gulftalent")


def michael_page_adapter() -> AlertIngestionAdapter:
    return AlertIngestionAdapter("michael_page", default_alert_subdir="michael_page")
