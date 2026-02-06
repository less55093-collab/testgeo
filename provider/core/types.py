"""Core data types for AI backend framework"""

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class AccountStatus(Enum):
    """Account status - combines login and health states"""

    # Login states
    LOGGED_IN = auto()  # Has valid token
    NEED_LOGIN = auto()  # Needs password login
    NEED_CAPTCHA = auto()  # Needs captcha verification
    NEED_QRCODE = auto()  # Needs QR code scan

    # Health states
    BANNED = auto()  # Account banned by platform
    RATE_LIMITED = auto()  # Temporarily rate limited
    ERROR = auto()  # Unknown error state


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""

    max_requests_per_period: int = 10  # Max requests in time window
    period_seconds: float = 60.0  # Time window size
    min_delay_between_requests: float = 1.0  # Min delay between requests


@dataclass
class Account:
    """Account with credentials and states"""

    id: str  # Unique identifier (email/mobile/etc)
    credentials: dict  # Platform-specific credentials
    token: str | None = None  # Auth token/cookie

    # States (in_use is separate to avoid confusion)
    in_use: bool = False  # Whether currently handling a request
    status: AccountStatus = AccountStatus.NEED_LOGIN  # Combined login + health state

    # Other fields
    last_used: float | None = None
    request_timestamps: list[float] = field(default_factory=list)  # For rate limiting
    error_count: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class CallParams:
    """Platform-agnostic call parameters"""

    messages: str
    enable_thinking: bool = False
    enable_search: bool = True
    extra: dict = field(default_factory=dict)  # Extensible for future params


@dataclass
class CallResult:
    """Unified response format"""

    raw_response: Any  # Original response
    content: str  # Main text content
    reasoning: str | None = None  # Thinking/reasoning if available
    sources: list[dict] = field(default_factory=list)  # Citations
    rankings: list[dict] = field(default_factory=list)  # Parsed rankings
    metadata: dict = field(default_factory=dict)


@dataclass
class LoginSession:
    """Login session for manual auth flows (captcha/QR)"""

    account_id: str
    login_type: str  # "captcha" | "qrcode" | "api"
    captcha_image: bytes | None = None
    qrcode_data: str | None = None
    expires_at: float | None = None
    token: str | None = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def is_complete(self) -> bool:
        return self.token is not None
