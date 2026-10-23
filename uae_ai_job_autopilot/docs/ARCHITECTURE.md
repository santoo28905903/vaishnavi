# Architecture — Phases 1–4

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
        ├─ discover  (P1 adapters + source health)
        ├─ evaluate  (P2 Jev/embeddings; Ollama forced off in cloud)
        ├─ prepare_docs (P3 PDFs/ATS/DB/Sheets)
        └─ report (Gmail daily; failures + source health)
```

Phase 5 application submission is not wired (`ENABLE_LIVE_SUBMISSION` ignored/false).
