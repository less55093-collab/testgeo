"""Login manager for manual auth flows"""

import asyncio

from ..account_pool.base import AccountPool
from ..auth.base import Authenticator
from ..core.types import Account, AccountStatus, LoginSession


class LoginManager:
    """Manages background login processes for accounts needing manual auth"""

    def __init__(self, authenticator: Authenticator, account_pool: AccountPool):
        self._authenticator = authenticator
        self._account_pool = account_pool
        self._active_logins: dict[str, asyncio.Task] = {}

    async def start_login(self, account: Account) -> LoginSession:
        """Start a login session, returns session with captcha/QR data"""
        if account.id in self._active_logins:
            self._active_logins[account.id].cancel()

        session = await self._authenticator.initiate_login(account)
        task = asyncio.create_task(self._monitor_login(account, session))
        self._active_logins[account.id] = task
        return session

    async def _monitor_login(self, account: Account, session: LoginSession):
        """Monitor login session, handle expiry"""
        try:
            while not session.is_complete:
                if session.is_expired:
                    # Captcha/QR expired, reset account state
                    await self._account_pool.mark_status(
                        account, AccountStatus.NEED_LOGIN
                    )
                    return
                await asyncio.sleep(1)

            # Login successful
            account.token = session.token
            await self._account_pool.mark_status(account, AccountStatus.LOGGED_IN)

        except asyncio.CancelledError:
            pass
        finally:
            self._active_logins.pop(account.id, None)

    async def submit_captcha(self, account_id: str, captcha: str) -> bool:
        """Submit captcha solution - platform-specific implementation needed"""
        raise NotImplementedError("Platform-specific captcha submission required")

    def get_active_logins(self) -> dict[str, asyncio.Task]:
        """Get currently active login sessions"""
        return self._active_logins.copy()
