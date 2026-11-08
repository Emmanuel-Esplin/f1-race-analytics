"""Polite JSON client shared by the Jolpica and OpenF1 ingesters."""

from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

USER_AGENT = "f1-race-analytics/0.1 (+https://github.com/Emmanuel-Esplin/f1-race-analytics)"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OutOfTimeError(RuntimeError):
    """The caller's time budget is spent. Files already written are kept; rerun to continue."""


class LiveSessionLockError(RuntimeError):
    """OpenF1 refuses anonymous requests, even for past sessions, while a session is live."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


class ApiClient:
    """GETs JSON with a minimum gap between requests and retries on transient errors."""

    def __init__(
        self,
        base_url: str,
        min_interval_s: float,
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        deadline: float | None = None,
    ) -> None:
        # `transport` lets tests swap in httpx.MockTransport instead of the network.
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout_s,
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        )
        self._min_interval_s = min_interval_s
        self._last_request = 0.0
        # time.monotonic() value after which no new request starts (Lambda has a hard limit).
        self._deadline = deadline

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self._http.close()

    def _wait_turn(self) -> None:
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise OutOfTimeError("time budget spent")
        # Sleeping before each call keeps us under the documented hourly limits.
        gap = time.monotonic() - self._last_request
        if gap < self._min_interval_s:
            time.sleep(self._min_interval_s - gap)
        self._last_request = time.monotonic()

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=5, max=300),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Return the decoded JSON body of GET `path`."""
        self._wait_turn()
        response = self._http.get(path, params=params)
        if response.status_code in (401, 403) and "Live F1 session" in response.text:
            raise LiveSessionLockError(response.text)
        response.raise_for_status()
        return response.json()
