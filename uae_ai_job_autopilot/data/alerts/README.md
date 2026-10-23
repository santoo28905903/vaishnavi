# Job alert ingestion

Boards without an authorized programmatic search API (LinkedIn, NaukriGulf, Indeed UAE, Bayt, GulfTalent, Michael Page) are **not scraped**.

To include jobs from those sources:

1. Create or use the subdirectory named after the source (`linkedin_jobs`, `naukrigulf`, …).
2. Drop one or more `.json` files exported from job alerts / saved searches you are permitted to use.
3. Re-run `uae-jobs discover`.

## JSON schema

```json
{
  "jobs": [
    {
      "title": "Senior Machine Learning Engineer",
      "employer": "Example Corp",
      "location": "Dubai, United Arab Emirates",
      "application_url": "https://example.com/jobs/123",
      "published_at": "2026-10-23T08:00:00+00:00",
      "source_job_id": "optional-id",
      "description": "optional",
      "salary_raw": "AED 25000-30000 / month"
    }
  ]
}
```

If a directory is missing or empty, SourceHealth records `skipped_not_configured` and the daily report must **not** claim that platform was searched.
