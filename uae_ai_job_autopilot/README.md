# UAE AI Job Autopilot

Production-oriented, cost-optimized autonomous system for UAE AI/ML job discovery, eligibility evaluation, document generation, authorized application submission, tracking, and daily reporting.

**Candidate (source of truth for facts):** Vaishnavi Santoshi Batchu  
**Resume (factual source of truth):** [`data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf`](data/resume/Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf)

## Current status

| Phase | Scope | Status |
|-------|--------|--------|
| 0 | Repository inspection + implementation plan | **Complete** (this document set) |
| 1 | Multi-source discovery, normalization, dedup, source health | Not started — wait for Phase 1 command |
| 2 | Jev, embeddings, model routing, visa + resume matching | Not started |
| 3 | Docs, ATS checks, DB records, Sheets, Gmail reports | Not started |
| 4 | GitHub Actions, cloud DB, secrets, retries, monitoring | Not started |
| 5 | Authorized auto-apply, confirmations, blockers, outreach drafts | Not started |

See [`docs/PHASE_PLAN.md`](docs/PHASE_PLAN.md) for the full milestone checklist, API inventory, dependencies, limitations, and test strategy.

See [`docs/PROGRESS.md`](docs/PROGRESS.md) for living progress notes.

## Hard constraints (always)

- No CAPTCHA/MFA bypass, prohibited scraping, false answers, or fabricated submission confirmations.
- Never invent skills, employment history, or qualifications beyond the resume.
- Never misrepresent visa status, location, compensation, or work authorization.
- Unknown sponsorship ≠ confirmed sponsorship.
- Cloud runs must not depend on a local Mac Ollama instance.
- Do not claim a source was searched unless its adapter ran successfully.

## Quick start (after Phase 1+)

Implementation and runnable commands will be added when Phase 1 lands. Until then this package contains planning docs and the verified resume only.

## Repository note

The GitHub repository root currently contains an unrelated static HTML fashion site (`1.html`, `men.html`, images, etc.). This autopilot lives under `uae_ai_job_autopilot/` so existing assets are left untouched.
