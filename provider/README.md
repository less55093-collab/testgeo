# AI Backend Framework

A modular, replaceable AI backend calling framework for querying different AI platforms (DeepSeek, etc.) with account management, rate limiting, and automatic retry logic.

## Architecture

The framework is organized into layers using Protocol-based composition:

```
Config → AccountPool → Auth → Session → Client → Parser
```

### Key Features

- **Protocol-based composition**: Easy to swap implementations per platform
- **Account state management**: IDLE, IN_USE, NEED_LOGIN, NEED_CAPTCHA, NEED_QRCODE, BANNED, RATE_LIMITED
- **Per-account rate limiting**: Configurable requests/period and min delay between requests
- **Auto-retry logic**: Automatically retries with different accounts on failure
- **Persistent token storage**: Tokens saved to disk and survive restarts
- **Login flows**: Support for API login, captcha, and QR code authentication

## Directory Structure

```
ai_backend/
├── core/
│   ├── types.py          # Account, CallParams, CallResult, enums
│   ├── exceptions.py     # Custom exceptions
│   └── config.py         # Config loading, provider factory
├── storage/
│   ├── base.py           # TokenStorage protocol
│   └── json_file.py      # JSON file storage
├── account_pool/
│   ├── base.py           # AccountPool protocol
│   └── simple_pool.py    # Rate-limited pool
├── auth/
│   ├── base.py           # Authenticator protocol
│   └── login_manager.py  # Manages captcha/QR login flows
├── session/
│   ├── base.py           # SessionManager protocol
│   └── noop.py           # No-op for platforms without sessions
├── client/
│   └── base.py           # AIClient protocol
├── parser/
│   ├── base.py           # ResponseParser protocol
│   └── passthrough.py    # Returns raw response
└── providers/
    ├── base.py           # Provider class
    └── deepseek/
        ├── auth.py       # DeepSeek API login
        ├── session.py    # Session + PoW computation
        └── client.py     # DeepSeek completion API
```

## Quick Start

### 1. Configure accounts

Create a `config.json` file (see `config.example.json`):

```json
{
  "providers": {
    "deepseek": {
      "accounts": [
        {
          "email": "your-email@example.com",
          "password": "your-password"
        }
      ],
      "rate_limit": {
        "max_requests_per_period": 10,
        "period_seconds": 60.0,
        "min_delay_between_requests": 1.0
      }
    }
  }
}
```

### 2. Use the framework

```python
import asyncio
from ai_backend.core.config import Config
from ai_backend.core.types import CallParams

async def main():
    # Load config and create provider
    config = Config("config.json")
    provider = await config.create_provider("deepseek")

    # Make API call
    params = CallParams(
        messages=[{"role": "user", "content": "Hello!"}],
        enable_thinking=False,
        enable_search=False,
    )

    result = await provider.call(params)
    print(result.content)

asyncio.run(main())
```

## Adding a New Provider

To add a new AI platform:

1. **Implement Authenticator**: Create `providers/<platform>/auth.py`
   - Implement `login()`, `refresh()`, `needs_manual_login()`, `initiate_login()`

2. **Implement SessionManager**: Create `providers/<platform>/session.py`
   - Implement `prepare()` to set up session data

3. **Implement AIClient**: Create `providers/<platform>/client.py`
   - Implement `call()` to make the actual API request

4. **Register in Config**: Add factory logic in `core/config.py`

5. **(Optional) Custom Parser**: Implement `ResponseParser` for platform-specific response parsing

## Core Types

### Account

```python
@dataclass
class Account:
    id: str                     # Unique identifier
    credentials: dict           # Platform credentials
    token: str | None          # Auth token/cookie
    status: AccountStatus      # Current status
    request_timestamps: list[float]  # For rate limiting
```

### CallParams

```python
@dataclass
class CallParams:
    messages: list[dict]       # Chat messages
    enable_thinking: bool      # Enable reasoning
    enable_search: bool        # Enable web search
    extra: dict                # Platform-specific params
```

### CallResult

```python
@dataclass
class CallResult:
    raw_response: Any          # Original response
    content: str               # Main text content
    reasoning: str | None      # Thinking/reasoning
    sources: list[dict]        # Citations
    rankings: list[dict]       # Parsed rankings
    metadata: dict
```

## Rate Limiting

Configure per-account rate limits:

```python
RateLimitConfig(
    max_requests_per_period=10,    # Max requests in window
    period_seconds=60.0,            # Time window
    min_delay_between_requests=1.0  # Min delay between requests
)
```

The account pool automatically:
- Tracks request timestamps
- Enforces rate limits
- Waits before acquiring accounts if needed

## Error Handling

The framework provides custom exceptions:

- `NoAccountAvailable`: No accounts in pool
- `TokenExpired`: Account token expired
- `AccountBanned`: Account banned
- `RateLimited`: Account rate limited
- `AllRetriesFailed`: All retry attempts exhausted
- `APIError`: Generic API error

The provider automatically retries with different accounts on failure.

## License

MIT
