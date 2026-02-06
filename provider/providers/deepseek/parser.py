"""DeepSeek response parser"""

import json
import logging
import re

from llm import OpenAIWrapper
from ...core.types import CallResult

logger = logging.getLogger(__name__)


RANKING_EXTRACTION_PROMPT = """请从以下内容中提取产品或平台的排名信息。内容中包含 [citation:X] 标记表示引用编号。

内容：
{content}

要求：
1. 提取所有提到的产品或平台名称
2. 根据文本中的顺序确定排名
3. 如果有并排的情况，rank相同；后续的rank不会因为有并排的rank就加一，而是保持为原始的rank
4. 找出每个产品对应的citation编号（例如 [citation:1] 表示引用编号1）
5. 如果某个产品没有source，则不包含source这一项
6. 如果原始文本中没有出现企业名称，则不输出任何字符

输出格式（每行一个产品，使用分号分隔字段）：
平台名;rank:排名;source:引用编号1,引用编号2

示例输出：
FOR U 健身私教馆;rank:1;source:1,2
角马私教;rank:1;source:5
人鱼线健身工作室;rank:2;source:3

请只输出结果，不要包含任何解释文字。如果没有找到产品，请返回空字符串。
"""


class DeepSeekParser:
    """Parser for DeepSeek SSE streaming responses"""

    def __init__(self, llm_wrapper: OpenAIWrapper | None = None):
        """Initialize parser

        Args:
            llm_wrapper: Optional OpenAI wrapper for ranking extraction
        """
        self.llm_wrapper = llm_wrapper

    async def parse_response(self, raw_response: str) -> CallResult:
        """Parse DeepSeek SSE stream to extract content and sources

        Args:
            raw_response: Raw SSE stream string from DeepSeek API

        Returns:
            CallResult with content and sources extracted, rankings empty
        """
        content_parts = []
        sources = []
        collecting_content = False

        # Split by SSE message separator
        messages = raw_response.strip().split('\n\n')

        for message in messages:
            if not message.strip():
                continue

            # Parse message
            event, data_dict = self._parse_message(message)

            # Check for finish event
            if event == 'finish':
                break

            # Extract search results
            if data_dict and data_dict.get('p') == 'response/search_results':
                v_value = data_dict.get('v')
                if isinstance(v_value, list):
                    sources = v_value
                    logger.debug(f"Found {len(sources)} search results")
                continue

            # Extract content parts
            if data_dict and 'v' in data_dict:
                v_value = data_dict['v']
                p_value = data_dict.get('p', '')

                # Start collecting when we see response/content
                if p_value == 'response/content':
                    collecting_content = True

                # Collect content text (only if no 'p' field or p='response/content')
                if collecting_content and isinstance(v_value, str):
                    if not p_value or p_value == 'response/content':
                        content_parts.append(v_value)

        # Join content parts
        content = ''.join(content_parts).strip()

        return CallResult(
            raw_response=raw_response,
            content=content,
            sources=sources,
        )

    async def parse_content(self, result: CallResult) -> CallResult:
        """Extract rankings from content using LLM

        Args:
            result: CallResult from parse_response with content and sources

        Returns:
            Complete CallResult with rankings extracted
        """
        if not self.llm_wrapper:
            logger.warning("No LLM wrapper provided, skipping ranking extraction")
            return result

        if not result.content:
            logger.debug("No content to parse for rankings")
            return result

        # Build prompt with content only
        prompt = RANKING_EXTRACTION_PROMPT.format(content=result.content)

        # Call LLM
        try:
            logger.info("Calling LLM for ranking extraction...")
            llm_response = await self.llm_wrapper.call(prompt)
            logger.debug(f"LLM response: {llm_response}")

            # Parse LLM response into rankings
            rankings = self._parse_ranking_response(llm_response, result.sources)

            # Update result
            result.rankings = rankings

        except Exception as e:
            logger.error(f"Failed to extract rankings: {e}")
            # Don't fail the whole parse, just leave rankings empty

        return result

    async def parse(self, raw_response: str) -> CallResult:
        """Full parse pipeline: response -> content extraction -> ranking extraction

        Args:
            raw_response: Raw response from API

        Returns:
            Complete CallResult with content, sources, and rankings
        """
        result = await self.parse_response(raw_response)
        return await self.parse_content(result)

    def _parse_message(self, message: str) -> tuple[str | None, dict | None]:
        """Parse a single SSE message

        Args:
            message: Single SSE message string

        Returns:
            Tuple of (event_type, data_dict)
        """
        event = None
        data_dict = None

        lines = message.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Parse event line
            if line.startswith('event:'):
                event = line[6:].strip()

            # Parse data line
            elif line.startswith('data:'):
                data_str = line[5:].strip()
                if data_str and data_str != '{}':
                    try:
                        data_dict = json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.debug(f"Failed to parse JSON: {data_str}")

        return event, data_dict

    def _parse_ranking_response(
        self, llm_response: str, sources: list[dict]
    ) -> list[dict]:
        """Parse LLM response into structured rankings

        Args:
            llm_response: Response from LLM in format "name;rank:X;source:Y,Z"
            sources: Original sources list to copy from

        Returns:
            List of ranking dictionaries
        """
        rankings = []

        # Split by lines
        lines = llm_response.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Parse line format: "name;rank:X;source:Y,Z"
            parts = line.split(';')
            if len(parts) < 2:
                logger.warning(f"Invalid ranking line: {line}")
                continue

            ranking_dict = {}

            # First part is the name
            ranking_dict['name'] = parts[0].strip()

            # Parse remaining parts
            for part in parts[1:]:
                part = part.strip()
                if ':' in part:
                    key, value = part.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    if key == 'rank':
                        try:
                            ranking_dict['rank'] = int(value)
                        except ValueError:
                            logger.warning(f"Invalid rank value: {value}")

                    elif key == 'source':
                        # Parse source indices
                        source_indices = []
                        for idx_str in value.split(','):
                            try:
                                idx = int(idx_str.strip())
                                source_indices.append(idx)
                            except ValueError:
                                logger.warning(f"Invalid source index: {idx_str}")

                        # Copy source objects from original sources
                        ranking_dict['sources'] = []
                        for idx in source_indices:
                            # Sources are 1-indexed in citation
                            if 1 <= idx <= len(sources):
                                ranking_dict['sources'].append(sources[idx - 1])
                            else:
                                logger.warning(f"Source index out of range: {idx}")

            # Add to rankings if we have at least name and rank
            if 'name' in ranking_dict and 'rank' in ranking_dict:
                rankings.append(ranking_dict)

        return rankings
