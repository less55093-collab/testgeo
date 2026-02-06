"""Provider base class that composes all layers"""

import asyncio
import logging
from dataclasses import dataclass

from ..account_pool.base import AccountPool
from ..auth.base import Authenticator
from ..client.base import AIClient
from ..core.exceptions import (
    AccountBanned,
    AllRetriesFailed,
    NoAccountAvailable,
    RateLimited,
    TokenExpired,
)
from ..core.types import AccountStatus, CallParams, CallResult
from ..parser.base import ResponseParser
from ..session.base import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class Provider:
    """Provider that composes all layers for a platform"""

    name: str
    account_pool: AccountPool
    authenticator: Authenticator
    session_manager: SessionManager
    client: AIClient
    parser: ResponseParser
    max_retries: int = 3

    async def call(self, params: CallParams) -> CallResult:
        """
        Make API call with retry logic.
        Automatically retries with different accounts on failure.
        """
        tried_accounts: list[str] = []
        last_error: Exception | None = None

        for _ in range(self.max_retries + 1):
            result = await self.account_pool.acquire(exclude=tried_accounts)
            if not result:
                raise NoAccountAvailable(tried=tried_accounts)

            account, wait_time = result
            if wait_time > 0:
                await asyncio.sleep(wait_time)

            tried_accounts.append(account.id)

            try:
                # Ensure logged in
                if account.status == AccountStatus.NEED_LOGIN:
                    token = await self.authenticator.login(account)
                    account.token = token
                    account.status = AccountStatus.LOGGED_IN

                if account.token is None:
                    raise TokenExpired("No valid token after login")

                # Prepare session
                session_data = await self.session_manager.prepare(
                    account, account.token
                )

                # Make call
                raw = await self.client.call(params, account.token, session_data)

                # Parse response
                return await self.parser.parse(raw)

            except TokenExpired as e:
                await self.account_pool.mark_status(
                    account, AccountStatus.NEED_LOGIN
                )
                last_error = e
                # Continue to retry with different account

            except AccountBanned as e:
                await self.account_pool.mark_status(account, AccountStatus.BANNED)
                last_error = e
                # Continue to retry with different account

            except RateLimited as e:
                await self.account_pool.mark_status(
                    account, AccountStatus.RATE_LIMITED
                )
                last_error = e
                # Continue to retry with different account

            finally:
                await self.account_pool.release(account)

        # All retries exhausted
        raise AllRetriesFailed(attempts=len(tried_accounts), last_error=last_error)
