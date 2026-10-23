from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from uae_job_autopilot.config import Settings, get_settings

logger = logging.getLogger(__name__)

SHEET_TABS = [
    "Dashboard",
    "Applications",
    "TodayJobs",
    "RejectedJobs",
    "RunHistory",
    "SourceHealth",
    "ModelCosts",
    "RecruiterOutreach",
]


class SheetsError(RuntimeError):
    pass


class SheetsClient(ABC):
    @abstractmethod
    def ensure_tabs(self) -> None: ...

    @abstractmethod
    def upsert_rows(
        self, tab: str, rows: list[dict[str, Any]], *, key_field: str
    ) -> int: ...

    @abstractmethod
    def replace_tab(self, tab: str, rows: list[dict[str, Any]]) -> int: ...

    @abstractmethod
    def read_tab(self, tab: str) -> list[dict[str, Any]]: ...


class InMemorySheetsClient(SheetsClient):
    """Local stand-in when Google credentials are absent — used in tests and dry environments."""

    def __init__(self) -> None:
        self.tabs: dict[str, list[dict[str, Any]]] = {t: [] for t in SHEET_TABS}
        self.fail_next_upsert: bool = False
        self.fail_next_replace: bool = False

    def ensure_tabs(self) -> None:
        for t in SHEET_TABS:
            self.tabs.setdefault(t, [])

    def upsert_rows(self, tab: str, rows: list[dict[str, Any]], *, key_field: str) -> int:
        if self.fail_next_upsert:
            self.fail_next_upsert = False
            raise SheetsError("simulated sheets upsert failure")
        self.ensure_tabs()
        existing = {str(r.get(key_field)): r for r in self.tabs.get(tab, []) if key_field in r}
        for row in rows:
            existing[str(row.get(key_field))] = row
        self.tabs[tab] = list(existing.values())
        return len(rows)

    def replace_tab(self, tab: str, rows: list[dict[str, Any]]) -> int:
        if self.fail_next_replace:
            self.fail_next_replace = False
            raise SheetsError("simulated sheets replace failure")
        self.ensure_tabs()
        self.tabs[tab] = list(rows)
        return len(rows)

    def read_tab(self, tab: str) -> list[dict[str, Any]]:
        return list(self.tabs.get(tab, []))


class GoogleSheetsClient(SheetsClient):
    def __init__(self, *, spreadsheet_id: str, service_account_json: str) -> None:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        # service_account_json may be a path or raw JSON
        path_or_info = service_account_json
        try:
            import json
            from pathlib import Path

            p = Path(path_or_info)
            if p.exists():
                creds = Credentials.from_service_account_file(str(p), scopes=scopes)
            else:
                info = json.loads(path_or_info)
                creds = Credentials.from_service_account_info(info, scopes=scopes)
        except Exception as exc:  # noqa: BLE001
            raise SheetsError(f"Failed to load Google credentials: {exc}") from exc

        self._gc = gspread.authorize(creds)
        self._sh = self._gc.open_by_key(spreadsheet_id)

    def ensure_tabs(self) -> None:
        existing = {ws.title for ws in self._sh.worksheets()}
        for tab in SHEET_TABS:
            if tab not in existing:
                self._sh.add_worksheet(title=tab, rows=1000, cols=26)

    def _ws(self, tab: str):
        return self._sh.worksheet(tab)

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def upsert_rows(self, tab: str, rows: list[dict[str, Any]], *, key_field: str) -> int:
        self.ensure_tabs()
        if not rows:
            return 0
        ws = self._ws(tab)
        headers = list(rows[0].keys())
        existing = ws.get_all_records()
        key_to_rownum: dict[str, int] = {}
        if existing:
            # row 1 is header; data starts at 2
            for idx, rec in enumerate(existing, start=2):
                key_to_rownum[str(rec.get(key_field))] = idx
        else:
            ws.update("A1", [headers])

        # Ensure headers
        current_headers = ws.row_values(1)
        if current_headers != headers:
            # Preserve union of headers for stability
            merged = list(dict.fromkeys(current_headers + headers))
            ws.update("A1", [merged])
            headers = merged
            existing = ws.get_all_records()
            key_to_rownum = {
                str(rec.get(key_field)): idx for idx, rec in enumerate(existing, start=2)
            }

        updates = 0
        for row in rows:
            values = [row.get(h, "") for h in headers]
            key = str(row.get(key_field))
            if key in key_to_rownum:
                r = key_to_rownum[key]
                ws.update(f"A{r}", [values])
            else:
                ws.append_row(values, value_input_option="USER_ENTERED")
            updates += 1
        return updates

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def replace_tab(self, tab: str, rows: list[dict[str, Any]]) -> int:
        self.ensure_tabs()
        ws = self._ws(tab)
        ws.clear()
        if not rows:
            return 0
        headers = list(rows[0].keys())
        values = [headers] + [[r.get(h, "") for h in headers] for r in rows]
        ws.update("A1", values)
        return len(rows)

    def read_tab(self, tab: str) -> list[dict[str, Any]]:
        self.ensure_tabs()
        return self._ws(tab).get_all_records()


def build_sheets_client(settings: Settings | None = None) -> SheetsClient:
    settings = settings or get_settings()
    if (
        settings.sheets_enabled
        and settings.google_service_account_json
        and settings.google_sheets_spreadsheet_id
    ):
        try:
            return GoogleSheetsClient(
                spreadsheet_id=settings.google_sheets_spreadsheet_id,
                service_account_json=settings.google_service_account_json,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Google Sheets unavailable, falling back to in-memory: %s", exc)
            return InMemorySheetsClient()
    return InMemorySheetsClient()


def sync_phase3_workbook(
    client: SheetsClient,
    *,
    dashboard: dict[str, Any],
    applications: list[dict[str, Any]],
    today_jobs: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    run_history: list[dict[str, Any]],
    source_health: list[dict[str, Any]],
    model_costs: list[dict[str, Any]],
    recruiter_outreach: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Idempotent sync. On tab failure, records error and continues other tabs.
    """
    results: dict[str, Any] = {"ok": True, "errors": {}}
    client.ensure_tabs()

    def _safe_replace(tab: str, rows: list[dict[str, Any]]) -> None:
        try:
            client.replace_tab(tab, rows)
        except Exception as exc:  # noqa: BLE001
            results["ok"] = False
            results["errors"][tab] = str(exc)
            logger.exception("Sheets replace failed for %s", tab)

    def _safe_upsert(tab: str, rows: list[dict[str, Any]], key: str) -> None:
        try:
            client.upsert_rows(tab, rows, key_field=key)
        except Exception as exc:  # noqa: BLE001
            results["ok"] = False
            results["errors"][tab] = str(exc)
            logger.exception("Sheets upsert failed for %s", tab)

    _safe_replace("Dashboard", [dashboard] if dashboard else [])
    _safe_upsert("Applications", applications, "application_key")
    _safe_replace("TodayJobs", today_jobs)
    _safe_upsert("RejectedJobs", rejected, "application_key")
    _safe_upsert("RunHistory", run_history, "run_id")
    _safe_replace("SourceHealth", source_health)
    _safe_upsert("ModelCosts", model_costs, "id")
    _safe_replace("RecruiterOutreach", recruiter_outreach or [])
    return results
