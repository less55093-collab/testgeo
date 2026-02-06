"""Authenticator protocol"""

from typing import Protocol

from ..core.types import Account, LoginSession


class Authenticator(Protocol):
    """Protocol for account authentication"""

    async def login(self, account: Account) -> str:
        """
        Login and return token. Raises LoginRequired if needs manual intervention.
        """
        ...

    async def refresh(self, account: Account) -> str | None:
        """
        Try to refresh token. Returns None if needs full re-login.
        """
        ...

    def needs_manual_login(self) -> bool:
        """Whether this auth method requires user interaction"""
        ...

    async def initiate_login(self, account: Account) -> LoginSession:
        """
        Initiate manual login process (for captcha/QR flows).
        Returns LoginSession with captcha/QR data.
        """
        ...
