"""Custom exceptions for AI backend framework"""

from typing import Any


class AIBackendError(Exception):
    """Base exception for AI backend framework"""

    pass


class NoAccountAvailable(AIBackendError):
    """No account available in pool"""

    def __init__(self, tried: list[str] | None = None):
        self.tried = tried or []
        super().__init__(
            f"No account available. Tried accounts: {', '.join(self.tried) if self.tried else 'none'}"
        )


class TokenExpired(AIBackendError):
    """Account token expired"""

    def __init__(self, account_id: str):
        self.account_id = account_id
        super().__init__(f"Token expired for account: {account_id}")


class AccountBanned(AIBackendError):
    """Account has been banned"""

    def __init__(self, account_id: str, reason: str | None = None):
        self.account_id = account_id
        self.reason = reason
        msg = f"Account banned: {account_id}"
        if reason:
            msg += f" (reason: {reason})"
        super().__init__(msg)


class RateLimited(AIBackendError):
    """Account is rate limited"""

    def __init__(self, account_id: str, retry_after: float | None = None):
        self.account_id = account_id
        self.retry_after = retry_after
        msg = f"Rate limited for account: {account_id}"
        if retry_after:
            msg += f" (retry after: {retry_after}s)"
        super().__init__(msg)


class AllRetriesFailed(AIBackendError):
    """All retry attempts failed"""

    def __init__(self, attempts: int, last_error: Exception | None = None):
        self.attempts = attempts
        self.last_error = last_error
        msg = f"All {attempts} retry attempts failed"
        if last_error:
            msg += f". Last error: {last_error}"
        super().__init__(msg)


class LoginRequired(AIBackendError):
    """Manual login required"""

    def __init__(self, account_id: str, login_type: str):
        self.account_id = account_id
        self.login_type = login_type
        super().__init__(
            f"Manual {login_type} login required for account: {account_id}"
        )


class APIError(AIBackendError):
    """API call error"""

    def __init__(self, status_code: int, detail: str, response: Any = None):
        self.status_code = status_code
        self.detail = detail
        self.response = response
        super().__init__(f"API error {status_code}: {detail}")
