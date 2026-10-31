from aiogram.exceptions import (
    TelegramEntityTooLarge,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)

from ...errors import failure_kind as shared_failure_kind


def failure_kind(exc: Exception) -> str:
    if isinstance(exc, TelegramEntityTooLarge):
        return "failure_size"
    if isinstance(exc, (TelegramUnauthorizedError, TelegramForbiddenError)):
        return "failure_access"
    if isinstance(exc, (TelegramNetworkError, TelegramServerError, TelegramRetryAfter)):
        return "failure_network"
    return shared_failure_kind(exc)


def retry_delay(exc: Exception, attempt: int) -> float | None:
    delay = (2.0, 5.0)[attempt - 1]
    if isinstance(exc, TelegramEntityTooLarge):
        return None
    if isinstance(exc, TelegramRetryAfter):
        return max(delay, float(exc.retry_after)) if exc.retry_after <= 30 else None
    if isinstance(exc, (TelegramNetworkError, TelegramServerError)):
        return delay
    return None
