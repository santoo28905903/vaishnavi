# Source capability matrix (planning)

Adapters are only marked **enabled** after a Phase 1+ implementation runs successfully. Until then all rows are **planned**.

| Source | Category | Planned access | Phase 1 target | Status |
|--------|----------|----------------|----------------|--------|
| JSearch | Aggregator API | RapidAPI | Implement if key | planned |
| Jooble | Aggregator API | Jooble API | Implement if key | planned |
| Greenhouse | ATS public board | JSON boards | Implement (public) | planned |
| Lever | ATS public postings | JSON | Implement (public) | planned |
| Ashby | ATS public board | JSON | Implement (public) | planned |
| SmartRecruiters | ATS | Public ads API where available | Probe | planned |
| Workday | ATS | Official feed only | Conditional | planned / often unsupported |
| Oracle Recruiting | ATS | Official feed only | Conditional | planned / often unsupported |
| SAP SuccessFactors | ATS | Official feed only | Conditional | planned / often unsupported |
| NaukriGulf | Board | Authorized API or alerts only | Health stub if no API | planned |
| LinkedIn Jobs | Board | Alerts/export; no scrape | Health stub | planned |
| Indeed UAE | Board | Authorized path only | Health stub | planned |
| Bayt | Board | Authorized path only | Health stub | planned |
| GulfTalent | Board | Authorized path only | Health stub | planned |
| Foundit Gulf | Board | Authorized path only | Health stub | planned |
| Michael Page UAE | Recruiter | Permitted feed/search | Conditional | planned |
| Hays UAE | Recruiter | Permitted feed/search | Conditional | planned |
| Robert Half | Recruiter | Permitted feed/search | Conditional | planned |
| TASC Outsourcing | Recruiter | Permitted feed/search | Conditional | planned |
| Charterhouse ME | Recruiter | Permitted feed/search | Conditional | planned |
| Discovered MENA | Recruiter | Permitted feed/search | Conditional | planned |
| Kingston Stanley | Recruiter | Permitted feed/search | Conditional | planned |
| Salt | Recruiter | Permitted feed/search | Conditional | planned |
| Cooper Fitch | Recruiter | Permitted feed/search | Conditional | planned |
| Priority employers | Career pages / ATS | Prefer Greenhouse/Lever/Ashby | Board ID registry | planned |

**Rule:** Never report a source as queried unless its adapter completed a successful or explicitly failed attempt that is logged in SourceHealth.
