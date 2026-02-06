import base64
import ctypes
import json
import logging
import random
import struct
import time
from dataclasses import dataclass, field

from curl_cffi import requests
from wasmtime import Linker, Module, Store

# -------------------------- Logging Configuration --------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("deepseek_client")


@dataclass
class DeepSeekAPIError(Exception):
    status_code: int
    detail: str


@dataclass
class AccountContext:
    """Context object to track state during API calls"""
    account: dict
    deepseek_token: str
    tried_accounts: list = field(default_factory=list)


# ----------------------------------------------------------------------
# Configuration Management
# ----------------------------------------------------------------------
CONFIG_PATH = "config.json"


def load_config():
    """Load configuration from config.json"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[load_config] Failed to read config file: {e}")
        return {}


def save_config(cfg):
    """Save configuration to config.json"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[save_config] Failed to write config.json: {e}")


CONFIG = load_config()

# -------------------------- Global Account Queue --------------------------
account_queue = []


def init_account_queue():
    """Initialize account queue from configuration"""
    global account_queue
    account_queue = CONFIG.get("accounts", [])[:]
    random.shuffle(account_queue)


init_account_queue()

# ----------------------------------------------------------------------
# DeepSeek API Constants
# ----------------------------------------------------------------------
DEEPSEEK_HOST = "chat.deepseek.com"
DEEPSEEK_LOGIN_URL = f"https://{DEEPSEEK_HOST}/api/v0/users/login"
DEEPSEEK_CREATE_SESSION_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat_session/create"
DEEPSEEK_CREATE_POW_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat/create_pow_challenge"
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

WASM_PATH = "sha3_wasm_bg.7b9ca65ddd.wasm"


# ----------------------------------------------------------------------
# Account Management Helpers
# ----------------------------------------------------------------------
def get_account_identifier(account):
    """Get unique identifier for account (email or mobile)"""
    return account.get("email", "").strip() or account.get("mobile", "").strip()


def choose_new_account(exclude_ids=None):
    """
    Select an available account from queue, excluding specified IDs.
    Returns the account and removes it from queue.
    """
    if exclude_ids is None:
        exclude_ids = []

    for i in range(len(account_queue)):
        acc = account_queue[i]
        acc_id = get_account_identifier(acc)
        if acc_id and acc_id not in exclude_ids:
            logger.info(f"[choose_new_account] Selected account: {acc_id}")
            return account_queue.pop(i)

    logger.warning("[choose_new_account] No available accounts or all accounts in use")
    return None


def release_account(account):
    """Return account to the end of queue"""
    account_queue.append(account)


# ----------------------------------------------------------------------
# DeepSeek Login
# ----------------------------------------------------------------------
def login_deepseek_via_account(account):
    """
    Login to DeepSeek using account credentials (email or mobile).
    Updates account token and saves to config. Returns new token.
    """
    email = account.get("email", "").strip()
    mobile = account.get("mobile", "").strip()
    password = account.get("password", "").strip()

    if not password or (not email and not mobile):
        raise DeepSeekAPIError(
            status_code=400,
            detail="Account missing required login info (email or mobile + password)",
        )

    if email:
        payload = {
            "email": email,
            "password": password,
            "device_id": "deepseek_to_api",
            "os": "android",
        }
    else:
        payload = {
            "mobile": mobile,
            "area_code": None,
            "password": password,
            "device_id": "deepseek_to_api",
            "os": "android",
        }

    try:
        resp = requests.post(
            DEEPSEEK_LOGIN_URL, headers=BASE_HEADERS, json=payload, impersonate="chrome"
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"[login_deepseek_via_account] Login request failed: {e}")
        raise DeepSeekAPIError(status_code=500, detail="Account login failed: request error")

    try:
        logger.info(f"[login_deepseek_via_account] Response: {resp.text}")
        data = resp.json()
    except Exception as e:
        logger.error(f"[login_deepseek_via_account] JSON parse failed: {e}")
        raise DeepSeekAPIError(
            status_code=500, detail="Account login failed: invalid JSON response"
        )

    if (
        data.get("data") is None
        or data["data"].get("biz_data") is None
        or data["data"]["biz_data"].get("user") is None
    ):
        logger.error(f"[login_deepseek_via_account] Invalid response format: {data}")
        raise DeepSeekAPIError(
            status_code=500, detail="Account login failed: invalid response format"
        )

    new_token = data["data"]["biz_data"]["user"].get("token")
    if not new_token:
        logger.error(f"[login_deepseek_via_account] Missing token in response: {data}")
        raise DeepSeekAPIError(
            status_code=500, detail="Account login failed: missing token"
        )

    account["token"] = new_token
    save_config(CONFIG)
    return new_token


# ----------------------------------------------------------------------
# Headers Helper
# ----------------------------------------------------------------------
def get_auth_headers(token: str):
    """Return DeepSeek request headers with authorization token"""
    return {**BASE_HEADERS, "authorization": f"Bearer {token}"}


# ----------------------------------------------------------------------
# Session Creation
# ----------------------------------------------------------------------
def create_session(ctx: AccountContext, max_attempts=3):
    """
    Create a DeepSeek chat session.
    On failure, attempts to switch accounts if possible.
    Returns session_id or None.
    """
    attempts = 0
    while attempts < max_attempts:
        headers = get_auth_headers(ctx.deepseek_token)
        try:
            resp = requests.post(
                DEEPSEEK_CREATE_SESSION_URL,
                headers=headers,
                json={"agent": "chat"},
                impersonate="chrome",
            )
        except Exception as e:
            logger.error(f"[create_session] Request failed: {e}")
            attempts += 1
            continue

        try:
            logger.info(f"[create_session] Response: {resp.text}")
            data = resp.json()
        except Exception as e:
            logger.error(f"[create_session] JSON parse error: {e}")
            data = {}

        if resp.status_code == 200 and data.get("code") == 0:
            session_id = data["data"]["biz_data"]["id"]
            resp.close()
            return session_id
        else:
            code = data.get("code")
            logger.warning(
                f"[create_session] Failed, code={code}, msg={data.get('msg')}"
            )
            resp.close()

            # Try to switch account
            current_id = get_account_identifier(ctx.account)
            if current_id not in ctx.tried_accounts:
                ctx.tried_accounts.append(current_id)

            new_account = choose_new_account(ctx.tried_accounts)
            if new_account is None:
                break

            try:
                login_deepseek_via_account(new_account)
            except Exception as e:
                logger.error(
                    f"[create_session] Account {get_account_identifier(new_account)} login failed: {e}"
                )
                attempts += 1
                continue

            ctx.account = new_account
            ctx.deepseek_token = new_account.get("token")

        attempts += 1

    return None


# ----------------------------------------------------------------------
# PoW Computation
# ----------------------------------------------------------------------
def compute_pow_answer(
    algorithm: str,
    challenge_str: str,
    salt: str,
    difficulty: int,
    expire_at: int,
    signature: str,
    target_path: str,
    wasm_path: str,
) -> int:
    """
    Compute DeepSeek PoW answer using WASM module.
    Returns integer answer or None if computation fails.
    """
    if algorithm != "DeepSeekHashV1":
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    prefix = f"{salt}_{expire_at}_"

    # Load WASM module
    store = Store()
    linker = Linker(store.engine)
    try:
        with open(wasm_path, "rb") as f:
            wasm_bytes = f.read()
    except Exception as e:
        raise RuntimeError(f"Failed to load WASM file: {wasm_path}, error: {e}")

    module = Module(store.engine, wasm_bytes)
    instance = linker.instantiate(store, module)
    exports = instance.exports(store)

    try:
        memory = exports["memory"]
        add_to_stack = exports["__wbindgen_add_to_stack_pointer"]
        alloc = exports["__wbindgen_export_0"]
        wasm_solve = exports["wasm_solve"]
    except KeyError as e:
        raise RuntimeError(f"Missing WASM export: {e}")

    def write_memory(offset: int, data: bytes):
        size = len(data)
        base_addr = ctypes.cast(memory.data_ptr(store), ctypes.c_void_p).value
        ctypes.memmove(base_addr + offset, data, size)

    def read_memory(offset: int, size: int) -> bytes:
        base_addr = ctypes.cast(memory.data_ptr(store), ctypes.c_void_p).value
        return ctypes.string_at(base_addr + offset, size)

    def encode_string(text: str):
        data = text.encode("utf-8")
        length = len(data)
        ptr_val = alloc(store, length, 1)
        ptr = int(ptr_val.value) if hasattr(ptr_val, "value") else int(ptr_val)
        write_memory(ptr, data)
        return ptr, length

    # Allocate 16 bytes on stack
    retptr_val = add_to_stack(store, -16)
    retptr = int(retptr_val.value) if hasattr(retptr_val, "value") else int(retptr_val)

    # Encode challenge and prefix to WASM memory
    ptr_challenge, len_challenge = encode_string(challenge_str)
    ptr_prefix, len_prefix = encode_string(prefix)

    # Call wasm_solve
    wasm_solve(
        store,
        retptr,
        ptr_challenge,
        len_challenge,
        ptr_prefix,
        len_prefix,
        float(difficulty),
    )

    # Read 4 bytes status and 8 bytes result
    status_bytes = read_memory(retptr, 4)
    if len(status_bytes) != 4:
        add_to_stack(store, 16)
        raise RuntimeError("Failed to read status bytes")
    status = struct.unpack("<i", status_bytes)[0]

    value_bytes = read_memory(retptr + 8, 8)
    if len(value_bytes) != 8:
        add_to_stack(store, 16)
        raise RuntimeError("Failed to read result bytes")
    value = struct.unpack("<d", value_bytes)[0]

    # Restore stack pointer
    add_to_stack(store, 16)

    if status == 0:
        return None
    return int(value)


# ----------------------------------------------------------------------
# PoW Response
# ----------------------------------------------------------------------
def get_pow_response(ctx: AccountContext, max_attempts=3):
    """
    Get PoW challenge and compute answer.
    On failure, attempts to switch accounts if possible.
    Returns base64-encoded PoW response or None.
    """
    attempts = 0
    while attempts < max_attempts:
        headers = get_auth_headers(ctx.deepseek_token)
        try:
            resp = requests.post(
                DEEPSEEK_CREATE_POW_URL,
                headers=headers,
                json={"target_path": "/api/v0/chat/completion"},
                timeout=30,
                impersonate="chrome",
            )
        except Exception as e:
            logger.error(f"[get_pow_response] Request failed: {e}")
            attempts += 1
            continue

        try:
            data = resp.json()
        except Exception as e:
            logger.error(f"[get_pow_response] JSON parse error: {e}")
            data = {}

        if resp.status_code == 200 and data.get("code") == 0:
            challenge = data["data"]["biz_data"]["challenge"]
            difficulty = challenge.get("difficulty", 144000)
            expire_at = challenge.get("expire_at", 1680000000)

            try:
                answer = compute_pow_answer(
                    challenge["algorithm"],
                    challenge["challenge"],
                    challenge["salt"],
                    difficulty,
                    expire_at,
                    challenge["signature"],
                    challenge["target_path"],
                    WASM_PATH,
                )
            except Exception as e:
                logger.error(f"[get_pow_response] PoW computation failed: {e}")
                answer = None

            if answer is None:
                logger.warning("[get_pow_response] PoW computation failed, retrying...")
                resp.close()
                attempts += 1
                continue

            pow_dict = {
                "algorithm": challenge["algorithm"],
                "challenge": challenge["challenge"],
                "salt": challenge["salt"],
                "answer": answer,
                "signature": challenge["signature"],
                "target_path": challenge["target_path"],
            }
            pow_str = json.dumps(pow_dict, separators=(",", ":"), ensure_ascii=False)
            encoded = base64.b64encode(pow_str.encode("utf-8")).decode("utf-8").rstrip()
            resp.close()
            return encoded
        else:
            code = data.get("code")
            logger.warning(
                f"[get_pow_response] Failed, code={code}, msg={data.get('msg')}"
            )
            resp.close()

            # Try to switch account
            current_id = get_account_identifier(ctx.account)
            if current_id not in ctx.tried_accounts:
                ctx.tried_accounts.append(current_id)

            new_account = choose_new_account(ctx.tried_accounts)
            if new_account is None:
                break

            try:
                login_deepseek_via_account(new_account)
            except Exception as e:
                logger.error(
                    f"[get_pow_response] Account {get_account_identifier(new_account)} login failed: {e}"
                )
                attempts += 1
                continue

            ctx.account = new_account
            ctx.deepseek_token = new_account.get("token")

            attempts += 1

    return None


# ----------------------------------------------------------------------
# Completion API Call
# ----------------------------------------------------------------------
def call_completion_endpoint(payload, headers, max_attempts=3):
    """
    Call DeepSeek completion endpoint with retry logic.
    Returns response object or None.
    """
    attempts = 0
    while attempts < max_attempts:
        try:
            deepseek_resp = requests.post(
                DEEPSEEK_COMPLETION_URL,
                headers=headers,
                json=payload,
                stream=True,
                impersonate="chrome",
            )
        except Exception as e:
            logger.warning(f"[call_completion_endpoint] Request failed: {e}")
            time.sleep(1)
            attempts += 1
            continue

        if deepseek_resp.status_code == 200:
            return deepseek_resp
        else:
            logger.warning(
                f"[call_completion_endpoint] Failed, status: {deepseek_resp.status_code}"
            )
            deepseek_resp.close()
            time.sleep(1)
            attempts += 1

    return None


# ----------------------------------------------------------------------
# Main DeepSeek API Call
# ----------------------------------------------------------------------
async def call_deepseek(payload):
    """
    Main entry point for calling DeepSeek API.

    Args:
        payload: Dict containing 'model' and 'messages' keys

    Returns:
        Response object from DeepSeek API or None

    Raises:
        DeepSeekAPIError: If no accounts available or authentication fails
    """
    # Select an account from config
    selected_account = choose_new_account()
    if not selected_account:
        raise DeepSeekAPIError(
            status_code=429,
            detail="No accounts configured or all accounts are busy",
        )

    # Login if no token
    if not selected_account.get("token", "").strip():
        try:
            login_deepseek_via_account(selected_account)
        except Exception as e:
            release_account(selected_account)
            logger.error(
                f"[call_deepseek] Account {get_account_identifier(selected_account)} login failed: {e}"
            )
            raise DeepSeekAPIError(status_code=500, detail="Account login failed")

    # Create context for this call
    ctx = AccountContext(
        account=selected_account,
        deepseek_token=selected_account.get("token"),
        tried_accounts=[]
    )

    try:
        # Create session
        session_id = create_session(ctx)
        if not session_id:
            raise DeepSeekAPIError(status_code=401, detail="Invalid token")

        # Get PoW response
        pow_resp = get_pow_response(ctx)
        if not pow_resp:
            raise DeepSeekAPIError(
                status_code=401,
                detail="Failed to get PoW (invalid token or unknown error)",
            )

        # Determine model features
        model = payload.get("model", "deepseek-chat")
        messages = payload.get("messages", [])

        model_lower = model.lower()
        if model_lower in ["deepseek-v3", "deepseek-chat"]:
            thinking_enabled = False
            search_enabled = False
        elif model_lower in ["deepseek-r1", "deepseek-reasoner"]:
            thinking_enabled = True
            search_enabled = False
        elif model_lower in ["deepseek-v3-search", "deepseek-chat-search"]:
            thinking_enabled = False
            search_enabled = True
        elif model_lower in ["deepseek-r1-search", "deepseek-reasoner-search"]:
            thinking_enabled = True
            search_enabled = True
        else:
            thinking_enabled = False
            search_enabled = False

        # Prepare request
        headers = {**get_auth_headers(ctx.deepseek_token), "x-ds-pow-response": pow_resp}
        api_payload = {
            "chat_session_id": session_id,
            "parent_message_id": None,
            "prompt": messages,
            "ref_file_ids": [],
            "thinking_enabled": thinking_enabled,
            "search_enabled": search_enabled,
        }

        # Call completion endpoint
        deepseek_resp = call_completion_endpoint(api_payload, headers, max_attempts=3)
        return deepseek_resp

    except Exception as e:
        logger.error(f"[call_deepseek] Call failed: {e}")
        raise
    finally:
        # Always release account back to queue
        release_account(ctx.account)
