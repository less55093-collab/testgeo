"""Passthrough parser that returns raw response"""

from ..core.types import CallResult


class PassthroughParser:
    """Parser that wraps raw response in CallResult without modification"""

    async def parse_response(self, raw_response: str) -> CallResult:
        """Parse raw response (passthrough implementation)"""
        return CallResult(
            raw_response=raw_response,
            content=raw_response,
            reasoning=None,
            sources=[],
            rankings=[],
            metadata={},
        )

    async def parse_content(self, result: CallResult) -> CallResult:
        """Parse content (passthrough implementation - no-op)"""
        return result

    async def parse(self, raw_response: str) -> CallResult:
        """Full parse pipeline (passthrough implementation)"""
        result = await self.parse_response(raw_response)
        return await self.parse_content(result)
