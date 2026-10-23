from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from uae_job_autopilot.config import (
    DEFAULT_DATA_DIR,
    SearchProfile,
    SourcesConfig,
    load_search_profile,
    load_sources_config,
)
from uae_job_autopilot.discovery.dedupe import deduplicate
from uae_job_autopilot.discovery.freshness import partition_by_freshness
from uae_job_autopilot.discovery.registry import build_adapter_registry, iter_configured_sources
from uae_job_autopilot.domain.enums import AccessMode, SourceStatus
from uae_job_autopilot.domain.models import (
    DiscoveryReport,
    DiscoveryStats,
    JobPosting,
    SourceHealth,
)
from uae_job_autopilot.utils.http import make_client
from uae_job_autopilot.utils.timeutil import utcnow

logger = logging.getLogger(__name__)


class DiscoveryOrchestrator:
    def __init__(
        self,
        *,
        profile: SearchProfile | None = None,
        sources: SourcesConfig | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.profile = profile or load_search_profile()
        self.sources = sources or load_sources_config()
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.registry = build_adapter_registry()

    def run(self, *, dry_run: bool = False) -> DiscoveryReport:
        run_id = utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        started = utcnow()
        health_rows: list[SourceHealth] = []
        collected: list[JobPosting] = []
        notes: list[str] = []

        configured = iter_configured_sources(self.sources)
        stats = DiscoveryStats(sources_configured=len(configured))

        with make_client(
            timeout=float(self.sources.defaults.get("timeout_seconds") or 30)
        ) as client:
            for name, cfg, category in configured:
                adapter = self.registry.get(name)
                if adapter is None:
                    now = utcnow()
                    if not cfg.enabled:
                        # Disabled + unimplemented: record quietly, do not claim searched.
                        health_rows.append(
                            SourceHealth(
                                source=name,
                                access_mode=AccessMode.UNSUPPORTED,
                                status=SourceStatus.SKIPPED_DISABLED,
                                attempted=False,
                                detail=f"Disabled; no Phase 1 adapter for {name}",
                                started_at=now,
                                finished_at=now,
                            )
                        )
                        stats.sources_skipped += 1
                        continue
                    health_rows.append(
                        SourceHealth(
                            source=name,
                            access_mode=AccessMode.UNSUPPORTED,
                            status=SourceStatus.SKIPPED_UNSUPPORTED,
                            attempted=False,
                            detail=f"Enabled but no adapter registered for {name} ({category})",
                            started_at=now,
                            finished_at=now,
                        )
                    )
                    stats.sources_skipped += 1
                    notes.append(f"{name}: no adapter — not searched")
                    continue

                logger.info("Running source adapter %s (enabled=%s)", name, cfg.enabled)
                result = adapter.fetch(
                    client=client,
                    profile=self.profile,
                    source_cfg=cfg,
                    dry_run=dry_run,
                )
                # Fill freshness count at adapter level when possible
                fresh_adapter, _ = partition_by_freshness(
                    result.jobs,
                    now=started,
                    window_hours=self.profile.freshness_window_hours,
                )
                result.health.jobs_after_freshness = len(fresh_adapter)
                health_rows.append(result.health)

                if result.health.attempted:
                    stats.sources_attempted += 1
                    stats.jobs_raw += result.health.jobs_fetched_raw
                    stats.jobs_uae += result.health.jobs_after_uae_filter
                    collected.extend(result.jobs)
                    if result.health.status in {
                        SourceStatus.SUCCESS,
                        SourceStatus.EMPTY,
                    }:
                        stats.sources_success += 1
                    elif result.health.status in {
                        SourceStatus.FAILED,
                        SourceStatus.QUOTA_EXHAUSTED,
                    }:
                        stats.sources_failed += 1
                else:
                    stats.sources_skipped += 1
                    notes.append(
                        f"{name}: not searched ({result.health.status}) — {result.health.detail}"
                    )

        unique, dupes = deduplicate(collected)
        stats.jobs_duplicates_removed = dupes

        fresh, excluded = partition_by_freshness(
            unique,
            now=started,
            window_hours=self.profile.freshness_window_hours,
        )
        stats.jobs_fresh = len(fresh)
        stats.jobs_excluded_stale_or_unverifiable = len(excluded)

        # Prefer priority employers, then newest published_at
        priority = {e.lower() for e in self.profile.priority_employers}

        def sort_key(job: JobPosting) -> tuple:
            emp = job.employer.lower()
            pri = 0 if any(p in emp or emp in p for p in priority) else 1
            published = job.published_at or started
            return (pri, -published.timestamp())

        fresh_sorted = sorted(fresh, key=sort_key)
        selected = fresh_sorted[: self.profile.evaluation_cap]
        stats.jobs_selected_for_evaluation = len(selected)
        stats.jobs_additionally_discovered = max(0, len(fresh_sorted) - len(selected)) + len(
            excluded
        )

        finished = utcnow()
        report = DiscoveryReport(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            dry_run=dry_run,
            window_hours=self.profile.freshness_window_hours,
            evaluation_cap=self.profile.evaluation_cap,
            stats=stats,
            source_health=health_rows,
            selected_jobs=selected,
            all_fresh_unique_jobs=fresh_sorted,
            notes=notes,
        )
        self._persist_report(report)
        return report

    def _persist_report(self, report: DiscoveryReport) -> Path:
        out_dir = self.data_dir / "runs"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{report.run_id}.json"
        path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        # Compact summary for quick inspection
        summary = {
            "run_id": report.run_id,
            "dry_run": report.dry_run,
            "stats": report.stats.model_dump(),
            "sources_queried": [
                {"source": h.source, "status": h.status, "detail": h.detail}
                for h in report.sources_queried()
            ],
            "sources_unavailable": [
                {"source": h.source, "status": h.status, "detail": h.detail}
                for h in report.sources_unavailable()
            ],
            "selected_job_links": [
                {
                    "title": j.title,
                    "employer": j.employer,
                    "location": j.location_raw,
                    "url": j.application_url,
                    "published_at": j.published_at.isoformat() if j.published_at else None,
                    "source": j.source,
                }
                for j in report.selected_jobs
            ],
            "notes": report.notes,
        }
        summary_path = out_dir / f"{report.run_id}.summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.info("Wrote discovery report %s", path)
        return path
