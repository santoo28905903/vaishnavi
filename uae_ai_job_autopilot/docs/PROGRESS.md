# Progress checklist

Last updated: 24 Oct 2026, Asia/Kolkata.

## Phase 0 — Repository inspection & plan

- [x] Complete

## Phase 1 — Discovery

- [x] Complete (see prior evidence under `docs/evidence/phase1_*`)

## Phase 2 — Matching & models

- [x] TypeSafe Jev client (`POST /v1/systemone`), pinned `JEV_MODEL`
- [x] Deterministic hard rules (salary floor, experience gap, nationals-only, no-sponsorship)
- [x] Sentence Transformers embeddings + disk cache
- [x] Cloud vs local generative routers (Ollama local-only; Groq/Gemini opt-in)
- [x] Resume parse from PDF (truthful fields only)
- [x] Fit score: 40% embedding + 60% Jev rubric; threshold 75
- [x] Visa: 50% deterministic + 50% Jev; threshold 70; unknown ≠ confirmed
- [x] Decision/cost/error telemetry + model decision cache
- [x] Tests with mocked Jev + fixtures; live Jev skipped without `TYPESAFE_API_KEY`
- [x] Update docs; **stop before Phase 3**

### Implemented modules

- `src/uae_job_autopilot/models/{jev,embeddings,routers,cache,costs}.py`
- `src/uae_job_autopilot/matching/{resume,hard_rules,visa,scoring,pipeline}.py`
- CLI: `uae-jobs evaluate`

### Test results (executed)

```text
19 passed, 5 deselected (-m 'not live') 
# Full suite with live markers: live Jev skipped without TYPESAFE_API_KEY;
# Phase 1 live ATS tests pass when network available.
```

See `docs/evidence/phase2_pytest.txt`.

### Real provider calls

| Provider | Status |
|----------|--------|
| TypeSafe Jev | **Not called in evidence run** — `TYPESAFE_API_KEY` absent. Mocked System One responses covered in unit tests. Live test auto-skips. |
| Sentence Transformers (`all-MiniLM-L6-v2`) | Loaded locally during `uae-jobs evaluate` evidence run |
| Ollama / Groq / Gemini | Disabled / no keys — not called |

### Evaluate evidence (fixtures, no Jev key)

`docs/evidence/phase2_evaluate_summary.json` / `phase2_evaluate_run.summary.json`

- jobs_input: 6
- hard_blocked: 4 (nationals-only, no-sponsorship, salary floor, experience gap)
- match_pass: 0 (Jev rubric unavailable without API key → remaining jobs `needs_model` / fail resume gate)
- notes honestly state Jev was not configured

With a mocked Jev client in unit tests: `good-rag-1` **PASS**es resume≥75 and visa≥70 with `sponsorship_confirmed=true`; blockers remain authoritative.

## Phase 3 — Documents, DB, Sheets, Gmail

- [ ] Not started — waiting for Phase 3 command

## Phase 4 — GitHub Actions & cloud ops

- [ ] Not started

## Phase 5 — Authorized apply

- [ ] Not started
