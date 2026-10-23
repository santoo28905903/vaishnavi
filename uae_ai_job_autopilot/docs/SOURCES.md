# Source capability matrix (Phase 1)

| Source | Access mode | Adapter | Live status in evidence run |
|--------|-------------|---------|-----------------------------|
| Greenhouse | Public ATS API | `GreenhouseAdapter` | Queried successfully |
| Lever | Public ATS API | `LeverAdapter` | Queried successfully (0 UAE AI/ML) |
| Ashby | Public ATS API | `AshbyAdapter` | Queried successfully |
| JSearch | Licensed RapidAPI | `JSearchAdapter` | **Not searched** — missing `JSEARCH_API_KEY` |
| LinkedIn Jobs | Alert JSON only | `AlertIngestionAdapter` | **Not searched** — empty `data/alerts/linkedin_jobs/` |
| NaukriGulf | Alert JSON only | `AlertIngestionAdapter` | **Not searched** — empty alert dir |
| Indeed UAE | Alert JSON only | `AlertIngestionAdapter` | **Not searched** — empty alert dir |
| Bayt | Alert JSON only | `AlertIngestionAdapter` | **Not searched** — empty alert dir |
| GulfTalent | Alert JSON only | `AlertIngestionAdapter` | **Not searched** — empty alert dir |
| Michael Page | Alert JSON only | `AlertIngestionAdapter` | **Not searched** — empty alert dir |
| Jooble / SmartRecruiters / Workday / Oracle / SAP / other recruiters | — | none yet | Disabled / planned — not searched |

**Rule:** Never report a source as queried unless its adapter completed an attempted run that is logged in SourceHealth.
