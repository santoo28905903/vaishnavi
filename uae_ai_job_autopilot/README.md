# UAE AI Job Autopilot

Autonomous UAE AI/ML job discovery, matching, document preparation, tracking, and reporting for **Vaishnavi Santoshi Batchu**.

Resume source of truth: [`data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf`](data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf)

## Status

| Phase | Scope | Status |
|-------|--------|--------|
| 0 | Plan | Complete |
| 1 | Discovery | Complete |
| 2 | Jev + embeddings matching | Complete |
| 3 | Docs, ATS, DB, Sheets, Gmail | **Complete** |
| 4 | GitHub Actions / cloud ops | Not started |
| 5 | Authorized auto-apply | Not started |

## Quick start

```bash
cd uae_ai_job_autopilot
python3 -m pip install -e '.[dev]'

uae-jobs dry-run
uae-jobs discover --summary-only
uae-jobs evaluate --summary-only

# Phase 3
uae-jobs build-master
uae-jobs prepare-docs --jobs-json tests/fixtures/jobs/representative_jobs.json --summary-only
# Optional live Sheets/Gmail:
#   SHEETS_ENABLED=true GOOGLE_SERVICE_ACCOUNT_JSON=... GOOGLE_SHEETS_SPREADSHEET_ID=...
#   GMAIL_ENABLED=true GMAIL_CREDENTIALS_JSON=... uae-jobs prepare-docs --send-email

pytest -m 'not live'
```

## Phase 3 highlights

- Verified master resume JSON (no invented employers/skills)
- Tailored ATS PDFs + cover letters; reparsed ATS score **≥ 80** (40% structure + 60% keywords)
- SQLite + Alembic; idempotent application upserts
- Sheets workbook tabs + Gmail daily report with failure recovery
- **No application submission** (Phase 5)

## Docs

- [`docs/PHASE_PLAN.md`](docs/PHASE_PLAN.md) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/PROGRESS.md`](docs/PROGRESS.md)
- Evidence: [`docs/evidence/`](docs/evidence/)
