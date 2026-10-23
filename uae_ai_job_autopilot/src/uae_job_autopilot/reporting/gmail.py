from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from uae_job_autopilot.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmailError(RuntimeError):
    pass


class EmailClient(ABC):
    @abstractmethod
    def send(self, *, to: str, subject: str, body: str) -> dict[str, Any]: ...


class InMemoryEmailClient(EmailClient):
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail_next: bool = False

    def send(self, *, to: str, subject: str, body: str) -> dict[str, Any]:
        if self.fail_next:
            self.fail_next = False
            raise EmailError("simulated gmail send failure")
        msg = {"to": to, "subject": subject, "body": body}
        self.sent.append(msg)
        return {"status": "sent", **msg}


class SmtpEmailClient(EmailClient):
    """
    Optional SMTP path. Prefer Gmail API when credentials JSON is a service/oauth path;
    for Phase 3 we support explicit SMTP via env-less dry use and documented API wrapper below.
    """

    def __init__(self, *, host: str, port: int, username: str, password: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def send(self, *, to: str, subject: str, body: str) -> dict[str, Any]:
        msg = EmailMessage()
        msg["To"] = to
        msg["From"] = self.username
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(self.username, self.password)
            smtp.send_message(msg)
        return {"status": "sent", "to": to, "subject": subject}


class GmailApiClient(EmailClient):
    def __init__(self, credentials_json: str) -> None:
        import base64
        import json
        from pathlib import Path

        from google.oauth2.credentials import Credentials
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        self._base64 = base64
        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        p = Path(credentials_json)
        raw = p.read_text(encoding="utf-8") if p.exists() else credentials_json
        info = json.loads(raw)
        if info.get("type") == "service_account":
            creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
            # Domain-wide delegation would set subject; without it, service accounts often cannot send.
            self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            self._user = "me"
        else:
            creds = Credentials.from_authorized_user_info(info, scopes=scopes)
            self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            self._user = "me"

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def send(self, *, to: str, subject: str, body: str) -> dict[str, Any]:
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw = self._base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = (
            self._service.users()
            .messages()
            .send(userId=self._user, body={"raw": raw})
            .execute()
        )
        return {"status": "sent", "to": to, "subject": subject, "id": result.get("id")}


def build_email_client(settings: Settings | None = None) -> EmailClient:
    settings = settings or get_settings()
    if settings.gmail_enabled and settings.gmail_credentials_json:
        try:
            return GmailApiClient(settings.gmail_credentials_json)
        except Exception as exc:  # noqa: BLE001
            logger.error("Gmail API unavailable, falling back to in-memory: %s", exc)
            return InMemoryEmailClient()
    return InMemoryEmailClient()


def build_daily_report_email(
    *,
    discovery_stats: dict[str, Any] | None,
    evaluation_stats: dict[str, Any] | None,
    document_stats: dict[str, Any] | None,
    sources_queried: list[str],
    sources_unavailable: list[dict[str, Any]],
    top_links: list[str],
    model_cost_usd: float,
    failures: list[str],
    dashboard_link: str | None = None,
    discovery_unavailable: bool = False,
    zero_jobs: bool = False,
) -> tuple[str, str]:
    """Returns (subject, body). Distinguishes zero jobs vs discovery unavailable."""
    if discovery_unavailable:
        subject = "UAE AI Job Autopilot — discovery unavailable"
        lead = "Job discovery was unavailable or not attempted for one or more required sources."
    elif zero_jobs:
        subject = "UAE AI Job Autopilot — zero verified-fresh jobs"
        lead = "Discovery ran, but zero verified-fresh UAE AI/ML jobs were selected."
    else:
        subject = "UAE AI Job Autopilot — daily report"
        lead = "Daily discovery / matching / document preparation summary."

    lines = [
        lead,
        "",
        f"Sources queried: {', '.join(sources_queried) or 'none'}",
        f"Sources unavailable: {len(sources_unavailable)}",
    ]
    for s in sources_unavailable[:10]:
        lines.append(f"  - {s.get('source')}: {s.get('status')} — {s.get('detail')}")
    if discovery_stats:
        lines.append("")
        lines.append("Discovery stats:")
        for k, v in discovery_stats.items():
            lines.append(f"  {k}: {v}")
    if evaluation_stats:
        lines.append("")
        lines.append("Evaluation stats:")
        for k, v in evaluation_stats.items():
            lines.append(f"  {k}: {v}")
    if document_stats:
        lines.append("")
        lines.append("Document stats:")
        for k, v in document_stats.items():
            lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append(f"Applications confirmed: 0 (Phase 5 not enabled)")
    lines.append(f"Model cost (USD): {model_cost_usd}")
    if top_links:
        lines.append("")
        lines.append("Top job links:")
        for link in top_links[:10]:
            lines.append(f"  - {link}")
    if dashboard_link:
        lines.append("")
        lines.append(f"Dashboard: {dashboard_link}")
    if failures:
        lines.append("")
        lines.append("Important failures:")
        for f in failures:
            lines.append(f"  - {f}")
    return subject, "\n".join(lines)


def send_daily_report_with_recovery(
    client: EmailClient,
    *,
    to: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Send with retry; on failure return structured error without raising to callers that continue."""
    try:
        return client.send(to=to, subject=subject, body=body)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Daily email failed after retries")
        return {"status": "failed", "error": str(exc), "to": to, "subject": subject}
