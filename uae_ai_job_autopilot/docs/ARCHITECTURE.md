# Architecture — Phases 1–5

```text
GitHub Actions (10:00 Asia/Kolkata) / workflow_dispatch
        │
        ▼
uae-jobs daily
        │
        ├─ assert persistent DATABASE_URL (no cloud SQLite)
        ├─ RunLock (DB) + Actions concurrency group
        ├─ CheckpointStore per stage (resumable)
        ├─ CostGuard (DAILY_COST_CAP_USD)
        │
        ├─ discover     (P1 adapters + source health)
        ├─ evaluate     (P2 Jev/embeddings; Ollama forced off in cloud)
        ├─ prepare_docs (P3 PDFs/ATS/DB/Sheets)
        ├─ apply        (P5 allowlisted channels only)
        └─ report       (Gmail daily; failures + apply outcomes + source health)
```

## Phase 5 apply gates

1. Channel must match `config/application_channels.yaml` URL patterns.
2. Pre-submit checklist: identity, truthful visa/relocation/salary/notice/quals, ATS pass, docs on disk, no prior apply, method authorized.
3. `ENABLE_LIVE_SUBMISSION=true` required for channels with `requires_live_submission`.
4. CAPTCHA/MFA → `blocked` (continue). Unconfirmed submit → `submission_unverified` (not `applied`).
5. Confirmation markers required before status `applied`.
6. Unsupported boards → honest `skipped_unsupported` (no fake success).

Mock sandbox is the only channel enabled by default for controlled tests.
