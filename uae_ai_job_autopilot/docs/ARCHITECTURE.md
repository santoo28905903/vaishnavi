# Architecture — Phase 1

```text
CLI (uae-jobs dry-run | discover)
        │
        ▼
DiscoveryOrchestrator
        │
        ├─ SourceAdapter registry (independent)
        │     ├─ Greenhouse / Lever / Ashby  (public ATS JSON)
        │     ├─ JSearch                    (RapidAPI; requires key)
        │     └─ AlertIngestionAdapter      (LinkedIn, NaukriGulf, Indeed UAE,
        │                                    Bayt, GulfTalent, Michael Page)
        │
        ├─ UAE location filter
        ├─ AI/ML title gate (deterministic; not Phase 2 scoring)
        ├─ Cross-source dedupe (URL + soft employer/title/location)
        ├─ Verified 24h freshness window
        └─ Cap 50 selected jobs + SourceHealth report
```

## Provenance rules

| Field | Meaning |
|-------|---------|
| `published_at` | Timestamp from the source when available |
| `publication_confidence` | `verified` / `unverified` / `unknown` |
| `discovered_at` | When this run saw the job |
| Only `verified` + within 24h | Counts toward evaluation selection |

## Honesty rules

- If an adapter did not run successfully (disabled, missing key, empty alert dir, HTTP failure), SourceHealth records it and the run **must not** claim that platform was searched.
- Alert adapters never scrape HTML; they only read permitted JSON exports under `data/alerts/<source>/`.
- Zero verified-fresh jobs ≠ discovery unavailable (see CLI messaging and report notes).
