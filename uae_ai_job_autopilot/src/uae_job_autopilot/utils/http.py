from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DEFAULT_HEADERS = {
    "User-Agent": "uae-job-autopilot/0.1 (+phase1-discovery; respectful; no-scrape-bypass)",
    "Accept": "application/json",
}


def make_client(timeout: float | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=timeout or DEFAULT_TIMEOUT,
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
    )


@retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)
def get_json(client: httpx.Client, url: str, **kwargs) -> tuple[int, object]:
    response = client.get(url, **kwargs)
    if response.status_code >= 500:
        response.raise_for_status()
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {"_raw_text": response.text[:500]}
