# Architecture — Phases 1–3

```text
CLI: dry-run | discover | evaluate | build-master | prepare-docs
        │
        ├─ DiscoveryOrchestrator (P1)
        ├─ MatchingPipeline (P2) — Jev + embeddings + hard rules
        └─ Phase3Pipeline
              ├─ MasterResume (verified editable JSON from PDF)
              ├─ DocumentPipeline
              │     deterministic tailor (+ optional Groq/Gemini)
              │     factual integrity gate
              │     reportlab ATS PDF + reparse ATS score (≥80)
              ├─ ApplicationRepository (SQLite / Postgres-ready)
              ├─ SheetsClient (Google or in-memory) — 8 tabs, upsert/replace + recovery
              └─ EmailClient (Gmail API or in-memory) — daily report + recovery
```

Submission / Playwright apply paths are **Phase 5** and are not present.
