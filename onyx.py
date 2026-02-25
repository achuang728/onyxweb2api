"""Onyx API client for OpenAI-compatible proxy."""
import json
import logging
from typing import AsyncGenerator, Tuple

import httpx

import config

logger = logging.getLogger(__name__)


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


async def create_chat_session(client: httpx.AsyncClient) -> str:
    if not config.ONYX_AUTH_COOKIE:
        raise RuntimeError("ONYX_AUTH_COOKIE is missing")

    payload = {"persona_id": config.ONYX_PERSONA_ID, "description": None, "project_id": None}
    response = await client.post(
        f"{config.ONYX_BASE_URL}/api/chat/create-chat-session",
        headers=_headers(with_json=True),
        json=payload,
        cookies={"fastapiusersauth": _extract_auth_value(config.ONYX_AUTH_COOKIE)},
        timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=15.0),
    )
    if response.status_code == 401:
        raise RuntimeError("Onyx auth failed - check ONYX_AUTH_COOKIE")
    if response.status_code != 200:
        raise RuntimeError(f"Onyx create-chat-session HTTP {response.status_code}: {response.text[:300]}")

    data = response.json()
    chat_session_id = data.get("chat_session_id") or data.get("id")
    if not chat_session_id:
        raise RuntimeError(f"create-chat-session missing chat_session_id: {data}")
    return chat_session_id


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
    chat_session_id = await create_chat_session(client)
    provider, version = _resolve_model(model_name)

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

    async with client.stream(
        "POST",
        f"{config.ONYX_BASE_URL}/api/chat/send-chat-message",
        headers=_headers(with_json=True),
        json=payload,
        cookies={"fastapiusersauth": _extract_auth_value(config.ONYX_AUTH_COOKIE)},
        timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=15.0),
    ) as response:
        if response.status_code == 401:
            raise RuntimeError("Onyx auth failed - check ONYX_AUTH_COOKIE")
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
                    yield "text", delta
            elif item_type == "stop":
                break


async def full_chat(client: httpx.AsyncClient, messages: list, model_name: str) -> Tuple[str, str]:
    text_parts = []
    thinking_parts = []
    async for item_type, content in stream_chat(client, messages, model_name):
        if item_type == "thinking":
            thinking_parts.append(content)
        else:
            text_parts.append(content)
    return "".join(text_parts), "".join(thinking_parts)
