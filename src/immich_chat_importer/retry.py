import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

RetryNotice = Callable[[str, int, float], Awaitable[None]]
retry_notice: ContextVar[RetryNotice | None] = ContextVar("retry_notice", default=None)


def _delay(exc: Exception, attempt: int) -> float | None:
    delay = (2.0, 5.0)[attempt - 1]
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return delay
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (500, 502, 503, 504):
            return delay
        if code == 429:
            try:
                wait = float(exc.response.headers.get("Retry-After", delay))
            except ValueError:
                try:
                    wait = (
                        parsedate_to_datetime(exc.response.headers["Retry-After"])
                        - datetime.now(UTC)
                    ).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    wait = delay
            return max(delay, wait) if wait <= 30 else None
    return None


async def retry[T](
    operation: Callable[[], Awaitable[T]],
    stage: str,
    *,
    delay_for: Callable[[Exception, int], float | None] = _delay,
) -> T:
    for attempt in range(1, 4):
        notice = retry_notice.get()
        if notice:
            await notice(stage, attempt, 0)
        try:
            return await operation()
        except Exception as exc:
            delay = delay_for(exc, attempt) if attempt < 3 else None
            if delay is None:
                raise
            if notice:
                await notice(stage, attempt + 1, delay)
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


async def report_stage(stage: str) -> None:
    notice = retry_notice.get()
    if notice:
        await notice(stage, 0, 0)
