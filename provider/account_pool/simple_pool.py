"""Simple account pool implementation with rate limiting"""

import asyncio
import time

from ..core.types import Account, AccountStatus, RateLimitConfig
from ..storage.base import TokenStorage


class SimpleAccountPool:
    """Account pool with rate limiting and token persistence"""

    def __init__(
        self,
        accounts: list[Account],
        rate_limit: RateLimitConfig,
        token_storage: TokenStorage,
    ):
        self._accounts = {a.id: a for a in accounts}
        self._rate_limit = rate_limit
        self._token_storage = token_storage
        self._lock = asyncio.Lock()

    def _is_rate_limited(self, account: Account) -> bool:
        """Check if account has exceeded rate limit"""
        now = time.time()
        cutoff = now - self._rate_limit.period_seconds
        # Clean old timestamps
        account.request_timestamps = [
            ts for ts in account.request_timestamps if ts > cutoff
        ]
        return (
            len(account.request_timestamps) >= self._rate_limit.max_requests_per_period
        )

    def _get_wait_time(self, account: Account) -> float:
        """Get time to wait before next request"""
        if not account.request_timestamps:
            return 0.0
        time_since_last = time.time() - account.request_timestamps[-1]
        return max(0, self._rate_limit.min_delay_between_requests - time_since_last)

    async def acquire(
        self, exclude: list[str] | None = None
    ) -> tuple[Account, float] | None:
        """Returns (account, wait_time) or None if no account available"""
        exclude = exclude or []
        async with self._lock:
            best_account = None
            best_wait = float("inf")

            for acc in self._accounts.values():
                if acc.id in exclude:
                    continue
                # Skip accounts that are in use or have bad status
                if acc.in_use:
                    continue
                if acc.status in (AccountStatus.BANNED, AccountStatus.RATE_LIMITED, AccountStatus.ERROR):
                    continue
                if self._is_rate_limited(acc):
                    continue

                wait = self._get_wait_time(acc)
                if wait < best_wait:
                    best_wait = wait
                    best_account = acc

            if best_account:
                best_account.in_use = True
                return best_account, best_wait

        return None

    async def release(self, account: Account, record_request: bool = True) -> None:
        """Release account back to pool"""
        async with self._lock:
            if record_request:
                account.request_timestamps.append(time.time())
            account.in_use = False
            # Persist token if changed
            await self._token_storage.save(account)

    async def mark_status(self, account: Account, status: AccountStatus) -> None:
        """Update account status"""
        async with self._lock:
            account.status = status

    async def get_accounts_needing_login(self) -> list[Account]:
        """Get accounts that need manual login"""
        async with self._lock:
            return [
                acc
                for acc in self._accounts.values()
                if acc.status
                in (AccountStatus.NEED_CAPTCHA, AccountStatus.NEED_QRCODE)
            ]
