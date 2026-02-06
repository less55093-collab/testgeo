"""DeepSeek session manager with PoW computation"""

import base64
import ctypes
import json
import logging
import struct

from curl_cffi import requests
from wasmtime import Linker, Module, Store

from ...core.exceptions import APIError, TokenExpired
from ...core.types import Account

logger = logging.getLogger(__name__)

DEEPSEEK_HOST = "chat.deepseek.com"
DEEPSEEK_CREATE_SESSION_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat_session/create"
DEEPSEEK_CREATE_POW_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat/create_pow_challenge"
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

WASM_PATH = "reference/sha3_wasm_bg.7b9ca65ddd.wasm"


class DeepSeekSessionManager:
    """Manages DeepSeek session creation and PoW computation"""

    def __init__(self, wasm_path: str = WASM_PATH):
        self.wasm_path = wasm_path

    async def prepare(self, account: Account, token: str) -> dict:
        """Create session and compute PoW"""
        # Create session
        session_id = await self._create_session(token)

        # Get PoW response
        pow_resp = await self._get_pow_response(token)

        return {"session_id": session_id, "pow_response": pow_resp}

    async def _create_session(self, token: str) -> str:
        """Create a DeepSeek chat session"""
        headers = {**BASE_HEADERS, "authorization": f"Bearer {token}"}

        try:
            resp = requests.post(
                DEEPSEEK_CREATE_SESSION_URL,
                headers=headers,
                json={"agent": "chat"},
                impersonate="chrome",
            )
        except Exception as e:
            logger.error(f"[DeepSeek session] Request failed: {e}")
            raise APIError(status_code=500, detail=f"Session creation failed: {e}")

        try:
            logger.info(f"[DeepSeek session] Response: {resp.text}")
            data = resp.json()
        except Exception as e:
            logger.error(f"[DeepSeek session] JSON parse error: {e}")
            raise APIError(status_code=500, detail="Session creation: invalid JSON")

        if resp.status_code == 200 and data.get("code") == 0:
            session_id = data["data"]["biz_data"]["id"]
            resp.close()
            return session_id
        else:
            code = data.get("code")
            msg = data.get("msg")
            logger.warning(f"[DeepSeek session] Failed, code={code}, msg={msg}")
            resp.close()
            if code == 401 or "token" in str(msg).lower():
                raise TokenExpired("session_creation")
            raise APIError(
                status_code=resp.status_code, detail=f"Session failed: {msg}"
            )

    async def _get_pow_response(self, token: str) -> str:
        """Get PoW challenge and compute answer"""
        headers = {**BASE_HEADERS, "authorization": f"Bearer {token}"}

        try:
            resp = requests.post(
                DEEPSEEK_CREATE_POW_URL,
                headers=headers,
                json={"target_path": "/api/v0/chat/completion"},
                timeout=30,
                impersonate="chrome",
            )
        except Exception as e:
            logger.error(f"[DeepSeek PoW] Request failed: {e}")
            raise APIError(status_code=500, detail=f"PoW request failed: {e}")

        try:
            data = resp.json()
        except Exception as e:
            logger.error(f"[DeepSeek PoW] JSON parse error: {e}")
            raise APIError(status_code=500, detail="PoW: invalid JSON")

        if resp.status_code == 200 and data.get("code") == 0:
            challenge = data["data"]["biz_data"]["challenge"]
            difficulty = challenge.get("difficulty", 144000)
            expire_at = challenge.get("expire_at", 1680000000)

            try:
                answer = self._compute_pow_answer(
                    challenge["algorithm"],
                    challenge["challenge"],
                    challenge["salt"],
                    difficulty,
                    expire_at,
                    challenge["signature"],
                    challenge["target_path"],
                )
            except Exception as e:
                logger.error(f"[DeepSeek PoW] Computation failed: {e}")
                raise APIError(status_code=500, detail=f"PoW computation failed: {e}")

            if answer is None:
                raise APIError(status_code=500, detail="PoW computation returned None")

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
            msg = data.get("msg")
            logger.warning(f"[DeepSeek PoW] Failed, code={code}, msg={msg}")
            resp.close()
            if code == 401 or "token" in str(msg).lower():
                raise TokenExpired("pow_creation")
            raise APIError(status_code=resp.status_code, detail=f"PoW failed: {msg}")

    def _compute_pow_answer(
        self,
        algorithm: str,
        challenge_str: str,
        salt: str,
        difficulty: int,
        expire_at: int,
        signature: str,
        target_path: str,
    ) -> int:
        """Compute DeepSeek PoW answer using WASM module"""
        if algorithm != "DeepSeekHashV1":
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        prefix = f"{salt}_{expire_at}_"

        # Load WASM module
        store = Store()
        linker = Linker(store.engine)
        try:
            with open(self.wasm_path, "rb") as f:
                wasm_bytes = f.read()
        except Exception as e:
            raise RuntimeError(
                f"Failed to load WASM file: {self.wasm_path}, error: {e}"
            )

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
        retptr = (
            int(retptr_val.value) if hasattr(retptr_val, "value") else int(retptr_val)
        )

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
