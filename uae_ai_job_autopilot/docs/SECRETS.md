# GitHub Secrets — Phases 4–5

Configure repository secrets (Settings → Secrets and variables → Actions).  
Never commit secret values.

## Required for production daily runs

| Secret | Purpose |
|--------|---------|
| `DATABASE_URL` | **Persistent** Postgres URL, e.g. `postgresql+psycopg://USER:PASS@HOST:5432/uae_jobs`. SQLite is rejected when `ENVIRONMENT=cloud`. |

## Strongly recommended

| Secret | Purpose |
|--------|---------|
| `TYPESAFE_API_KEY` | Jev System One decisions |
| `JEV_MODEL` | Pin e.g. `jev-1.14.0` |
| `REPORT_TO_EMAIL` | Daily report recipient (default candidate email) |

## Optional sources / generative / reporting

| Secret | Purpose |
|--------|---------|
| `JSEARCH_API_KEY` | JSearch adapter |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | Optional cloud generative tailor |
| `ENABLE_CLOUD_GENERATIVE` | `true` to allow Groq/Gemini |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Sheets service account JSON (string or use a file secret pattern) |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Spreadsheet id |
| `SHEETS_ENABLED` | `true` to sync Sheets |
| `GMAIL_CREDENTIALS_JSON` | Gmail API credentials JSON |
| `GMAIL_ENABLED` | `true` to send email |
| `DAILY_COST_CAP_USD` | Default `2.0` |

## Phase 5 — application submission

| Variable | Value / guidance |
|----------|------------------|
| `ENABLE_LIVE_SUBMISSION` | Keep `false` until mock_sandbox tests pass. Set `true` only after channels in `config/application_channels.yaml` are `enabled: true` **and** `authorized: true`. |
| Channel authorization | Not a secret — edit `application_channels.yaml`. Greenhouse/Lever start disabled. |
| Playwright | Required for authorized browser channels (`playwright install chromium` on the runner). |

Public Greenhouse/Lever discovery APIs do **not** accept applications. Do not add employer Harvest keys unless you intentionally authorize that path.

## Explicitly constrained

| Variable | Value |
|----------|-------|
| `OLLAMA_ENABLED` | Forced off in cloud / GitHub Actions |
| Unsupported boards | LinkedIn, Bayt, GulfTalent, NaukriGulf, Indeed UAE, etc. — never automated submit |

## Workflow

- File: `.github/workflows/uae-job-autopilot-daily.yml`
- Schedule: `0 10 * * *` with `timezone: Asia/Kolkata`
- Manual: Actions → **UAE AI Job Autopilot Daily** → Run workflow (`dry_run` optional)
