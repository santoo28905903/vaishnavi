from __future__ import annotations

import re

UAE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bUAE\b",
        r"U\.A\.E\.?",
        r"United Arab Emirates",
        r"\bDubai\b",
        r"Abu Dhabi",
        r"Abudhabi",
        r"\bSharjah\b",
        r"\bAjman\b",
        r"Ras Al Khaimah",
        r"\bRAK\b",
        r"Umm Al Quwain",
        r"Fujairah",
        r"\bDXB\b",
        r"\bAUH\b",
    ]
]

# Locations that mention MENA/Gulf but are not UAE-specific enough alone.
WEAK_REGIONAL = re.compile(r"\b(MENA|Middle East|Gulf|GCC)\b", re.IGNORECASE)


def is_uae_location(text: str | None) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in UAE_PATTERNS)


def normalize_locations(text: str | None) -> list[str]:
    if not text:
        return []
    parts = re.split(r"[;/|]| - |,", text)
    cleaned = [p.strip() for p in parts if p and p.strip()]
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in cleaned:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def location_mentions_uae_or_regional(text: str | None) -> bool:
    if is_uae_location(text):
        return True
    if text and WEAK_REGIONAL.search(text):
        # Accept MENA/Gulf only when UAE city also present elsewhere — already handled.
        # For soft prefilter on boards we still require UAE patterns.
        return False
    return False
