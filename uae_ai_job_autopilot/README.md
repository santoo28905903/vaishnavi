# UAE AI Job Autopilot

Production-oriented, cost-optimized autonomous system for UAE AI/ML job discovery, eligibility evaluation, document generation, authorized application submission, tracking, and daily reporting.

**Candidate (source of truth for facts):** Vaishnavi Santoshi Batchu  
**Resume (factual source of truth):** [`data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf`](data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf)

## Current status

| Phase | Scope | Status |
|-------|--------|--------|
| 0 | Plan | Complete |
| 1 | Multi-source discovery | Complete |
| 2 | Jev + embeddings + visa/resume matching | **Complete** |
| 3 | Docs, Sheets, Gmail | Not started |
| 4 | GitHub Actions / cloud ops | Not started |
| 5 | Authorized auto-apply | Not started |

## Quick start

```bash
cd uae_ai_job_autopilot
python3 -m pip install -e '.[dev]'

# Phase 1
uae-jobs dry-run
uae-jobs discover --summary-only

# Phase 2 matching (representative fixtures by default)
export TYPESAFE_API_KEY=...          # required for live Jev decisions
export JEV_MODEL=jev-1.14.0          # pin in production
uae-jobs evaluate --summary-only
uae-jobs evaluate --jobs-json tests/fixtures/jobs/representative_jobs.json

pytest -m 'not live'                 # unit + mocked
pytest                               # also runs live tests (skip if no keys)
```

## Phase 2 scoring

| Gate | Formula | Threshold |
|------|---------|-----------|
| Resume fit | 40% embedding + 60% Jev rubric | **75** |
| Visa | 50% deterministic + 50% Jev | **70** |

Explicit sponsorship / nationals-only blockers **always override** numeric scores.  
Unknown sponsorship is never reported as confirmed sponsorship.

## Hard constraints

- No CAPTCHA/MFA bypass, prohibited scraping, fabricated confirmations, or invented resume facts.
- Cloud must not depend on local Mac Ollama (`OLLAMA_ENABLED` default false).
- Never claim a source/model was used unless it actually ran.

## Docs

- [`docs/PHASE_PLAN.md`](docs/PHASE_PLAN.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/PROGRESS.md`](docs/PROGRESS.md)
- [`docs/SOURCES.md`](docs/SOURCES.md)
- Evidence: [`docs/evidence/`](docs/evidence/)
