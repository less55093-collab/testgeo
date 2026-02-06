"""Doubao (豆包) provider class with web search capability"""

import json
import logging
import httpx
import time
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from llm import create_random_llm_wrapper

from ...core.types import (
    Account,
    AccountStatus,
    CallParams,
    CallResult,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class DoubaoRateLimiter:
    """Simple rate limiter for Doubao API"""
    max_requests_per_period: int = 60
    period_seconds: float = 60.0
    request_timestamps: list = field(default_factory=list)
    
    def can_request(self) -> bool:
        """Check if we can make a request"""
        now = time.time()
        # Clean old timestamps
        self.request_timestamps = [
            t for t in self.request_timestamps if now - t < self.period_seconds
        ]
        return len(self.request_timestamps) < self.max_requests_per_period
    
    async def wait_for_slot(self):
        """Wait until a request slot is available"""
        while not self.can_request():
            await asyncio.sleep(1.0)
        self.request_timestamps.append(time.time())


class Doubao:
    """Doubao AI provider using Volcengine Ark API with web search capability"""

    def __init__(self, config_path: str = "config.json"):
        """
        Initialize Doubao provider from config file.

        Args:
            config_path: Path to config.json file
        """
        # Load config
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        provider_config = config.get("providers", {}).get("doubao", {})
        if not provider_config:
            raise ValueError("Doubao config not found in config file")

        # Get API key
        accounts = provider_config.get("accounts", [])
        if not accounts or not accounts[0].get("api_key"):
            raise ValueError("Doubao API key not found in config")
        
        self.api_key = accounts[0]["api_key"]
        self.model = provider_config.get("model", "doubao-pro-32k")
        self.endpoint_id = provider_config.get("endpoint_id", "")
        
        if not self.endpoint_id:
            raise ValueError("Doubao Endpoint ID (接入点 ID) is required. Please configure it in settings.")
            
        self.base_url = provider_config.get("base_url", "https://ark.cn-beijing.volces.com/api/v3/")
        
        # Rate limiter
        rate_limit_data = provider_config.get("rate_limit", {})
        self.rate_limiter = DoubaoRateLimiter(
            max_requests_per_period=rate_limit_data.get("max_requests_per_period", 60),
            period_seconds=rate_limit_data.get("period_seconds", 60.0)
        )
        
        # Create LLM wrapper for parsing rankings
        self.llm_wrapper = create_random_llm_wrapper(config_path)
        
        logger.info(f"Doubao provider initialized with endpoint: {self.endpoint_id}")

    async def call(self, params: CallParams) -> CallResult:
        """
        Make API call to Doubao with web search enabled.
        """
        await self.rate_limiter.wait_for_slot()
        
        # Prepare messages
        if isinstance(params.messages, str):
            messages = [{"role": "user", "content": params.messages}]
        elif isinstance(params.messages, list):
            messages = params.messages
        else:
            messages = [{"role": "user", "content": str(params.messages)}]
        
        # Build request payload with web search
        payload = {
            "model": self.endpoint_id or self.model,
            "messages": messages,
            "stream": False,
        }
        
        # Enable web search if requested
        # Note: If using a specific Bot (endpoint_id starts with 'bot-'), it likely handles search internally.
        # We should not inject tools in that case to avoid conflicts.
        is_bot = str(self.endpoint_id).startswith("bot-") or "/bots" in self.base_url
        
        if params.enable_search and not is_bot:
            payload["tools"] = [
                {
                    "type": "web_search",
                    "web_search": {
                        "enable": True,
                        "search_query": messages[-1].get("content", "") if messages else ""
                    }
                }
            ]
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                if response.status_code != 200:
                    logger.error(f"Doubao Error: {response.text}")
                response.raise_for_status()
                result = response.json()
            
            # Parse response
            return await self._parse_response(result, params)
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Doubao API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Doubao call failed: {e}")
            raise

    async def _parse_response(self, raw_response: dict, params: CallParams) -> CallResult:
        """Parse Doubao API response and extract content, sources, rankings"""
        
        content = ""
        sources = []
        reasoning = None
        
        # Extract main content
        choices = raw_response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            
            # Check for Bot API references (top-level 'references' field)
            references = raw_response.get("references", [])
            for ref in references:
                sources.append({
                    "title": ref.get("title", ""),
                    "url": ref.get("url", ""),
                    "snippet": ref.get("content", "") or ref.get("snippet", ""), 
                    "source": "doubao_bot"
                })
            
            # Check for tool calls (web search results)
            tool_calls = message.get("tool_calls", [])
            for tool_call in tool_calls:
                if tool_call.get("type") == "web_search":
                    # Parse web search results
                    search_results = tool_call.get("web_search", {}).get("results", [])
                    for result in search_results:
                        sources.append({
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "snippet": result.get("snippet", ""),
                            "source": "doubao_search"
                        })
        
        # Extract citations from content if present
        if "【" in content and "】" in content:
            sources.extend(self._extract_inline_citations(content))
        
        # Parse rankings using LLM if content is available
        rankings = []
        if content and self.llm_wrapper:
            try:
                rankings = await self._extract_rankings(content)
            except Exception as e:
                logger.warning(f"Failed to extract rankings: {e}")
        
        return CallResult(
            raw_response=raw_response,
            content=content,
            reasoning=reasoning,
            sources=sources,
            rankings=rankings,
            metadata={
                "model": raw_response.get("model", self.model),
                "usage": raw_response.get("usage", {}),
                "search_enabled": params.enable_search,
            }
        )

    def _extract_inline_citations(self, content: str) -> list[dict]:
        """Extract inline citations from content like 【1】、【2】"""
        import re
        
        citations = []
        pattern = r'【(\d+)】([^【]*?)(?=【|\Z)'
        matches = re.findall(pattern, content)
        
        for idx, text in matches:
            citations.append({
                "index": int(idx),
                "text": text.strip()[:200],
                "source": "inline_citation"
            })
        
        return citations

    async def _extract_rankings(self, content: str) -> list[dict]:
        """Use LLM to extract product/brand rankings from content"""
        
        prompt = f"""请从以下AI回复中提取产品/品牌排名信息。

回复内容:
{content}

请以JSON格式返回排名列表，格式如下:
[
  {{"rank": 1, "name": "产品名称", "reason": "推荐理由"}},
  {{"rank": 2, "name": "产品名称", "reason": "推荐理由"}}
]

如果没有明确的排名信息，返回空列表 []。
只返回JSON，不要其他文字。"""

        try:
            result = await asyncio.to_thread(
                self.llm_wrapper.chat,
                [{"role": "user", "content": prompt}]
            )
            
            # Parse JSON from response
            response_text = result.choices[0].message.content
            
            # Extract JSON array
            import re
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                rankings = json.loads(json_match.group())
                return rankings
            
            return []
            
        except Exception as e:
            logger.warning(f"Failed to parse rankings: {e}")
            return []

    async def search(self, query: str, enable_analysis: bool = True) -> CallResult:
        """
        Convenience method for web search with optional analysis.
        
        Args:
            query: Search query
            enable_analysis: Whether to analyze and rank results
            
        Returns:
            CallResult with search results and analysis
        """
        params = CallParams(
            messages=[{"role": "user", "content": query}],
            enable_thinking=False,
            enable_search=True,
        )
        
        return await self.call(params)
