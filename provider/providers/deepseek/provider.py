"""DeepSeek provider class"""

import json
import logging
from pathlib import Path

from llm import create_random_llm_wrapper

from ...account_pool.simple_pool import SimpleAccountPool
from ...core.types import (
    Account,
    AccountStatus,
    CallParams,
    CallResult,
    RateLimitConfig,
)
from ...providers.base import Provider
from ...providers.deepseek.auth import DeepSeekAuthenticator
from ...providers.deepseek.client import DeepSeekClient
from ...providers.deepseek.parser import DeepSeekParser
from ...providers.deepseek.session import DeepSeekSessionManager
from ...storage.json_file import JsonFileTokenStorage

logger = logging.getLogger(__name__)


class DeepSeek:
    """DeepSeek AI provider"""

    def __init__(self, config_path: str = "config.json"):
        """
        Initialize DeepSeek provider from config file.

        Args:
            config_path: Path to config.json file
        """
        # Load config
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        provider_config = config.get("providers", {}).get("deepseek", {})
        if not provider_config:
            raise ValueError("DeepSeek config not found in config file")

        # Parse accounts
        accounts = self._parse_accounts(provider_config.get("accounts", []))

        # Parse rate limit
        rate_limit_data = provider_config.get("rate_limit", {})
        rate_limit = RateLimitConfig(
            max_requests_per_period=rate_limit_data.get("max_requests_per_period", 10),
            period_seconds=rate_limit_data.get("period_seconds", 60.0),
            min_delay_between_requests=rate_limit_data.get(
                "min_delay_between_requests", 1.0
            ),
        )

        # Get paths
        token_storage_path = provider_config.get(
            "token_storage_path", "data/deepseek_tokens.json"
        )
        wasm_path = provider_config.get("wasm_path", "sha3_wasm_bg.7b9ca65ddd.wasm")
        max_retries = provider_config.get("max_retries", 3)

        # Create token storage and load tokens (synchronously)
        token_storage = JsonFileTokenStorage(token_storage_path)
        existing_tokens = token_storage.load_all_sync()
        for account in accounts:
            if account.id in existing_tokens and not account.token:
                account.token = existing_tokens[account.id]
                account.status = AccountStatus.LOGGED_IN

        # Create components
        account_pool = SimpleAccountPool(accounts, rate_limit, token_storage)
        authenticator = DeepSeekAuthenticator()
        session_manager = DeepSeekSessionManager(wasm_path=wasm_path)
        client = DeepSeekClient()

        # Create parser with LLM wrapper for ranking extraction
        llm_wrapper = create_random_llm_wrapper(config_path)
        parser = DeepSeekParser(llm_wrapper=llm_wrapper)

        # Create internal provider
        self._provider = Provider(
            name="deepseek",
            account_pool=account_pool,
            authenticator=authenticator,
            session_manager=session_manager,
            client=client,
            parser=parser,
            max_retries=max_retries,
        )

        logger.info(f"DeepSeek provider initialized with {len(accounts)} account(s)")

    def _parse_accounts(self, accounts_data: list[dict]) -> list[Account]:
        """Parse account data into Account objects"""
        accounts = []
        for acc_data in accounts_data:
            account_id = (
                acc_data.get("email") or acc_data.get("mobile") or acc_data.get("id")
            )
            if not account_id:
                logger.warning(f"Skipping account with no identifier: {acc_data}")
                continue

            account = Account(
                id=account_id,
                credentials=acc_data,
                token=acc_data.get("token"),
                status=AccountStatus.NEED_LOGIN
                if not acc_data.get("token")
                else AccountStatus.LOGGED_IN,
            )
            accounts.append(account)
        return accounts

    async def call(self, params: CallParams) -> CallResult:
        """
        Make API call to DeepSeek.

        Args:
            params: Call parameters

        Returns:
            Call result
        """
        return await self._provider.call(params)
