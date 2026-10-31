from ...errors import failure_kind as shared_failure_kind


class TelegramError(Exception):
    def __init__(self, code: int, description: str, retry_after: float | None = None):
        super().__init__(description)
        self.code = code
        self.retry_after = retry_after


def failure_kind(exc: Exception) -> str:
    if isinstance(exc, TelegramError):
        if exc.code == 413:
            return "failure_size"
        if exc.code in (401, 403):
            return "failure_access"
        if exc.code == 0 or exc.code == 429 or exc.code >= 500:
            return "failure_network"
    return shared_failure_kind(exc)


def retry_delay(exc: Exception, attempt: int) -> float | None:
    delay = (2.0, 5.0)[attempt - 1]
    if isinstance(exc, TelegramError):
        if exc.code == 429:
            wait = exc.retry_after or delay
            return max(delay, wait) if wait <= 30 else None
        if exc.code == 0 or exc.code >= 500:
            return delay
    return None
