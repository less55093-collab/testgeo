"""Session manager protocol"""

from typing import Protocol

from ..core.types import Account


class SessionManager(Protocol):
    """Protocol for session management"""

    async def prepare(self, account: Account, token: str) -> dict:
        """
        Prepare session for API call.
        Returns session data (session_id, pow, etc) as dict.
        """
        ...
