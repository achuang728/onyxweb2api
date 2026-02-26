"""Onyx API client for OpenAI-compatible proxy."""
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Tuple

import httpx

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES_PER_COOKIE = 3
_EMPTY_SUCCESS_SWITCH_THRESHOLD = 2
_COOKIE_COOLDOWN_SECONDS = 7 * 24 * 60 * 60
_COOKIE_STATE_PATH = Path(__file__).with_name("cookie_state.json")
_COOKIE_POOL: List[str] = []
_CURRENT_COOKIE_INDEX = 0
_EMPTY_OK_COUNTS: Dict[int, int] = {}
_STATE_LOADED = False
_EXHAUSTED_COOKIES: Dict[str, int] = {}
_LAST_GOOD_FINGERPRINT = ""


def _content_to_text(content) -> str:
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content or "")


def _build_prompt(messages: list) -> str:
    if not messages:
        return "Hello"

    lines = []
    for msg in messages:
        role = msg.get("role", "user")
        text = _content_to_text(msg.get("content", "")).strip()
        if not text:
            continue
        lines.append(f"{role}: {text}")

    if not lines:
        return "Hello"
    return "\n".join(lines)


def _resolve_model(model_name: str) -> Tuple[str, str]:
    if model_name in config.MODEL_MAP:
        return config.MODEL_MAP[model_name]

    if "__" in model_name:
        parts = model_name.split("__")
        if len(parts) >= 3:
            return parts[0], parts[-1]

    # Safe fallback for unknown names
    return "Anthropic", "claude-opus-4-6"


def _headers(with_json: bool = False) -> dict:
    headers = {
        "accept": "application/json",
        "origin": "https://cloud.onyx.app",
        "referer": config.ONYX_REFERER,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
        ),
    }
    if with_json:
        headers["content-type"] = "application/json"
    return headers


def _parse_auth_cookies(raw: str) -> List[str]:
    normalized = (raw or "").replace("，", ",")
    values: List[str] = []
    seen = set()
    for chunk in normalized.split(","):
        value = _extract_auth_value(chunk).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _cookie_fingerprint(cookie_value: str) -> str:
    digest = hashlib.sha256(cookie_value.encode("utf-8")).hexdigest()
    return digest[:16]


def _load_cookie_state() -> None:
    global _STATE_LOADED, _EXHAUSTED_COOKIES, _LAST_GOOD_FINGERPRINT
    if _STATE_LOADED:
        return
    _STATE_LOADED = True

    if not _COOKIE_STATE_PATH.exists():
        return

    try:
        raw = json.loads(_COOKIE_STATE_PATH.read_text(encoding="utf-8"))
        exhausted = raw.get("exhausted", {})
        if isinstance(exhausted, dict):
            _EXHAUSTED_COOKIES = {
                str(k): int(v) for k, v in exhausted.items() if isinstance(k, str) and isinstance(v, (int, float))
            }
        last_good = raw.get("last_good", "")
        if isinstance(last_good, str):
            _LAST_GOOD_FINGERPRINT = last_good
    except Exception as exc:
        logger.warning("Failed to load cookie state file: %s", exc)


def _save_cookie_state() -> None:
    try:
        payload = {
            "version": 1,
            "updated_at": int(time.time()),
            "cooldown_seconds": _COOKIE_COOLDOWN_SECONDS,
            "exhausted": _EXHAUSTED_COOKIES,
            "last_good": _LAST_GOOD_FINGERPRINT,
        }
        _COOKIE_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save cookie state file: %s", exc)


def _is_cookie_in_cooldown(cookie_value: str) -> bool:
    fp = _cookie_fingerprint(cookie_value)
    exhausted_at = _EXHAUSTED_COOKIES.get(fp)
    if not exhausted_at:
        return False
    return (int(time.time()) - int(exhausted_at)) < _COOKIE_COOLDOWN_SECONDS


def _mark_cookie_exhausted(cookie_value: str) -> None:
    fp = _cookie_fingerprint(cookie_value)
    _EXHAUSTED_COOKIES[fp] = int(time.time())
    _save_cookie_state()


def _mark_cookie_available(cookie_value: str) -> None:
    global _LAST_GOOD_FINGERPRINT
    fp = _cookie_fingerprint(cookie_value)
    if fp in _EXHAUSTED_COOKIES:
        del _EXHAUSTED_COOKIES[fp]
    _LAST_GOOD_FINGERPRINT = fp
    _save_cookie_state()


def _available_cookie_indexes(cookies: List[str]) -> List[int]:
    available = []
    skipped = 0
    for idx, value in enumerate(cookies):
        if _is_cookie_in_cooldown(value):
            skipped += 1
            continue
        available.append(idx)
    if skipped:
        logger.info("Cookie cooldown: skipped=%d, available=%d", skipped, len(available))
    return available


def _ensure_cookie_pool() -> List[str]:
    global _COOKIE_POOL, _CURRENT_COOKIE_INDEX
    _load_cookie_state()
    if not _COOKIE_POOL:
        _COOKIE_POOL = _parse_auth_cookies(config.ONYX_AUTH_COOKIE)
        _CURRENT_COOKIE_INDEX = 0
        if _LAST_GOOD_FINGERPRINT:
            for idx, cookie_value in enumerate(_COOKIE_POOL):
                if _cookie_fingerprint(cookie_value) == _LAST_GOOD_FINGERPRINT:
                    _CURRENT_COOKIE_INDEX = idx
                    break
    if not _COOKIE_POOL:
        raise RuntimeError("ONYX_AUTH_COOKIE is missing")
    return _COOKIE_POOL


def _ordered_cookie_indexes(candidates: List[int]) -> List[int]:
    if not candidates:
        return []
    ordered = sorted(candidates)
    start_pos = 0
    for pos, idx in enumerate(ordered):
        if idx >= _CURRENT_COOKIE_INDEX:
            start_pos = pos
            break
    else:
        start_pos = 0
    return ordered[start_pos:] + ordered[:start_pos]


def _mark_cookie_success(index: int) -> None:
    global _CURRENT_COOKIE_INDEX
    _CURRENT_COOKIE_INDEX = index
    _EMPTY_OK_COUNTS[index] = 0


def _mark_empty_ok(index: int) -> int:
    count = _EMPTY_OK_COUNTS.get(index, 0) + 1
    _EMPTY_OK_COUNTS[index] = count
    return count


def _clear_empty_ok(index: int) -> None:
    _EMPTY_OK_COUNTS[index] = 0


async def _create_chat_session_with_cookie(
    client: httpx.AsyncClient,
    cookie_value: str,
) -> str:
    payload = {"persona_id": config.ONYX_PERSONA_ID, "description": None, "project_id": None}
    response = await client.post(
        f"{config.ONYX_BASE_URL}/api/chat/create-chat-session",
        headers=_headers(with_json=True),
        json=payload,
        cookies={"fastapiusersauth": cookie_value},
        timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=15.0),
    )
    if response.status_code in (401, 403):
        raise RuntimeError("Onyx auth failed")
    if response.status_code != 200:
        raise RuntimeError(f"Onyx create-chat-session HTTP {response.status_code}: {response.text[:300]}")

    data = response.json()
    chat_session_id = data.get("chat_session_id") or data.get("id")
    if not chat_session_id:
        raise RuntimeError(f"create-chat-session missing chat_session_id: {data}")
    return chat_session_id


async def create_chat_session(client: httpx.AsyncClient) -> str:
    cookies = _ensure_cookie_pool()
    available = _available_cookie_indexes(cookies)
    if not available:
        raise RuntimeError("All cookies are in cooldown window")
    pick = _ordered_cookie_indexes(available)[0]
    return await _create_chat_session_with_cookie(client, cookies[pick])


def _extract_auth_value(cookie_str: str) -> str:
    # Accept either full cookie string or only fastapiusersauth value.
    if "fastapiusersauth=" in cookie_str:
        for piece in cookie_str.split(";"):
            piece = piece.strip()
            if piece.startswith("fastapiusersauth="):
                return piece.split("=", 1)[1]
    return cookie_str.strip()


async def stream_chat(
    client: httpx.AsyncClient,
    messages: list,
    model_name: str,
) -> AsyncGenerator[Tuple[str, str], None]:
    cookies = _ensure_cookie_pool()
    total = len(cookies)
    available_indexes = _available_cookie_indexes(cookies)
    if not available_indexes:
        raise RuntimeError(f"All cookies are in cooldown window. total={total}")

    effective_total = len(available_indexes)
    provider, version = _resolve_model(model_name)
    request_order = _ordered_cookie_indexes(available_indexes)

    for pos, cookie_index in enumerate(request_order):
        cookie_value = cookies[cookie_index]
        logger.info("Cookie status: current=%d/%d (pool=%d)", pos + 1, effective_total, total)

        for attempt in range(1, _MAX_RETRIES_PER_COOKIE + 1):
            try:
                chat_session_id = await _create_chat_session_with_cookie(client, cookie_value)
                payload = {
                    "message": _build_prompt(messages),
                    "chat_session_id": chat_session_id,
                    "parent_message_id": None,
                    "file_descriptors": [],
                    "internal_search_filters": {
                        "source_type": None,
                        "document_set": None,
                        "time_cutoff": None,
                        "tags": [],
                    },
                    "deep_research": False,
                    "forced_tool_id": None,
                    "llm_override": {
                        "temperature": 0.5,
                        "model_provider": provider,
                        "model_version": version,
                    },
                    "origin": config.ONYX_ORIGIN,
                }

                got_text = False
                async with client.stream(
                    "POST",
                    f"{config.ONYX_BASE_URL}/api/chat/send-chat-message",
                    headers=_headers(with_json=True),
                    json=payload,
                    cookies={"fastapiusersauth": cookie_value},
                    timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=15.0),
                ) as response:
                    if response.status_code in (401, 403):
                        raise RuntimeError("Onyx auth failed")
                    if response.status_code != 200:
                        body = await response.aread()
                        raise RuntimeError(f"Onyx send-chat-message HTTP {response.status_code}: {body[:300]}")

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        obj = item.get("obj", {})
                        item_type = obj.get("type")

                        if item_type == "reasoning_delta":
                            delta = obj.get("reasoning", "")
                            if delta:
                                yield "thinking", delta
                        elif item_type == "message_delta":
                            delta = obj.get("content", "")
                            if delta:
                                got_text = True
                                yield "text", delta
                        elif item_type == "stop":
                            break

                if got_text:
                    _clear_empty_ok(cookie_index)
                    _mark_cookie_success(cookie_index)
                    _mark_cookie_available(cookie_value)
                    return

                empty_count = _mark_empty_ok(cookie_index)
                logger.warning(
                    "Cookie %d/%d returned empty content (count=%d/%d)",
                    cookie_index + 1,
                    total,
                    empty_count,
                    _EMPTY_SUCCESS_SWITCH_THRESHOLD,
                )
                if empty_count >= _EMPTY_SUCCESS_SWITCH_THRESHOLD:
                    _mark_cookie_exhausted(cookie_value)
                    break
                continue
            except Exception as exc:
                logger.warning(
                    "Cookie %d/%d attempt %d/%d failed: %s",
                    cookie_index + 1,
                    total,
                    attempt,
                    _MAX_RETRIES_PER_COOKIE,
                    exc,
                )
                if attempt < _MAX_RETRIES_PER_COOKIE:
                    continue
                _mark_cookie_exhausted(cookie_value)
                break

        next_cookie = pos + 2 if pos + 1 < len(request_order) else None
        if next_cookie is not None:
            logger.warning(
                "Cookie %d/%d unavailable, auto switch to cookie %d/%d",
                pos + 1,
                effective_total,
                next_cookie,
                effective_total,
            )

    raise RuntimeError(f"All available cookies unavailable. available={effective_total}, total={total}")


async def full_chat(client: httpx.AsyncClient, messages: list, model_name: str) -> Tuple[str, str]:
    text_parts = []
    thinking_parts = []
    async for item_type, content in stream_chat(client, messages, model_name):
        if item_type == "thinking":
            thinking_parts.append(content)
        else:
            text_parts.append(content)
    return "".join(text_parts), "".join(thinking_parts)
