"""HTTP clients with retries and polite rate limiting."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter


@dataclass(slots=True)
class RateLimiter:
    delay_seconds: float
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _last_call: float = 0.0

    async def wait(self) -> None:
        if self.delay_seconds <= 0:
            return
        async with self._lock:
            now = asyncio.get_running_loop().time()
            wait_for = self.delay_seconds - (now - self._last_call)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_call = asyncio.get_running_loop().time()


class AsyncHttpClient:
    def __init__(self, *, timeout: float, user_agent: str, rate_limit_seconds: float = 0.0):
        self.rate_limiter = RateLimiter(rate_limit_seconds)
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json,text/csv,*/*;q=0.8",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        wait=wait_exponential_jitter(initial=1.0, max=30),
        stop=stop_after_attempt(10),
        reraise=True,
    )
    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        await self.rate_limiter.wait()
        response = await self.client.get(url, **kwargs)
        response.raise_for_status()
        return response

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        wait=wait_exponential_jitter(initial=1.0, max=30),
        stop=stop_after_attempt(10),
        reraise=True,
    )
    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.get(url, **kwargs)
        try:
            return response.json()
        except Exception as exc:
            raise httpx.HTTPError(f"Non-JSON response from {url}: {exc}") from exc

    async def __aenter__(self) -> "AsyncHttpClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
