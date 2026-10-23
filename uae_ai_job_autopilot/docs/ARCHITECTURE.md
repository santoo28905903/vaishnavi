# Architecture — Phases 1–2

```text
CLI (uae-jobs dry-run | discover | evaluate)
        │
        ├─ DiscoveryOrchestrator (Phase 1)
        │     Source adapters → UAE filter → title gate → dedupe → 24h freshness → cap 50
        │
        └─ MatchingPipeline (Phase 2)
              │
              ├─ Hard exclusions (authoritative)
              │     salary floor · experience gap · nationals-only · no-sponsorship
              │
              ├─ EmbeddingService (Sentence Transformers, cached)
              │
              ├─ JevClient → POST https://api.typesafe.ai/v1/systemone
              │     score: relevance, skills
              │     noul: seniority_ok
              │     choice: visa_evidence, next_action
              │
              ├─ Resume fit = 0.4*embedding + 0.6*rubric  (≥75)
              ├─ Visa = 0.5*deterministic + 0.5*Jev      (≥70)
              └─ CostLedger + decision/embedding caches
```

Optional generative routers (Ollama local / Groq / Gemini cloud) are available for prose assist only and are **not** decision authority.

## Provenance & honesty

| Rule | Behavior |
|------|----------|
| Missing `TYPESAFE_API_KEY` | Jev not called; report `jev_configured=false` / `needs_model` |
| Unknown sponsorship | `sponsorship_confirmed=false` always |
| Explicit blocker | `decision=blocked` regardless of scores |
| Cached Jev/embeddings | Recorded in usage with `cached=true`; Jev cache cost counted as 0 |
