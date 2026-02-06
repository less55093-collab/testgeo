# AI Backend Framework Documentation

A modular, replaceable backend framework for querying AI platforms to analyze product rankings for advertising placement optimization.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Core Concepts](#core-concepts)
- [Implementation Status](#implementation-status)
- [Adding a New Platform](#adding-a-new-platform)
- [Advanced Topics](#advanced-topics)

---

## Overview

### Purpose

Query AI platforms with product-related keywords, analyze which products appear in results and their rankings, identify source platforms, optimize ad placement, and validate effectiveness through re-querying.

### Design Philosophy

- **Protocol-based composition**: Each layer is a Protocol interface allowing easy swapping
- **Separated state management**: Independent tracking of usage, login, and health states
- **Automatic retry**: Transparent account rotation and retry logic
- **Persistent storage**: Tokens survive restarts
- **Platform-agnostic API**: Same interface regardless of backend platform

---

## Quick Start

### Installation

```bash
# Clone repository
cd ai-crawler

# Install dependencies
uv sync
```

### Basic Usage

```python
import asyncio
from provider.providers.deepseek import DeepSeek
from provider.core.types import CallParams

async def main():
    # Direct instantiation
    deepseek = DeepSeek("config.json")

    # Make API call
    params = CallParams(
        messages="What are the best wireless headphones?",
        enable_thinking=False,
        enable_search=True,
    )

    result = await deepseek.call(params)
    print(result.content)

asyncio.run(main())
```

### Configuration

Create `config.json`:

```json
{
  "providers": {
    "deepseek": {
      "accounts": [
        {
          "mobile": "your-mobile-number",
          "password": "your-password",
          "token": null
        }
      ],
      "rate_limit": {
        "max_requests_per_period": 10,
        "period_seconds": 60.0,
        "min_delay_between_requests": 1.0
      },
      "token_storage_path": "data/deepseek_tokens.json",
      "wasm_path": "sha3_wasm_bg.7b9ca65ddd.wasm"
    }
  }
}
```

---

## Architecture

### Layer Structure

```
┌────────────────────────────────────────────────────────┐
│                  Provider (DeepSeek)                   │
│  - Direct instantiation from config                    │
│  - Retry logic & account rotation                      │
└────────────────────────────────────────────────────────┘
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│Account Pool  │  │     Auth     │  │   Session    │
│- Rate limit  │  │  - Login     │  │  - Prepare   │
│- State mgmt  │  │  - Refresh   │  │  - PoW/CSRF  │
└──────────────┘  └──────────────┘  └──────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Client     │  │    Parser    │  │   Storage    │
│- API call    │  │  - Parse     │  │  - Tokens    │
│- Streaming   │  │  - Extract   │  │  - Persist   │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Request Flow

```
User Request
    │
    ├─> Provider.call(CallParams)
    │   ├─> AccountPool.acquire() → Get available account
    │   ├─> Authenticator.login() → Ensure logged in
    │   ├─> SessionManager.prepare() → Create session/PoW
    │   ├─> AIClient.call() → Make streaming API request
    │   └─> ResponseParser.parse() → Parse SSE to string
    └─> CallResult (unified response)
```

### Directory Structure

```
provider/
├── core/
│   ├── types.py         # Account, CallParams, CallResult, State enums
│   └── exceptions.py    # Custom exception hierarchy
├── account_pool/
│   ├── base.py          # AccountPool protocol
│   └── simple_pool.py   # Simple implementation with rate limiting
├── auth/
│   ├── base.py          # Authenticator protocol
│   └── login_manager.py # Manual login session management
├── session/
│   ├── base.py          # SessionManager protocol
│   └── noop.py          # No-op implementation
├── client/
│   └── base.py          # AIClient protocol
├── parser/
│   ├── base.py          # ResponseParser protocol
│   └── passthrough.py   # Simple string passthrough
├── storage/
│   ├── base.py          # TokenStorage protocol
│   └── json_file.py     # JSON file persistence
└── providers/
    ├── base.py          # Provider base class with retry logic
    └── deepseek/
        ├── provider.py  # DeepSeek main class (direct instantiation)
        ├── auth.py      # Mobile/email + password login
        ├── session.py   # Session + PoW computation
        └── client.py    # SSE streaming API client
```

---

## Core Concepts

### Account States (Separated)

Each account has three independent state dimensions:

```python
@dataclass
class Account:
    id: str
    credentials: dict
    token: str | None

    # Three independent states
    in_use: bool = False                           # Usage state
    login_status: LoginStatus = LoginStatus.NEED_LOGIN  # Auth state
    health_status: HealthStatus = HealthStatus.HEALTHY  # Health state
```

**LoginStatus Enum:**
- `LOGGED_IN`: Has valid token
- `NEED_LOGIN`: Needs password login
- `NEED_CAPTCHA`: Needs captcha verification
- `NEED_QRCODE`: Needs QR code scan

**HealthStatus Enum:**
- `HEALTHY`: Account is healthy
- `BANNED`: Account banned by platform
- `RATE_LIMITED`: Temporarily rate limited
- `ERROR`: Unknown error state

**Why Separated?** Mixing usage state (in_use) with login state caused bugs where `acquire()` would overwrite `NEED_LOGIN`, making the system think the account was already logged in.

### Rate Limiting

Per-account rate limiting with three parameters:

```python
RateLimitConfig(
    max_requests_per_period=10,    # Max requests in rolling window
    period_seconds=60.0,            # Rolling time window size
    min_delay_between_requests=1.0  # Minimum gap between requests
)
```

**Implementation:**
- Each account tracks `request_timestamps: list[float]`
- On `acquire()`, pool filters out rate-limited accounts
- Old timestamps outside the window are cleaned up
- Returns wait time if delay needed

### Token Storage

Tokens are persisted to JSON file:

```python
{
  "account_id": "token_value",
  "another_account": "another_token"
}
```

- Thread-safe with async locks
- Auto-creates parent directories
- Loaded synchronously on startup, saved async on changes

### Streaming Responses

All responses are SSE (Server-Sent Events) streams:

```python
# Client returns concatenated string
async def call(...) -> str:
    all_content = ""
    for line in resp.iter_lines():
        if line:
            line_str = line.decode("utf-8")
            all_content += line_str + "\n"
    return all_content

# Parser receives string
def parse(raw_response: str) -> CallResult:
    return CallResult(content=raw_response, ...)
```

---

## Implementation Status

### ✅ Completed

#### Core Framework (100%)
- [x] Type definitions with separated account states
- [x] Exception hierarchy
- [x] Account pool with rate limiting
- [x] Token persistence
- [x] Provider composition with retry logic
- [x] All protocol definitions

#### DeepSeek Provider (100%)
- [x] Mobile/email + password login
- [x] Session creation
- [x] PoW (proof-of-work) computation via WASM
- [x] SSE streaming API client
- [x] Direct instantiation: `DeepSeek("config.json")`
- [x] Parameters: `enable_thinking`, `enable_search`

### 🔲 Not Implemented

#### Authentication Methods
- [ ] Captcha-based login (protocol defined, impl needed)
- [ ] QR code login (protocol defined, impl needed)
- [ ] Playwright browser automation
- [ ] OAuth flows

#### Response Parsing
- [ ] SSE stream parser (extract content from `data:` lines)
- [ ] Text extraction with reasoning
- [ ] Product ranking extraction
- [ ] Source citation extraction

#### Additional Features
- [ ] Proxy support
- [ ] Request history and analytics
- [ ] Account health monitoring
- [ ] Adaptive rate limiting
- [ ] Other providers (ChatGPT, Claude, Gemini)

---

## Adding a New Platform

### 5-Step Process (30 minutes)

#### Step 1: Create Directory

```bash
mkdir -p provider/providers/your_platform
touch provider/providers/your_platform/__init__.py
touch provider/providers/your_platform/provider.py
touch provider/providers/your_platform/auth.py
touch provider/providers/your_platform/session.py
touch provider/providers/your_platform/client.py
```

#### Step 2: Implement Authenticator

```python
# provider/providers/your_platform/auth.py
from provider.core.types import Account
from provider.core.exceptions import APIError

class YourPlatformAuthenticator:
    async def login(self, account: Account) -> str:
        """Login and return token"""
        email = account.credentials.get("email")
        password = account.credentials.get("password")

        resp = await http_post(
            "https://platform.com/api/login",
            json={"email": email, "password": password}
        )

        if resp.status_code == 200:
            return resp.json()["token"]
        else:
            raise APIError(resp.status_code, "Login failed")

    async def refresh(self, account: Account) -> str | None:
        return None  # Not supported

    def needs_manual_login(self) -> bool:
        return False

    async def initiate_login(self, account: Account):
        raise NotImplementedError()
```

#### Step 3: Implement Session Manager

```python
# provider/providers/your_platform/session.py
from provider.core.types import Account

class YourPlatformSessionManager:
    async def prepare(self, account: Account, token: str) -> dict:
        # Option 1: No session needed
        return {}

        # Option 2: Session required
        resp = await http_post(
            "https://platform.com/api/session/create",
            headers={"Authorization": f"Bearer {token}"}
        )
        return {"session_id": resp.json()["session_id"]}
```

#### Step 4: Implement Client

```python
# provider/providers/your_platform/client.py
from provider.core.types import CallParams
from provider.core.exceptions import APIError, TokenExpired

class YourPlatformClient:
    async def call(
        self,
        params: CallParams,
        token: str,
        session_data: dict
    ) -> str:
        """Make API call and return string"""
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Map CallParams to platform format
        payload = {
            "messages": params.messages,
            "reasoning": params.enable_thinking,
            "search": params.enable_search,
        }

        resp = await http_post(
            "https://platform.com/api/chat",
            headers=headers,
            json=payload,
            stream=True
        )

        if resp.status_code == 401:
            raise TokenExpired("api_call")
        elif resp.status_code != 200:
            raise APIError(resp.status_code, resp.text)

        # Read streaming response
        content = ""
        for line in resp.iter_lines():
            if line:
                content += line.decode("utf-8") + "\n"

        return content
```

#### Step 5: Create Provider Class

```python
# provider/providers/your_platform/provider.py
import json
from pathlib import Path
from provider.account_pool.simple_pool import SimpleAccountPool
from provider.core.types import Account, CallParams, CallResult, LoginStatus, RateLimitConfig
from provider.parser.passthrough import PassthroughParser
from provider.providers.base import Provider
from provider.providers.your_platform.auth import YourPlatformAuthenticator
from provider.providers.your_platform.session import YourPlatformSessionManager
from provider.providers.your_platform.client import YourPlatformClient
from provider.storage.json_file import JsonFileTokenStorage

class YourPlatform:
    """Your Platform AI provider"""

    def __init__(self, config_path: str = "config.json"):
        # Load config
        config_file = Path(config_path)
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        provider_config = config["providers"]["your_platform"]

        # Parse accounts
        accounts = self._parse_accounts(provider_config["accounts"])

        # Parse rate limit
        rate_limit = RateLimitConfig(
            max_requests_per_period=provider_config["rate_limit"]["max_requests_per_period"],
            period_seconds=provider_config["rate_limit"]["period_seconds"],
            min_delay_between_requests=provider_config["rate_limit"]["min_delay_between_requests"],
        )

        # Create token storage and load tokens
        token_storage = JsonFileTokenStorage(provider_config["token_storage_path"])
        existing_tokens = token_storage.load_all_sync()
        for account in accounts:
            if account.id in existing_tokens and not account.token:
                account.token = existing_tokens[account.id]
                account.login_status = LoginStatus.LOGGED_IN

        # Create components
        account_pool = SimpleAccountPool(accounts, rate_limit, token_storage)
        authenticator = YourPlatformAuthenticator()
        session_manager = YourPlatformSessionManager()
        client = YourPlatformClient()
        parser = PassthroughParser()

        # Create internal provider
        self._provider = Provider(
            name="your_platform",
            account_pool=account_pool,
            authenticator=authenticator,
            session_manager=session_manager,
            client=client,
            parser=parser,
            max_retries=provider_config.get("max_retries", 3),
        )

    def _parse_accounts(self, accounts_data: list[dict]) -> list[Account]:
        accounts = []
        for acc_data in accounts_data:
            account_id = acc_data.get("email") or acc_data.get("mobile") or acc_data.get("id")
            if account_id:
                account = Account(
                    id=account_id,
                    credentials=acc_data,
                    token=acc_data.get("token"),
                    login_status=LoginStatus.NEED_LOGIN if not acc_data.get("token") else LoginStatus.LOGGED_IN,
                )
                accounts.append(account)
        return accounts

    async def call(self, params: CallParams) -> CallResult:
        return await self._provider.call(params)

# __init__.py
from provider.providers.your_platform.provider import YourPlatform
__all__ = ["YourPlatform"]
```

#### Test It

```python
# test_your_platform.py
import asyncio
from provider.providers.your_platform import YourPlatform
from provider.core.types import CallParams

async def main():
    platform = YourPlatform("config.json")

    params = CallParams(
        messages="Hello!",
        enable_thinking=False,
        enable_search=False,
    )

    result = await platform.call(params)
    print(result.content)

asyncio.run(main())
```

---

## Advanced Topics

### Error Handling

**Exception Hierarchy:**
```
AIBackendError (base)
    ├─> NoAccountAvailable
    ├─> TokenExpired
    ├─> AccountBanned
    ├─> RateLimited
    ├─> AllRetriesFailed
    ├─> LoginRequired
    └─> APIError
```

**Retry Strategy:**
- `TokenExpired`: Attempts re-login, then tries different account
- `AccountBanned`: Marks account as banned, tries different account
- `RateLimited`: Marks account as rate limited, tries different account
- `APIError` (400/500): Does not retry (indicates request issue)

### Captcha Login (Protocol Defined)

```python
class CaptchaAuthenticator:
    def needs_manual_login(self) -> bool:
        return True

    async def initiate_login(self, account: Account) -> LoginSession:
        resp = await self._request_captcha(account)

        return LoginSession(
            account_id=account.id,
            login_type="captcha",
            captcha_image=resp["captcha_image"],
            expires_at=time.time() + 300,
        )

    async def submit_captcha_solution(self, session: LoginSession, solution: str) -> str:
        resp = await self._submit_captcha(session.account_id, solution)
        if resp["success"]:
            return resp["token"]
        raise APIError(400, "Captcha verification failed")
```

**Integration:**
```python
# Start login
login_manager = LoginManager(authenticator, account_pool)
session = await login_manager.start_login(account)

# Display captcha to user
display_image(session.captcha_image)
user_input = get_user_input()

# Submit
success = await login_manager.submit_captcha(account.id, user_input)
```

### QR Code Login (Protocol Defined)

```python
class QRAuthenticator:
    async def initiate_login(self, account: Account) -> LoginSession:
        resp = await self._request_qr_code(account)

        return LoginSession(
            account_id=account.id,
            login_type="qrcode",
            qrcode_data=resp["qr_url"],
            expires_at=time.time() + 300,
            metadata={"poll_url": resp["poll_url"], "qr_id": resp["qr_id"]},
        )

    async def poll_qr_status(self, session: LoginSession) -> str | None:
        resp = await self._poll_status(
            session.metadata["poll_url"],
            session.metadata["qr_id"]
        )
        if resp["status"] == "scanned":
            return resp["token"]
        return None  # Still waiting
```

### Response Parsing

**SSE Stream Parser:**
```python
class SSEParser:
    def parse(self, raw_response: str) -> CallResult:
        content = ""
        reasoning = ""

        for line in raw_response.split("\n"):
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                    if "choices" in data:
                        for choice in data["choices"]:
                            delta = choice.get("delta", {})
                            if "content" in delta:
                                content += delta["content"]
                            if "reasoning_content" in delta:
                                reasoning += delta["reasoning_content"]
                except json.JSONDecodeError:
                    continue

        return CallResult(
            raw_response=None,
            content=content,
            reasoning=reasoning if reasoning else None,
            sources=[],
            rankings=[],
            metadata={},
        )
```

### Proxy Support (Design)

```python
@dataclass
class ProxyConfig:
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    def to_url(self) -> str:
        if self.username:
            return f"http://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"http://{self.host}:{self.port}"

# Add to Account
@dataclass
class Account:
    # ... existing fields ...
    proxy: ProxyConfig | None = None

# Use in HTTP client
resp = requests.post(
    url,
    headers=headers,
    json=payload,
    proxies={"http": account.proxy.to_url(), "https": account.proxy.to_url()}
)
```

---

## Best Practices

### Configuration Security

Don't store passwords in plain JSON. Use environment variables:

```python
import os

# In provider initialization
for account in accounts:
    env_key = f"PROVIDER_ACCOUNT_{account.id}_PASSWORD"
    if env_key in os.environ:
        account.credentials["password"] = os.environ[env_key]
```

### Logging

Add detailed logging for debugging:

```python
import logging

logger = logging.getLogger(__name__)

async def call(...):
    logger.info(f"Making API call with session: {session_data.get('session_id')}")
    try:
        resp = await http_post(...)
        logger.info(f"API call successful, status: {resp.status_code}")
        return resp
    except Exception as e:
        logger.error(f"API call failed: {e}", exc_info=True)
        raise
```

### Testing

Write tests for each component:

```python
import pytest

@pytest.mark.asyncio
async def test_account_pool_rate_limit():
    accounts = [Account(id=f"acc{i}", credentials={}) for i in range(3)]
    rate_limit = RateLimitConfig(max_requests_per_period=2, period_seconds=1.0)
    storage = MockTokenStorage()

    pool = SimpleAccountPool(accounts, rate_limit, storage)

    # Should succeed first 2 times
    result1 = await pool.acquire()
    assert result1 is not None
    await pool.release(result1[0])

    result2 = await pool.acquire()
    assert result2 is not None
    await pool.release(result2[0])

    # Should fail or wait on 3rd time
    result3 = await pool.acquire()
    assert result3 is None or result3[1] > 0
```

---

## Troubleshooting

### Issue: "TokenExpired" immediately after login

**Check:**
1. Is login returning a valid token?
2. Add logging: `logger.info(f"Token: {token}")` in `login()`
3. Verify token format is correct for platform

### Issue: "APIError 422" (Unprocessable Entity)

**Common causes:**
- Incorrect payload format for platform
- Missing required fields
- Invalid parameter values

**Debug:**
```python
logger.info(f"Payload: {json.dumps(payload, indent=2)}")
```

### Issue: Rate limiting not working

**Check:**
1. Is `rate_limit` config set correctly in config.json?
2. Are timestamps being recorded? Add logging in `pool.release()`
3. Try with `max_requests_per_period=1` to test

### Issue: Account stuck in "in_use" state

**Cause:** Exception occurred before `release()` was called

**Solution:** Provider automatically calls `release()` in `finally` block

---

## Protocol Reference

Quick reference for all protocols:

```python
# AccountPool
async def acquire(exclude: list[str] = None) -> tuple[Account, float] | None
async def release(account: Account, record_request: bool = True) -> None
async def mark_login_status(account: Account, status: LoginStatus) -> None
async def mark_health_status(account: Account, status: HealthStatus) -> None

# Authenticator
async def login(account: Account) -> str
async def refresh(account: Account) -> str | None
def needs_manual_login() -> bool
async def initiate_login(account: Account) -> LoginSession

# SessionManager
async def prepare(account: Account, token: str) -> dict

# AIClient
async def call(params: CallParams, token: str, session_data: dict) -> str

# ResponseParser
def parse(raw_response: str) -> CallResult

# TokenStorage
async def load(account_id: str) -> str | None
async def save(account: Account) -> None
async def load_all() -> dict[str, str]
def load_all_sync() -> dict[str, str]  # For initialization only
```

---

## Key Changes From Original Design

1. **Direct Instantiation**: `DeepSeek("config.json")` instead of `Config.create_provider()`
2. **Separated States**: Three independent fields (`in_use`, `login_status`, `health_status`) instead of single `status`
3. **String Responses**: Client returns `str`, parser accepts `str` (not `Any`)
4. **Removed Config**: No Config factory pattern, each provider loads its own config
5. **Provider Directory**: Code is in `provider/` not `ai_backend/`

---

## Summary

**Core Framework**: ✅ Complete - All protocols defined, DeepSeek fully implemented
**Ready for Extension**: 🔄 Templates and guides ready for new platforms
**Documentation**: 📖 Comprehensive guides for all features

**Next Steps:**
1. Implement SSE stream parser to extract content from `data:` lines
2. Add second platform (ChatGPT, Claude) to validate extensibility
3. Implement captcha/QR login when needed
4. Add product ranking extraction parser

For detailed implementation patterns and examples, see the DeepSeek provider implementation in `provider/providers/deepseek/`.
