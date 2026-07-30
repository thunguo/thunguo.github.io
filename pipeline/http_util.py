"""带重试的 HTTP 抓取：网络抖动/超时自动退避重试。"""
from __future__ import annotations

import time

import httpx


def get_with_retry(url: str, *, retries: int = 2, timeout: float = 45.0,
                   backoff: float = 2.0, **kw) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = httpx.get(url, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise last  # type: ignore[misc]
