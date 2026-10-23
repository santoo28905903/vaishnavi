# Progress checklist

Last updated: 24 Oct 2026, Asia/Kolkata.

## Phase 0–4

- [x] Complete

## Phase 5 — Authorized apply

- [x] Explicit channel allowlist (`config/application_channels.yaml`)
- [x] Pre-submit checklist (identity, quals, truthful answers, no prior apply, docs valid, method authorized)
- [x] Truthful visa / relocation / salary / notice / qualification answers from `candidate.yaml`
- [x] Confirmation verification before `applied`
- [x] CAPTCHA/MFA/restricted → `blocked` + continue next job
- [x] `submission_unverified` when submit uncertain (never claim `applied`)
- [x] Duplicate protection + retry history on `applications` rows
- [x] Mock sandbox channel for controlled tests (default enabled)
- [x] Greenhouse/Lever Playwright adapters present but **disabled + unauthorized** until explicitly enabled
- [x] Unsupported boards (LinkedIn, Bayt, etc.) honest skip — no fake submit
- [x] Evidence in Postgres/SQLite + Google Sheets + daily email outcomes
- [x] Dry-run / `ENABLE_LIVE_SUBMISSION` safety gates
- [x] Optional recruiter outreach **drafts** only (never auto-send)
- [x] Tests on mock fixtures; **stop**

### Modules

- `config/application_channels.yaml`
- `apply/{answers,checklist,base,channels_config,orchestrator}.py`
- `apply/channels/{mock_sandbox,greenhouse_browser,lever_browser,unsupported,browser_common}.py`
- Alembic `20261024_0003_phase5_application_evidence`
- Daily pipeline stage `apply`; CLI `uae-jobs apply`

### Honest limits

- Public Greenhouse/Lever **discovery** APIs do not accept applications.
- Real browser apply requires channel `enabled` + `authorized` + `ENABLE_LIVE_SUBMISSION=true`.
- No CAPTCHA/MFA bypass. No pretending LinkedIn/Bayt/etc. accept automation.
