# Progress checklist

Last updated: 24 Oct 2026, Asia/Kolkata.

## Phase 0 — Repository inspection & plan

- [x] Inspect git repository
- [x] Extract verified resume facts
- [x] Write planning docs
- [x] Stop before implementation

## Phase 1 — Discovery

- [x] Package scaffold (`pyproject.toml`, CLI, logging, settings)
- [x] Domain models + SourceHealth + DiscoveryReport
- [x] Adapters: Greenhouse, Lever, Ashby, JSearch
- [x] Alert ingestion: LinkedIn, NaukriGulf, Indeed UAE, Bayt, GulfTalent, Michael Page
- [x] Normalization, timestamps, UAE filter, AI/ML title gate
- [x] Cross-source dedupe + verified 24h freshness + evaluation cap 50
- [x] CLI `dry-run` and `discover`
- [x] Mocked tests + live connectivity tests
- [x] Real discovery run evidence under `docs/evidence/`
- [x] **Stop before Phase 2**

### Implemented modules

- `src/uae_job_autopilot/cli.py`
- `src/uae_job_autopilot/config.py`
- `src/uae_job_autopilot/domain/*`
- `src/uae_job_autopilot/discovery/{base,registry,orchestrator,normalize,dedupe,freshness}.py`
- `src/uae_job_autopilot/discovery/adapters/{greenhouse,lever,ashby,jsearch,alerts,common}.py`
- `src/uae_job_autopilot/utils/*`

### Test results (executed)

```text
17 passed in ~12.6s
(unit + mocked integration + live connectivity)
```

See `docs/evidence/phase1_pytest.txt`.

### Real external integrations tested

| Source | Result |
|--------|--------|
| Greenhouse public boards API | Live success (8 boards; HTTP 200) |
| Lever public postings API | Live success (2 sites; 0 UAE AI/ML after filters → `empty`) |
| Ashby public job board API | Live success (openai board) |
| JSearch RapidAPI | Not searched — `JSEARCH_API_KEY` absent (`skipped_not_configured`) |
| LinkedIn / NaukriGulf / Indeed UAE / Bayt / GulfTalent / Michael Page | Not searched live — alert dirs empty (`skipped_not_configured`); mocked alert ingestion covered in tests |

### Discovery run evidence

- Summary: `docs/evidence/phase1_discovery_summary.json`
- Detail: `docs/evidence/phase1_discovery_full.json`
- Dry-run: `docs/evidence/phase1_dry_run.json`

Recorded stats (run `20261023T194918Z-5f2d7067`):

- sources attempted: 3 (greenhouse, lever, ashby)
- jobs raw: 2833
- UAE AI/ML: 4 (none inside verified 24h window)
- selected for evaluation: 0
- JSearch / alert boards explicitly **not searched**

UAE AI/ML jobs seen but outside 24h window (not selected):

1. Associate Data Scientist - Builders Program (Emirati National) — Tamara / Greenhouse — published 2026-04-27
2. Binance Accelerator Program - Data Scientist, Analytics — Greenhouse — published 2026-10-14
3. Principal AI Agent Development Engineer/Architect — Greenhouse — published 2026-06-26
4. Forward Deployed Engineer - UAE — OpenAI / Ashby — published 2026-09-21

## Phase 2 — Matching & models

- [ ] Not started — waiting for Phase 2 command

## Phase 3 — Documents, DB, Sheets, Gmail

- [ ] Not started

## Phase 4 — GitHub Actions & cloud ops

- [ ] Not started

## Phase 5 — Authorized apply

- [ ] Not started
