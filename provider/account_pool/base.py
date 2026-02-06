"""Account pool protocol"""

from typing import Protocol

from ..core.types import Account, AccountStatus


class AccountPool(Protocol):
    """Protocol for managing account pool"""

    async def acquire(
        self, exclude: list[str] | None = None
    ) -> tuple[Account, float] | None:
        """Get an available account, mark as in_use. Returns (account, wait_time) or None"""
        ...

    async def release(self, account: Account, record_request: bool = True) -> None:
        """Return account to pool"""
        ...

    async def mark_status(self, account: Account, status: AccountStatus) -> None:
        """Update account status"""
        ...

    async def get_accounts_needing_login(self) -> list[Account]:
        """Get accounts that need manual login"""
        ...
