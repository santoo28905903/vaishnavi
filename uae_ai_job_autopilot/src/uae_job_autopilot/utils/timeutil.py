from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from dateutil import parser as date_parser

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return ensure_aware(value)
    if isinstance(value, (int, float)):
        # Heuristic: ms vs seconds epoch
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=UTC)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return parse_datetime(int(text))
        try:
            return ensure_aware(date_parser.isoparse(text))
        except (ValueError, TypeError):
            try:
                return ensure_aware(date_parser.parse(text))
            except (ValueError, TypeError, OverflowError):
                return None
    return None


def is_within_window(
    published_at: datetime | None,
    *,
    now: datetime | None = None,
    window_hours: int = 24,
) -> bool:
    if published_at is None:
        return False
    now = ensure_aware(now or utcnow())
    published_at = ensure_aware(published_at)
    return (now - published_at) <= timedelta(hours=window_hours) and published_at <= now + timedelta(
        minutes=5
    )
