"""JSON file token storage implementation"""

import asyncio
import json
from pathlib import Path

from ..core.types import Account


class JsonFileTokenStorage:
    """Store tokens in a JSON file"""

    def __init__(self, path: str):
        self._path = Path(path)
        self._lock = asyncio.Lock()

    async def _read_file(self) -> dict[str, str]:
        """Read tokens from file"""
        if not self._path.exists():
            return {}

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    async def _write_file(self, data: dict[str, str]) -> None:
        """Write tokens to file"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def load(self, account_id: str) -> str | None:
        """Load token for account"""
        async with self._lock:
            data = await self._read_file()
            return data.get(account_id)

    async def save(self, account: Account) -> None:
        """Save account token"""
        if account.token is None:
            return

        async with self._lock:
            data = await self._read_file()
            data[account.id] = account.token
            await self._write_file(data)

    async def load_all(self) -> dict[str, str]:
        """Load all tokens"""
        async with self._lock:
            return await self._read_file()

    def load_all_sync(self) -> dict[str, str]:
        """Load all tokens synchronously (for initialization)"""
        if not self._path.exists():
            return {}

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
