"""Response parser protocol"""

from typing import Protocol

from ..core.types import CallResult


class ResponseParser(Protocol):
    """Protocol for parsing API responses"""

    async def parse_response(self, raw_response: str) -> CallResult:
        """Parse raw response string into intermediate format with content and sources

        Args:
            raw_response: Raw response from API

        Returns:
            CallResult with content and sources extracted, but rankings not yet parsed
        """
        ...

    async def parse_content(self, result: CallResult) -> CallResult:
        """Parse content and sources to extract rankings using LLM

        Args:
            result: CallResult from parse_response with content and sources

        Returns:
            Complete CallResult with rankings extracted
        """
        ...

    async def parse(self, raw_response: str) -> CallResult:
        """Full parse pipeline: response -> content extraction -> ranking extraction

        Args:
            raw_response: Raw response from API

        Returns:
            Complete CallResult with content, sources, and rankings
        """
        result = await self.parse_response(raw_response)
        return await self.parse_content(result)
