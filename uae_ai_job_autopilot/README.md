# UAE AI Job Autopilot

Autonomous UAE AI/ML job discovery → matching → document prep → **authorized apply** → reporting for **Vaishnavi Santoshi Batchu**.

## Status

| Phase | Status |
|-------|--------|
| 1 Discovery | Complete |
| 2 Matching (Jev) | Complete |
| 3 Docs / Sheets / Gmail | Complete |
| 4 Cloud schedule + ops | Complete |
| 5 Authorized apply | **Complete** (mock default; real channels gated) |

## Phase 5 safety

- Allowlist only: `config/application_channels.yaml`
- Default channel: **mock_sandbox** (controlled fixtures)
- Greenhouse/Lever browser adapters exist but are **disabled + unauthorized** until you flip both flags and set `ENABLE_LIVE_SUBMISSION=true`
- CAPTCHA/MFA → `blocked` (never bypassed); uncertain confirmations → `submission_unverified`
- Unsupported boards are skipped honestly — discovery APIs ≠ apply permission

```bash
cd uae_ai_job_autopilot
pip install -e '.[dev]'
# Controlled mock applications (no real employers):
uae-jobs apply --jobs-json tests/fixtures/apply/mock_candidates.json --summary-only
# Dry-run full daily pipeline:
uae-jobs daily --dry-run --summary-only
pytest -m 'not live'
```

## Cloud daily run

- Workflow: [`.github/workflows/uae-job-autopilot-daily.yml`](../.github/workflows/uae-job-autopilot-daily.yml)
- Schedule: **10:00 Asia/Kolkata** + manual **Run workflow**
- Secrets: [`docs/SECRETS.md`](docs/SECRETS.md)
- Keep `ENABLE_LIVE_SUBMISSION=false` until mock tests pass and channels are explicitly authorized
