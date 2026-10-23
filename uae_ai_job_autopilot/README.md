# UAE AI Job Autopilot

Production-oriented, cost-optimized autonomous system for UAE AI/ML job discovery, eligibility evaluation, document generation, authorized application submission, tracking, and daily reporting.

**Candidate (source of truth for facts):** Vaishnavi Santoshi Batchu  
**Resume (factual source of truth):** [`data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf`](data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf)

## Current status

| Phase | Scope | Status |
|-------|--------|--------|
| 0 | Repository inspection + implementation plan | Complete |
| 1 | Multi-source discovery, normalization, dedup, source health | **Complete** |
| 2 | Jev, embeddings, model routing, visa + resume matching | Not started |
| 3 | Docs, ATS checks, DB records, Sheets, Gmail reports | Not started |
| 4 | GitHub Actions, cloud DB, secrets, retries, monitoring | Not started |
| 5 | Authorized auto-apply, confirmations, blockers, outreach drafts | Not started |

## Phase 1 quick start

```bash
cd uae_ai_job_autopilot
python3 -m pip install -e '.[dev]'

# Plan only — no live HTTP / alert reads claimed as searches
uae-jobs dry-run

# Real discovery once
uae-jobs discover
uae-jobs discover --summary-only

# Tests
python3 -m pytest                # includes @pytest.mark.live connectivity
python3 -m pytest -m 'not live'  # mocked/unit only
```

Optional: set `JSEARCH_API_KEY` (RapidAPI) to enable the JSearch adapter.  
Optional: drop permitted job-alert JSON into `data/alerts/<source>/` (see `data/alerts/README.md`).

## Phase 1 modules

| Area | Path |
|------|------|
| CLI | `src/uae_job_autopilot/cli.py` |
| Orchestrator | `src/uae_job_autopilot/discovery/orchestrator.py` |
| Greenhouse / Lever / Ashby / JSearch | `src/uae_job_autopilot/discovery/adapters/` |
| Alert ingestion | `src/uae_job_autopilot/discovery/adapters/alerts.py` |
| Dedupe / freshness / normalize | `src/uae_job_autopilot/discovery/` |
| Evidence | `docs/evidence/` |

## Latest real discovery evidence (Phase 1)

See [`docs/evidence/phase1_discovery_summary.json`](docs/evidence/phase1_discovery_summary.json) and [`docs/PROGRESS.md`](docs/PROGRESS.md).

Honest outcome from the recorded run:

- **Queried successfully:** Greenhouse, Lever, Ashby
- **Not searched:** JSearch (no `JSEARCH_API_KEY`); LinkedIn / NaukriGulf / Indeed UAE / Bayt / GulfTalent / Michael Page (no alert JSON exports present)
- **Raw jobs seen:** 2833 across ATS boards
- **UAE AI/ML after filters:** 4
- **Verified-fresh (24h):** 0 → selected for evaluation: 0  
  (distinct from “discovery unavailable”)

## Hard constraints (always)

- No CAPTCHA/MFA bypass, prohibited scraping, false answers, or fabricated submission confirmations.
- Never invent skills, employment history, or qualifications beyond the resume.
- Never claim a source was searched unless its adapter ran successfully.
- Cloud runs must not depend on a local Mac Ollama instance (Phase 2+).

## Docs

- [`docs/PHASE_PLAN.md`](docs/PHASE_PLAN.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/SOURCES.md`](docs/SOURCES.md)
- [`docs/PROGRESS.md`](docs/PROGRESS.md)
