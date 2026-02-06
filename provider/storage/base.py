"""Token storage protocol"""

from typing import Protocol

from ..core.types import Account


class TokenStorage(Protocol):
    """Protocol for token persistence"""

    async def load(self, account_id: str) -> str | None:
        """Load token for account"""
        ...

    async def save(self, account: Account) -> None:
        """Save account token"""
        ...

    async def load_all(self) -> dict[str, str]:
        """Load all tokens"""
        ...
