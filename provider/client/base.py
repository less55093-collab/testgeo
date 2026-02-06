"""AI client protocol"""

from typing import Protocol

from ..core.types import CallParams


class AIClient(Protocol):
    """Protocol for AI API client"""

    async def call(self, params: CallParams, token: str, session_data: dict) -> str:
        """
        Make API call and return raw response as string.
        """
        ...
