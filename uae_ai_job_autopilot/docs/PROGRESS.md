# Progress checklist

Last updated: 24 Oct 2026, Asia/Kolkata.

## Phase 0–3

- [x] Complete

## Phase 4 — Cloud deployment

- [x] GitHub Actions schedule `0 10 * * *` + `timezone: Asia/Kolkata`
- [x] `workflow_dispatch` (dry_run / resume_run_id inputs)
- [x] Persistent DB policy — reject SQLite in cloud; Postgres via `DATABASE_URL`
- [x] Secrets documented (`docs/SECRETS.md`)
- [x] Concurrency locks (`run_locks`) + Actions `concurrency` group
- [x] Stage checkpoints (`run_checkpoints`) for resumable runs
- [x] Retries (tenacity) on discover/evaluate/prepare_docs
- [x] Daily cost cap (`DAILY_COST_CAP_USD`)
- [x] Cloud model routing — Ollama forced off; Groq/Gemini optional
- [x] Source health + failures included in daily email report stage
- [x] Live submission remains disabled
- [x] Tests + evidence; **stop before Phase 5**

### Modules

- `ops/{cloud_db,locks,checkpoints,cost_guard,daily_pipeline}.py`
- CLI: `uae-jobs daily`
- Workflow: `.github/workflows/uae-job-autopilot-daily.yml`

### Tests (executed)

```text
33 passed, 5 deselected (-m 'not live')
```

### Manual Actions invocation

Attempted via `gh workflow run` after push (see evidence). Requires `DATABASE_URL` secret for non-dry production runs; dry_run can validate workflow wiring.

## Phase 5 — Authorized apply

- [ ] Not started
