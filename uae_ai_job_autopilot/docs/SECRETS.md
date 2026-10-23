# GitHub Secrets — Phase 4

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

## Explicitly disabled

| Variable | Value |
|----------|-------|
| `ENABLE_LIVE_SUBMISSION` | Must remain `false` (Phase 5 not enabled) |
| `OLLAMA_ENABLED` | Forced off in cloud / GitHub Actions |

## Workflow

- File: `.github/workflows/uae-job-autopilot-daily.yml`
- Schedule: `0 10 * * *` with `timezone: Asia/Kolkata`
- Manual: Actions → **UAE AI Job Autopilot Daily** → Run workflow (`dry_run` optional)
