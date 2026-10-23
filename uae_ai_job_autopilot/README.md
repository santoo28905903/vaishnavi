# UAE AI Job Autopilot

Autonomous UAE AI/ML job discovery → matching → document prep → reporting for **Vaishnavi Santoshi Batchu**.

## Status

| Phase | Status |
|-------|--------|
| 1 Discovery | Complete |
| 2 Matching (Jev) | Complete |
| 3 Docs / Sheets / Gmail | Complete |
| 4 Cloud schedule + ops | **Complete** |
| 5 Auto-apply | Not started |

## Cloud daily run (Phase 4)

- Workflow: [`.github/workflows/uae-job-autopilot-daily.yml`](../.github/workflows/uae-job-autopilot-daily.yml)
- Schedule: **10:00 Asia/Kolkata** daily + manual **Run workflow**
- Requires persistent `DATABASE_URL` (Postgres) — SQLite rejected in cloud
- Secrets: [`docs/SECRETS.md`](docs/SECRETS.md)
- Live application submission is **disabled**

```bash
cd uae_ai_job_autopilot
pip install -e '.[dev]'
uae-jobs daily --dry-run --summary-only
# Production-like (needs Postgres URL):
ENVIRONMENT=cloud DATABASE_URL='postgresql+psycopg://...' uae-jobs daily --summary-only
```

## Local commands

```bash
uae-jobs discover --summary-only
uae-jobs evaluate --summary-only
uae-jobs prepare-docs --summary-only
pytest -m 'not live'
```
