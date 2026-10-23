from __future__ import annotations

import re
from typing import Any

AED_PER_USD = 3.6725
AED_PER_EUR = 4.0  # approximate; only used when source currency explicit
AED_PER_GBP = 4.7


def _to_monthly(amount: float, period: str | None) -> float:
    p = (period or "month").lower()
    if p in {"year", "yearly", "annual", "annually", "yr", "pa"}:
        return amount / 12.0
    if p in {"week", "weekly"}:
        return amount * 52.0 / 12.0
    if p in {"day", "daily"}:
        return amount * 22.0
    if p in {"hour", "hourly"}:
        return amount * 160.0
    return amount


def _convert_to_aed(amount: float, currency: str | None) -> float:
    c = (currency or "AED").upper().replace(" ", "")
    if c in {"AED", "DH", "DHS", "DIRHAM", "DIRHAMS"}:
        return amount
    if c in {"USD", "US$", "$"}:
        return amount * AED_PER_USD
    if c in {"EUR", "€"}:
        return amount * AED_PER_EUR
    if c in {"GBP", "£"}:
        return amount * AED_PER_GBP
    return amount


def parse_salary_to_aed_monthly(
    raw: str | None = None,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    currency: str | None = None,
    period: str | None = None,
) -> tuple[float | None, float | None]:
    """Best-effort salary parse. Returns (min, max) monthly AED or (None, None)."""
    if min_value is not None or max_value is not None:
        lo = _convert_to_aed(_to_monthly(min_value, period), currency) if min_value is not None else None
        hi = _convert_to_aed(_to_monthly(max_value, period), currency) if max_value is not None else None
        return lo, hi

    if not raw:
        return None, None

    text = raw.strip()
    curr = currency
    if not curr:
        if re.search(r"\bAED\b|dirham", text, re.I):
            curr = "AED"
        elif re.search(r"\bUSD\b|US\$", text, re.I) or "$" in text:
            curr = "USD"
        elif re.search(r"\bEUR\b|€", text, re.I):
            curr = "EUR"
        elif re.search(r"\bGBP\b|£", text, re.I):
            curr = "GBP"
        else:
            curr = "AED"

    per = period
    if not per:
        if re.search(r"year|annual|/yr|p\.a", text, re.I):
            per = "year"
        elif re.search(r"week|/wk", text, re.I):
            per = "week"
        elif re.search(r"hour|/hr", text, re.I):
            per = "hour"
        else:
            per = "month"

    nums = [float(n.replace(",", "")) for n in re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", text)]
    if not nums:
        return None, None
    if len(nums) == 1:
        v = _convert_to_aed(_to_monthly(nums[0], per), curr)
        return v, v
    lo = _convert_to_aed(_to_monthly(min(nums[0], nums[1]), per), curr)
    hi = _convert_to_aed(_to_monthly(max(nums[0], nums[1]), per), curr)
    return lo, hi


def salary_from_jsearch(job: dict[str, Any]) -> tuple[str | None, float | None, float | None]:
    raw_bits = []
    for key in ("job_salary_period", "job_min_salary", "job_max_salary", "job_salary_currency"):
        if job.get(key) is not None:
            raw_bits.append(f"{key}={job.get(key)}")
    raw = "; ".join(raw_bits) if raw_bits else None
    lo, hi = parse_salary_to_aed_monthly(
        None,
        min_value=job.get("job_min_salary"),
        max_value=job.get("job_max_salary"),
        currency=job.get("job_salary_currency"),
        period=job.get("job_salary_period"),
    )
    return raw, lo, hi
