"""DeepSeek API client"""

import logging

from curl_cffi import requests

from ...core.exceptions import APIError
from ...core.types import CallParams

logger = logging.getLogger(__name__)

DEEPSEEK_HOST = "chat.deepseek.com"
DEEPSEEK_COMPLETION_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat/completion"
BASE_HEADERS = {
    "Host": "chat.deepseek.com",
    "User-Agent": "DeepSeek/1.0.13 Android/35",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "x-client-platform": "android",
    "x-client-version": "1.3.0-auto-resume",
    "x-client-locale": "zh_CN",
    "accept-charset": "UTF-8",
}


class DeepSeekClient:
    """DeepSeek completion API client"""

    async def call(self, params: CallParams, token: str, session_data: dict) -> str:
        """Make completion API call"""
        session_id = session_data.get("session_id")
        pow_response = session_data.get("pow_response")

        if not session_id or not pow_response:
            raise APIError(
                status_code=500,
                detail="Missing session_id or pow_response in session_data",
            )

        headers = {
            **BASE_HEADERS,
            "authorization": f"Bearer {token}",
            "x-ds-pow-response": pow_response,
        }

        payload = {
            "chat_session_id": session_id,
            "parent_message_id": None,
            "prompt": params.messages,
            "ref_file_ids": [],
            "thinking_enabled": params.enable_thinking,
            "search_enabled": params.enable_search,
        }

        # Merge extra params
        if params.extra:
            payload.update(params.extra)

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                resp = requests.post(
                    DEEPSEEK_COMPLETION_URL,
                    headers=headers,
                    json=payload,
                    stream=True,
                    impersonate="chrome",
                )
            except Exception as e:
                logger.warning(
                    f"[DeepSeek completion] Request failed (attempt {attempt + 1}): {e}"
                )
                if attempt == max_attempts - 1:
                    raise APIError(
                        status_code=500, detail=f"Completion request failed: {e}"
                    )
                continue

            if resp.status_code == 200:
                # Read and concatenate the entire SSE stream
                logger.info("[DeepSeek completion] Reading SSE stream...")
                all_content = ""
                try:
                    for line in resp.iter_lines():
                        line_str = (
                            line.decode("utf-8") if isinstance(line, bytes) else line
                        )
                        all_content += line_str + "\n"
                        logger.info(f"[SSE] {line_str}")
                except Exception as e:
                    logger.error(f"[DeepSeek completion] Error reading stream: {e}")
                finally:
                    resp.close()

                # Return the concatenated string
                return all_content
            else:
                logger.warning(
                    f"[DeepSeek completion] Failed with status {resp.status_code} (attempt {attempt + 1})"
                )
                resp.close()
                if attempt == max_attempts - 1:
                    raise APIError(
                        status_code=resp.status_code,
                        detail=f"Completion failed with status {resp.status_code}",
                    )

        raise APIError(status_code=500, detail="Completion failed after max retries")
