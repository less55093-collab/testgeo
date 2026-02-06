"""No-op session manager for platforms without sessions"""

from ..core.types import Account


class NoOpSessionManager:
    """Session manager that does nothing"""

    async def prepare(self, account: Account, token: str) -> dict:
        """Returns empty dict"""
        return {}
