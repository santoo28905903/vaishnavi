from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.table import Table

from uae_job_autopilot.config import get_settings
from uae_job_autopilot.discovery.orchestrator import DiscoveryOrchestrator
from uae_job_autopilot.logging_setup import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uae-jobs",
        description="UAE AI Job Autopilot — Phase 1 discovery CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dry = sub.add_parser("dry-run", help="Plan source calls without hitting live APIs / alerts")
    dry.add_argument("--json", action="store_true", help="Print full JSON report")

    run = sub.add_parser("discover", help="Run multi-source discovery once")
    run.add_argument("--json", action="store_true", help="Print full JSON report")
    run.add_argument(
        "--summary-only",
        action="store_true",
        help="Print compact summary JSON only",
    )
    return parser


def _print_human(report) -> None:
    console = Console()
    console.print(f"[bold]Run[/bold] {report.run_id}  dry_run={report.dry_run}")
    console.print(
        f"Sources configured={report.stats.sources_configured} "
        f"attempted={report.stats.sources_attempted} "
        f"success={report.stats.sources_success} "
        f"failed={report.stats.sources_failed} "
        f"skipped={report.stats.sources_skipped}"
    )
    console.print(
        f"Jobs raw={report.stats.jobs_raw} uae={report.stats.jobs_uae} "
        f"fresh={report.stats.jobs_fresh} selected={report.stats.jobs_selected_for_evaluation} "
        f"dupes_removed={report.stats.jobs_duplicates_removed}"
    )

    table = Table(title="Source health")
    table.add_column("Source")
    table.add_column("Attempted")
    table.add_column("Status")
    table.add_column("Raw")
    table.add_column("UAE")
    table.add_column("Detail")
    for h in report.source_health:
        table.add_row(
            h.source,
            "yes" if h.attempted else "no",
            str(h.status),
            str(h.jobs_fetched_raw),
            str(h.jobs_after_uae_filter),
            (h.detail or h.error or "")[:80],
        )
    console.print(table)

    if report.selected_jobs:
        jobs_table = Table(title="Selected verified-fresh jobs (cap)")
        jobs_table.add_column("Title")
        jobs_table.add_column("Employer")
        jobs_table.add_column("Location")
        jobs_table.add_column("Source")
        jobs_table.add_column("Published")
        for j in report.selected_jobs[:20]:
            jobs_table.add_row(
                j.title[:40],
                j.employer[:24],
                j.location_raw[:28],
                j.source,
                j.published_at.isoformat() if j.published_at else "—",
            )
        console.print(jobs_table)
    else:
        if report.stats.sources_attempted == 0:
            console.print(
                "[yellow]Job discovery unavailable or not attempted "
                "(distinct from zero jobs found).[/yellow]"
            )
        else:
            console.print("[yellow]Zero verified-fresh UAE jobs selected this run.[/yellow]")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    setup_logging(settings.log_level)

    dry_run = args.command == "dry-run"
    orchestrator = DiscoveryOrchestrator()
    report = orchestrator.run(dry_run=dry_run)

    if getattr(args, "summary_only", False):
        summary = {
            "run_id": report.run_id,
            "dry_run": report.dry_run,
            "stats": report.stats.model_dump(),
            "sources_queried": [h.source for h in report.sources_queried()],
            "sources_unavailable": [
                {"source": h.source, "status": h.status, "detail": h.detail}
                for h in report.sources_unavailable()
            ],
            "selected_count": len(report.selected_jobs),
            "selected_links": [j.application_url for j in report.selected_jobs],
            "notes": report.notes,
        }
        print(json.dumps(summary, indent=2))
        return 0

    if getattr(args, "json", False):
        print(report.model_dump_json(indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
