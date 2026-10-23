# UAE AI Job Autopilot — Phase 0 Plan

Prepared after inspecting the repository and the verified resume PDF.  
**No Phase 1–5 application code is implemented in this deliverable.**

---

## 1. Existing code analysis

### Repository state

| Item | Finding |
|------|---------|
| Git remote | `github.com/santoo28905903/vaishnavi` |
| Default branch | `main` |
| History | Single commit: `Add files via upload` |
| Python project | **None** — no `pyproject.toml`, `requirements.txt`, `src/`, tests, or CI workflows |
| Autopilot code | **None** |
| Existing content | Static HTML fashion site (`1.html`, `men.html`, `women.html`, `kids.html`, `draft1.html`, `styles.css`, many product images, `reg._card.docx`) — **unrelated** to this project |

### Reusable modules

Nothing in the current repository is reusable for job discovery, matching, document generation, Sheets/Gmail, or application submission.

### Verified candidate facts (from resume PDF)

These facts are locked as the factual source of truth for later phases. Do not invent beyond this.

| Field | Verified value |
|-------|----------------|
| Full name | Vaishnavi Santoshi Batchu |
| Email | vaishnavibatchu28@gmail.com |
| Phone | +91 8500915151 |
| LinkedIn | linkedin.com/in/vaishnavi-santoshi-443527244 |
| Location | Pune, Maharashtra 411057 |
| Headline | Senior Data Scientist \| Generative AI & Agentic AI Engineer |
| Experience | 4+ years (stated in summary) |
| Current | Senior Data Scientist — Google (via Relanto), Jan 2025 – Present |
| Previous | Machine Learning Engineer — Searce Inc, Aug 2023 – Dec 2024 |
| Previous | Analyst ML Engineer — Searce Inc, Jul 2022 – Feb 2023 |
| Education | B.Tech, Data Science & Artificial Intelligence — ICFAI, Hyderabad, 2019 – 2023 |
| Certifications | GCP Professional ML Engineer; GCP Professional Data Engineer; GCP Associate Cloud Engineer; GCP Generative AI Leader; AWS ML – Specialty |
| Core stack | Python, SQL, LangGraph, LangChain, Google ADK, MCP, RAG, LLMs, FastAPI/Flask, Docker, Vertex AI, Document AI, Cloud Run, BigQuery, AWS Bedrock, MLOps, CV, vector search |

### Missing functionality (all of it)

- Source adapters, normalization, timestamps, deduplication, provenance, source-health
- Jev / embeddings / generative model routers and decision caches
- Deterministic + model eligibility (salary, visa, skills, seniority)
- Resume/cover-letter generation and ATS scoring
- PostgreSQL/SQLite persistence, Alembic migrations
- Google Sheets sync and Gmail daily reports
- GitHub Actions schedule (10:00 Asia/Kolkata), secrets, retries, cost controls
- Authorized application submission, confirmation verification, blocker handling
- CLI (`dry-run`, single run), concurrency locks, resumable runs

---

## 2. Proposed folder structure

```text
uae_ai_job_autopilot/
├── README.md
├── docs/
│   ├── PHASE_PLAN.md          # this document
│   ├── PROGRESS.md            # living checklist
│   ├── ARCHITECTURE.md        # added in Phase 1+
│   └── SOURCES.md             # adapter capability matrix (Phase 1)
├── pyproject.toml
├── .env.example               # names only; never commit secrets
├── .gitignore
├── alembic.ini
├── alembic/
│   └── versions/
├── config/
│   ├── candidate.yaml         # profile + salary/visa/notice (Phase 2+)
│   ├── search_profile.yaml    # titles, locations, freshness window
│   ├── sources.yaml           # enabled adapters + quotas
│   ├── models.yaml            # Jev / Ollama / Groq / Gemini routers
│   └── application_channels.yaml  # Phase 5 allowlist only
├── data/
│   ├── resume/
│   │   └── Vaishnavi_Santoshi_Batchu_Resume_ATS.pdf
│   └── cache/                 # gitignored embeddings/decisions
├── src/uae_job_autopilot/
│   ├── __init__.py
│   ├── cli.py                 # dry-run / run-once
│   ├── config.py              # pydantic-settings
│   ├── logging.py
│   ├── domain/
│   │   ├── models.py          # JobPosting, RunReport, SourceHealth, …
│   │   └── enums.py
│   ├── discovery/
│   │   ├── base.py            # SourceAdapter protocol
│   │   ├── registry.py
│   │   ├── orchestrator.py    # Phase 1 pipeline
│   │   ├── normalize.py
│   │   ├── dedupe.py
│   │   ├── freshness.py
│   │   └── adapters/
│   │       ├── jsearch.py
│   │       ├── jooble.py
│   │       ├── greenhouse.py
│   │       ├── lever.py
│   │       ├── ashby.py
│   │       ├── indeed_uae.py  # only if authorized path exists
│   │       ├── linkedin.py    # alerts/export path if no API
│   │       ├── bayt.py
│   │       ├── gulftalent.py
│   │       ├── naukrigulf.py
│   │       ├── foundit.py
│   │       ├── recruiters/    # Michael Page, Hays, …
│   │       └── employers/     # G42, Careem career feeds, …
│   ├── matching/              # Phase 2
│   ├── documents/             # Phase 3
│   ├── tracking/              # Phase 3 DB + Sheets
│   ├── reporting/             # Phase 3 Gmail
│   ├── apply/                 # Phase 5
│   ├── models/                # Jev, embeddings, routers
│   ├── db/
│   │   ├── session.py
│   │   └── tables.py
│   └── utils/
│       ├── http.py            # httpx + tenacity
│       ├── money.py           # AED normalization
│       └── time.py            # Asia/Kolkata helpers
├── tests/
│   ├── unit/
│   ├── integration/           # gated by credentials / network markers
│   └── fixtures/
│       └── sample_jobs/
└── .github/workflows/
    └── daily_job_run.yml      # Phase 4
```

Root fashion HTML remains outside this package.

---

## 3. Dependency list

Pinned major versions to be confirmed at Phase 1 scaffold (`pyproject.toml`).

### Core (Phase 1+)

| Package | Role |
|---------|------|
| Python 3.12+ | Runtime |
| `pydantic` / `pydantic-settings` | Config + domain models |
| `httpx` | HTTP clients |
| `tenacity` | Retries |
| `sqlalchemy` | ORM |
| `alembic` | Migrations |
| `structlog` or stdlib JSON logging | Structured logs |
| `python-dateutil` / `zoneinfo` | Timestamps + Asia/Kolkata |
| `pytest` / `pytest-asyncio` / `respx` | Tests + HTTP mocking |
| `PyYAML` | Config files |
| `rich` (optional) | CLI output |

### Phase 2+

| Package | Role |
|---------|------|
| `typesafe-sdk` or direct HTTPX to System One | TypeSafe Jev |
| `sentence-transformers` | Local embeddings |
| `numpy` | Similarity math |
| Groq / Google GenAI official clients | Free-tier generative routing |
| `diskcache` or SQLite cache table | Decision/document cache |

### Phase 3+

| Package | Role |
|---------|------|
| `reportlab` or `fpdf2` | ATS PDF generation |
| `pypdf` / `pdfminer.six` | Resume parse / ATS checks |
| `gspread` + Google service account | Sheets sync |
| Gmail API client or SMTP via Google | Daily reports |

### Phase 4–5

| Package | Role |
|---------|------|
| `psycopg[binary]` | PostgreSQL (cloud) |
| `playwright` | Permitted browser automation only |
| GitHub Actions `cron` | 10:00 Asia/Kolkata |

**Explicitly deferred unless justified:** LangGraph, CrewAI, AutoGen, and similar agent frameworks. Prefer a deterministic state machine.

---

## 4. API integration inventory

Status legend: **Planned** = design-ready; **Blocked** = needs credential or authorized path; **Unknown** = capability must be verified before claiming support.

### Decision / generative models

| Integration | Endpoint / access | Env vars | Phase | Notes |
|-------------|-------------------|----------|-------|-------|
| TypeSafe Jev (System One) | `POST https://api.typesafe.ai/v1/systemone` | `TYPESAFE_API_KEY`, `JEV_MODEL` (e.g. `jev-1.14.0` or `jev-latest`) | 2 | Structured Choice / Score / Noul — not prose. Prefer pinned version in prod. |
| Local embeddings | Sentence Transformers on-process | model name in config | 2 | Cloud-safe; no Mac dependency |
| Ollama (local Mac only) | localhost | `OLLAMA_*` | 2 | Separate local router; **disabled in cloud** |
| Groq free tier | Groq API | `GROQ_API_KEY` | 2 | Generative docs / optional assist |
| Gemini Flash-Lite free tier | Google AI | `GEMINI_API_KEY` | 2 | Generative docs |
| Optional paid LLM | disabled by default | provider key | 2–3 | Cost-gated |

### Job discovery sources

| Source | Access hypothesis | Auth | Phase 1 intent |
|--------|-------------------|------|----------------|
| JSearch (RapidAPI) | Documented jobs API | `JSEARCH_API_KEY` | Implement if key present; else mark unavailable |
| Jooble | Public/partner API | `JOOBLE_API_KEY` | Same |
| Greenhouse board API | Public job boards JSON | none / board tokens | Employer + agency boards |
| Lever postings API | Public postings | none / site | Same |
| Ashby | Public job board API | none / org | Same |
| SmartRecruiters | Public job ads API where available | varies | Probe + adapter if permitted |
| Workday / Oracle / SAP SuccessFactors | Often HTML or tenant-specific | varies | Only official feeds or documented APIs; else alert/manual link path |
| NaukriGulf, Bayt, GulfTalent, Foundit, Indeed UAE, LinkedIn Jobs | Mostly no free official apply/search API for automation | varies | Prefer licensed aggregators, official RSS/alerts, or email alerts; **no prohibited scraping** |
| Recruiter sites (Michael Page, Hays, Robert Half, TASC, Charterhouse, Discovered MENA, Kingston Stanley, Salt, Cooper Fitch) | Career search pages / feeds | varies | Adapter only when a permitted endpoint exists; otherwise source-health = unsupported |
| Priority employers (G42, Core42, Presight, Inception, AIQ, Microsoft, AWS, Google, Oracle, IBM, Salesforce, SAP, Accenture, Deloitte, PwC, EY, KPMG, Capgemini, Emirates Group, Emirates NBD, Careem, Talabat, Noon, Property Finder, Dubizzle, e&, …) | Prefer Greenhouse/Lever/Ashby/Workday feeds | board IDs | Phase 1 employer feed registry |

### Tracking / reporting / apply

| Integration | Phase | Notes |
|-------------|-------|-------|
| SQLite (local) / PostgreSQL (cloud) | 3–4 | Sheets is **not** system of record |
| Google Sheets | 3 | Service account; Dashboard, Applications, TodayJobs, RejectedJobs, RunHistory, SourceHealth, ModelCosts, RecruiterOutreach |
| Gmail | 3 | Daily report to candidate email |
| Authorized apply channels | 5 | Explicit allowlist in `application_channels.yaml` only |
| Playwright | 5 | Only for permitted automation; CAPTCHA/MFA → blocked |

---

## 5. Five-phase milestone checklist

### Phase 0 — Plan (this delivery)

- [x] Inspect repository
- [x] Extract verified resume facts
- [x] Folder structure proposal
- [x] Dependency + API inventories
- [x] Phase checklist, limitations, credentials, test strategy
- [x] Stop before implementation

### Phase 1 — Discovery foundation

- [ ] Scaffold Python package (`pyproject.toml`, CLI stubs, logging, settings)
- [ ] Domain models: `JobPosting`, provenance, publication vs discovery time, freshness flags
- [ ] `SourceAdapter` protocol + registry + orchestrator
- [ ] At least 2–3 **working** adapters with real or mocked-but-honest failure paths (prefer JSearch/Jooble + Greenhouse/Lever/Ashby public boards)
- [ ] Register remaining sources as `not_configured` / `unsupported` with health reporting (never claim searched)
- [ ] Normalization (title, employer, location UAE, salary parse to AED when present)
- [ ] Deduplication (job ID, URL, employer+title+location fingerprint)
- [ ] Rolling 24h freshness window; cap 50 verified-fresh unique jobs for evaluation handoff
- [ ] Persist counts: discovered / fresh / excluded / duplicates
- [ ] Source-health report artifact
- [ ] Unit + integration tests with recorded fixtures; document which live APIs were actually called
- [ ] Update README + PROGRESS; **stop**

### Phase 2 — Matching & models

- [ ] TypeSafe Jev client (System One), pinned `JEV_MODEL`
- [ ] Deterministic hard rules: salary floor AED 20,000 max, experience, location, explicit blockers
- [ ] Sentence Transformers embeddings + cache
- [ ] Cloud vs local generative routers (Ollama local-only)
- [ ] Resume parse from PDF (truthful fields only)
- [ ] Fit score: 40% embedding + 60% Jev rubric; threshold 75
- [ ] Visa evidence: 50% deterministic + 50% Jev; threshold 70; unknown ≠ confirmed
- [ ] Decision/cost/error telemetry
- [ ] Tests with mocked Jev + fixture jobs; optional live smoke if key present
- [ ] Update docs; **stop**

### Phase 3 — Documents, tracking, reporting

- [ ] Tailored ATS PDF resume + cover letter (no fabricated claims)
- [ ] ATS score: 40% structure + 60% keyword coverage; threshold 80
- [ ] SQLite schema + Alembic; idempotent application keys
- [ ] Google Sheets sync for the eight tabs
- [ ] Gmail daily report template (zero jobs vs discovery unavailable)
- [ ] Tests for generators, upserts, report content
- [ ] Update docs; **stop**

### Phase 4 — Cloud deployment

- [ ] GitHub Actions: cron `0 4 * * *` UTC ≈ 10:00 Asia/Kolkata (+ IST offset handling / `cron` with timezone if available)
- [ ] `workflow_dispatch` manual run
- [ ] PostgreSQL for cloud; secrets via GitHub Secrets
- [ ] Retries, concurrency lock, resumable run state, cost ceilings
- [ ] Monitoring + failure surfacing in email/Sheets
- [ ] Document required secrets; dry-run in CI without leaking secrets
- [ ] Update docs; **stop**

### Phase 5 — Authorized apply

- [ ] Explicit channel allowlist only
- [ ] Pre-submit checklist (identity, quals, truthful answers, no prior apply, docs valid, method authorized)
- [ ] Confirmation verification before `applied`
- [ ] CAPTCHA/MFA/restricted → `blocked` + continue
- [ ] Duplicate protection + retry history
- [ ] Optional recruiter outreach **drafts** (not auto-send unless separately authorized)
- [ ] End-to-end tests on sandbox/allowlisted fixtures only
- [ ] Update docs; **stop**

---

## 6. Current limitations and credentials needed

### Limitations right now

1. **Greenfield:** no executable autopilot code yet.
2. **Source legality:** many Gulf boards lack free public search APIs; Phase 1 will only enable adapters that are authorized/documented. Others stay `unsupported` until a lawful path exists.
3. **No LinkedIn official jobs API** for personal automation at typical free tiers — plan alerts/export or licensed aggregators, not scraping.
4. **Cloud ≠ local Mac:** Ollama and local Playwright sessions are optional side paths.
5. **Apply automation** is Phase 5 and allowlist-only; discovery APIs ≠ apply permission.
6. **Unrelated repo content:** fashion HTML remains; autopilot is isolated under `uae_ai_job_autopilot/`.

### Credentials / resources to supply before later phases

| Secret / resource | Needed by | Purpose |
|-------------------|-----------|---------|
| `TYPESAFE_API_KEY` | Phase 2 | Jev decisions |
| `JEV_MODEL` | Phase 2 | Pin e.g. `jev-1.14.0` |
| `JSEARCH_API_KEY` (or RapidAPI key) | Phase 1 (optional) | Aggregated jobs |
| `JOOBLE_API_KEY` | Phase 1 (optional) | Jooble |
| Other source keys as adapters are validated | Phase 1+ | Per-source |
| `GROQ_API_KEY` | Phase 2–3 | Free-tier generation |
| `GEMINI_API_KEY` | Phase 2–3 | Flash-Lite generation |
| Google service account JSON (Sheets) | Phase 3 | Dashboard sync |
| Gmail OAuth or Workspace send credentials | Phase 3 | Daily email |
| `DATABASE_URL` (Postgres) | Phase 4 | Cloud persistence |
| GitHub Actions secrets | Phase 4 | Scheduled runs |
| Apply-channel credentials (per allowlisted ATS) | Phase 5 | Submission only |

Candidate confirmation still needed later for: exact notice period, salary negotiation bounds updates, and which apply channels are explicitly authorized.

---

## 7. Test strategy

### Principles

- Never invent API responses or claim live success without execution.
- Prefer **recorded fixtures** (`respx` / VCR-style) for CI.
- Mark live tests `@pytest.mark.live` and skip without credentials.
- Separate **unit** (normalize, dedupe, salary parse, scoring math) from **integration** (adapter + DB + Sheets mocks).
- Report three outcomes honestly: **passed**, **skipped (no credential)**, **failed**.

### Phase 1 focus

| Layer | Examples |
|-------|----------|
| Unit | UAE location detection; AED salary parse; fingerprint dedupe; 24h freshness; 50-cap selection |
| Adapter | Fixture JSON → normalized `JobPosting`; error → `SourceHealth` failure without fake jobs |
| Orchestrator | Mix healthy + failing adapters; assert counts and “not searched” for disabled sources |
| Live (optional) | One real Greenhouse board fetch; JSearch only if key set |

### Later phases

- Phase 2: mock Jev Choice/Score/Noul payloads; embedding determinism on fixtures; hard-rule overrides.
- Phase 3: PDF structure smoke tests; idempotent DB upserts; email body snapshot tests.
- Phase 4: workflow YAML validation; dry-run job in Actions with secrets masked.
- Phase 5: apply dry-run against sandbox; assert blocked path never marks `applied`.

### Definition of done per phase

1. Implemented modules listed in PROGRESS.
2. Pytest (or documented live commands) executed; results pasted/summarized honestly.
3. README + checklist updated.
4. No start of the next phase until commanded.
