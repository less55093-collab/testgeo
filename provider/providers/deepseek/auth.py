"""DeepSeek authenticator"""

import logging

from curl_cffi import requests

from ...core.exceptions import APIError, LoginRequired
from ...core.types import Account, LoginSession

logger = logging.getLogger(__name__)

DEEPSEEK_HOST = "chat.deepseek.com"
DEEPSEEK_LOGIN_URL = f"https://{DEEPSEEK_HOST}/api/v0/users/login"
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


class DeepSeekAuthenticator:
    """DeepSeek API login authenticator"""

    async def login(self, account: Account) -> str:
        """Login via email/mobile + password"""
        email = account.credentials.get("email", "").strip()
        mobile = account.credentials.get("mobile", "").strip()
        password = account.credentials.get("password", "").strip()

        if not password or (not email and not mobile):
            raise APIError(
                status_code=400,
                detail="Account missing required login info (email or mobile + password)",
            )

        if email:
            payload = {
                "email": email,
                "password": password,
                "device_id": "Deepseek",
                "os": "android",
            }
        else:
            payload = {
                "mobile": mobile,
                "area_code": None,
                "password": password,
                "device_id": "Deepseek",
                "os": "android",
            }

        try:
            resp = requests.post(
                DEEPSEEK_LOGIN_URL,
                headers=BASE_HEADERS,
                json=payload,
                impersonate="chrome",
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[DeepSeek login] Request failed: {e}")
            raise APIError(status_code=500, detail=f"Account login failed: {e}")

        try:
            logger.info(f"[DeepSeek login] Response: {resp.text}")
            data = resp.json()
        except Exception as e:
            logger.error(f"[DeepSeek login] JSON parse failed: {e}")
            raise APIError(
                status_code=500, detail="Account login failed: invalid JSON response"
            )

        if (
            data.get("data") is None
            or data["data"].get("biz_data") is None
            or data["data"]["biz_data"].get("user") is None
        ):
            logger.error(f"[DeepSeek login] Invalid response format: {data}")
            raise APIError(
                status_code=500, detail="Account login failed: invalid response format"
            )

        new_token = data["data"]["biz_data"]["user"].get("token")
        if not new_token:
            logger.error(f"[DeepSeek login] Missing token in response: {data}")
            raise APIError(
                status_code=500, detail="Account login failed: missing token"
            )

        return new_token

    async def refresh(self, account: Account) -> str | None:
        """DeepSeek doesn't support token refresh"""
        return None

    def needs_manual_login(self) -> bool:
        """DeepSeek uses API login, no manual intervention needed"""
        return False

    async def initiate_login(self, account: Account) -> LoginSession:
        """Not needed for DeepSeek (API login only)"""
        raise LoginRequired(account.id, "api")
