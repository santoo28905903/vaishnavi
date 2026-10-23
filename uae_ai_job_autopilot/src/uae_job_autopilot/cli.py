from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from uae_job_autopilot.config import DEFAULT_DATA_DIR, get_settings
from uae_job_autopilot.discovery.orchestrator import DiscoveryOrchestrator
from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.logging_setup import setup_logging
from uae_job_autopilot.matching.pipeline import MatchingPipeline
from uae_job_autopilot.utils.timeutil import utcnow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uae-jobs",
        description="UAE AI Job Autopilot — discovery + matching + documents CLI",
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

    ev = sub.add_parser(
        "evaluate",
        help="Phase 2: match jobs (fixtures or discovery selection) with Jev + embeddings",
    )
    ev.add_argument(
        "--jobs-json",
        type=str,
        default=None,
        help="Path to JSON list of JobPosting objects (or {jobs:[...]})",
    )
    ev.add_argument(
        "--from-discovery",
        type=str,
        default=None,
        help="Path to discovery run JSON; uses selected_jobs",
    )
    ev.add_argument("--dry-run", action="store_true", help="Do not call models")
    ev.add_argument("--json", action="store_true", help="Print full JSON report")
    ev.add_argument("--summary-only", action="store_true")

    sub.add_parser("build-master", help="Phase 3: build verified editable master resume JSON")

    prep = sub.add_parser(
        "prepare-docs",
        help="Phase 3: tailored resume/cover PDFs, ATS score, DB + Sheets sync",
    )
    prep.add_argument("--jobs-json", type=str, default=None)
    prep.add_argument("--from-discovery", type=str, default=None)
    prep.add_argument("--send-email", action="store_true")
    prep.add_argument("--no-sheets", action="store_true")
    prep.add_argument("--json", action="store_true")
    prep.add_argument("--summary-only", action="store_true")

    daily = sub.add_parser(
        "daily",
        help="Phase 4–5: discover→evaluate→docs→apply→report with locks/checkpoints",
    )
    daily.add_argument("--dry-run", action="store_true")
    daily.add_argument("--resume-run-id", type=str, default=None)
    daily.add_argument("--skip-lock", action="store_true")
    daily.add_argument("--json", action="store_true")
    daily.add_argument("--summary-only", action="store_true")

    apply_cmd = sub.add_parser(
        "apply",
        help="Phase 5: allowlisted apply (mock sandbox by default; real channels gated)",
    )
    apply_cmd.add_argument(
        "--jobs-json",
        type=str,
        required=True,
        help="JSON list of apply candidates {job, resume_pdf, cover_pdf, ats_passed, scenario?}",
    )
    apply_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Never submit; record dry_run outcomes",
    )
    apply_cmd.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Force mock scenario: success|captcha|mfa|unverified",
    )
    apply_cmd.add_argument("--no-sheets", action="store_true")
    apply_cmd.add_argument("--json", action="store_true")
    apply_cmd.add_argument("--summary-only", action="store_true")
    return parser


def _print_discovery(report) -> None:
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


def _print_evaluation(report) -> None:
    console = Console()
    console.print(
        f"[bold]Match run[/bold] {report.run_id}  jev_configured={report.jev_configured}"
    )
    s = report.stats
    console.print(
        f"input={s.jobs_input} blocked={s.hard_blocked} "
        f"resume_pass={s.resume_pass} visa_pass={s.visa_pass} "
        f"match_pass={s.match_pass} needs_model={s.needs_model} "
        f"cost_usd={s.total_cost_usd}"
    )
    table = Table(title="Job decisions")
    table.add_column("Title")
    table.add_column("Decision")
    table.add_column("Resume")
    table.add_column("Visa")
    table.add_column("Sponsor")
    for r in report.results:
        table.add_row(
            r.job.title[:36],
            str(r.decision),
            f"{r.resume_fit.combined_score:.1f}" if r.resume_fit else "—",
            f"{r.visa.combined_score:.1f}" if r.visa else "—",
            (
                f"{r.visa.sponsorship_label}"
                + ("*" if r.visa and r.visa.sponsorship_confirmed else "")
            )
            if r.visa
            else "—",
        )
    console.print(table)
    console.print("[dim]* sponsorship_confirmed[/dim]")


def _load_jobs_for_eval(args) -> list[JobPosting]:
    if args.jobs_json:
        path = Path(args.jobs_json)
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data["jobs"] if isinstance(data, dict) and "jobs" in data else data
        return [JobPosting.model_validate(x) for x in items]
    if args.from_discovery:
        path = Path(args.from_discovery)
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("selected_jobs") or data.get("all_fresh_unique_jobs") or []
        return [JobPosting.model_validate(x) for x in items]
    # Default: representative fixtures
    fixture = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "jobs"
        / "representative_jobs.json"
    )
    if fixture.exists():
        data = json.loads(fixture.read_text(encoding="utf-8"))
        return [JobPosting.model_validate(x) for x in data["jobs"]]
    raise SystemExit(
        "No jobs provided. Use --jobs-json, --from-discovery, or ship fixtures."
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    setup_logging(settings.log_level)

    if args.command in {"dry-run", "discover"}:
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
            _print_discovery(report)
        return 0

    if args.command == "evaluate":
        jobs = _load_jobs_for_eval(args)
        # Ensure discovered_at present
        now = utcnow()
        for j in jobs:
            if not j.discovered_at:
                j.discovered_at = now
        pipeline = MatchingPipeline()
        report = pipeline.evaluate_jobs(jobs, dry_run=bool(args.dry_run))
        if args.summary_only:
            print(
                json.dumps(
                    {
                        "run_id": report.run_id,
                        "stats": report.stats.model_dump(),
                        "jev_configured": report.jev_configured,
                        "passes": len(report.passes()),
                        "notes": report.notes,
                    },
                    indent=2,
                )
            )
            return 0
        if args.json:
            print(report.model_dump_json(indent=2))
        else:
            _print_evaluation(report)
        return 0

    if args.command == "build-master":
        from uae_job_autopilot.documents.master import build_master_resume

        master = build_master_resume(persist=True)
        print(
            json.dumps(
                {
                    "full_name": master.full_name,
                    "skills": master.skills,
                    "experience_roles": len(master.experience),
                    "certifications": master.certifications,
                    "version": master.version,
                    "path": "data/resume/master_resume.json",
                },
                indent=2,
            )
        )
        return 0

    if args.command == "prepare-docs":
        from uae_job_autopilot.documents.pipeline import Phase3Pipeline

        jobs = _load_jobs_for_eval(args)
        now = utcnow()
        for j in jobs:
            if not j.discovered_at:
                j.discovered_at = now
        # Only generate docs for the strong AI fit fixture / non-blocked jobs when using full fixture set
        # Callers can pass a filtered jobs JSON; default uses representative jobs and prepares all.
        p3 = Phase3Pipeline(settings=settings)
        report = p3.prepare_for_jobs(
            jobs,
            send_email=bool(args.send_email),
            sync_sheets=not bool(args.no_sheets),
        )
        payload = {
            "run_id": report.run_id,
            "stats": report.stats,
            "failures": report.failures,
            "documents": [
                {
                    "job_key": d.job_key,
                    "ats": d.ats.combined_score,
                    "ats_passed": d.ats.passed,
                    "integrity_ok": d.integrity_ok,
                    "resume_pdf": d.resume_pdf,
                    "cover_pdf": d.cover_pdf,
                    "provider": d.generator_provider,
                }
                for d in report.documents
            ],
            "email_status": report.stats.get("email_status"),
            "sheets_ok": report.stats.get("sheets_ok"),
        }
        if args.summary_only or args.json:
            print(json.dumps(payload, indent=2))
        else:
            console = Console()
            console.print(f"[bold]Phase 3[/bold] {report.run_id}")
            console.print(json.dumps(report.stats, indent=2))
            for d in report.documents:
                console.print(
                    f"- ATS {d.ats.combined_score:.1f} "
                    f"{'PASS' if d.ats.passed else 'FAIL'} "
                    f"{d.resume_pdf}"
                )
        return 0

    if args.command == "daily":
        from uae_job_autopilot.ops.daily_pipeline import DailyPipeline

        pipeline = DailyPipeline(settings=settings)
        result = pipeline.run(
            dry_run=bool(args.dry_run),
            resume_run_id=args.resume_run_id or None,
            skip_lock=bool(args.skip_lock),
        )
        payload = result.to_dict()
        if args.summary_only:
            print(
                json.dumps(
                    {
                        "run_id": result.run_id,
                        "ok": result.ok,
                        "cost_usd": result.cost_usd,
                        "stages": {k: v.get("status") for k, v in result.stages.items()},
                        "failures": result.failures,
                        "notes": result.notes,
                        "submission_enabled": result.submission_enabled,
                        "skipped_due_to_lock": result.skipped_due_to_lock,
                    },
                    indent=2,
                )
            )
        elif args.json:
            print(json.dumps(payload, indent=2))
        else:
            console = Console()
            console.print(f"[bold]Daily[/bold] {result.run_id} ok={result.ok}")
            console.print(json.dumps(payload, indent=2)[:4000])
        return 0 if result.ok or result.skipped_due_to_lock or args.dry_run else 1

    if args.command == "apply":
        from uae_job_autopilot.apply.orchestrator import ApplyOrchestrator

        path = Path(args.jobs_json)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "candidates" in raw:
            candidates = raw["candidates"]
        elif isinstance(raw, list):
            candidates = raw
        else:
            candidates = [raw]
        # Ensure mock fixture runs have placeholder PDFs when paths omitted
        stub_dir = DEFAULT_DATA_DIR / "tmp" / "apply_stubs"
        stub_dir.mkdir(parents=True, exist_ok=True)
        stub_resume = stub_dir / "stub_resume.pdf"
        stub_cover = stub_dir / "stub_cover.pdf"
        minimal_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
        if not stub_resume.exists():
            stub_resume.write_bytes(minimal_pdf)
        if not stub_cover.exists():
            stub_cover.write_bytes(minimal_pdf)
        normalized = []
        for c in candidates:
            if not isinstance(c, dict):
                normalized.append(c)
                continue
            item = dict(c)
            item.setdefault("resume_pdf", str(stub_resume))
            item.setdefault("cover_pdf", str(stub_cover))
            item.setdefault("ats_passed", True)
            normalized.append(item)
        orch = ApplyOrchestrator(settings=settings)
        report = orch.run(
            normalized,
            dry_run=bool(args.dry_run),
            sync_sheets=not bool(args.no_sheets),
            force_scenario=args.scenario,
        )
        payload = {
            "run_id": report.run_id,
            "stats": report.stats.model_dump(),
            "live_submission_enabled": report.live_submission_enabled,
            "attempts": [
                {
                    "application_key": a.application_key,
                    "channel_id": a.channel_id,
                    "outcome": str(a.outcome),
                    "status": str(a.status),
                    "confirmation_verified": a.confirmation_verified,
                    "confirmation_reference": a.confirmation_reference,
                    "block_reason": a.block_reason,
                    "notes": a.notes,
                }
                for a in report.attempts
            ],
            "notes": report.notes,
            "failures": report.failures,
        }
        if args.summary_only or args.json:
            print(json.dumps(payload, indent=2))
        else:
            console = Console()
            console.print(f"[bold]Apply[/bold] {report.run_id}")
            console.print(json.dumps(report.stats.model_dump(), indent=2))
            for a in report.attempts:
                console.print(
                    f"- {a.channel_id} {a.outcome} confirmed={a.confirmation_verified} "
                    f"{a.block_reason or ''}"
                )
        return 0 if not report.failures else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
