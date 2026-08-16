#!/usr/bin/env python3
"""
YABBAI — client for the hub's AI gateway.

The hub at yabbai.network fronts a provider chain and falls back down it in order:

    nvidia -> groq -> cerebras -> google -> openrouter -> grok -> emergent -> yabbai

Routing, keys and fallback all live on the hub. This module holds no provider keys
and picks no model; it forwards a request and returns what comes back. That keeps
one place to rotate credentials and one place to change routing.

What this does NOT do
---------------------
Generating text does not generate revenue. The agent pool has always reported
$0.00 because nothing in it executes a trade or collects a fee, and wiring a
language model in does not alter that. What it can do is replace hardcoded
placeholder literals with actual reasoning, clearly labelled as generated
analysis rather than measured result. Anything derived from a model must never be
mixed into a revenue or performance figure.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

HUB_URL = (os.environ.get("HUB_AUTH_URL", "https://yabbai.network") or "").rstrip("/")
AI_PATH = os.environ.get("HUB_AI_PATH", "/api/ai/chat")
AI_TIMEOUT = float(os.environ.get("HUB_AI_TIMEOUT", "60"))

# The hub verifies the caller. Service-to-service calls need a key it accepts;
# browser-originated calls can forward the director's session cookie instead.
HUB_AI_KEY = os.environ.get("YABBAI_API_KEY", "")


class HubAIError(RuntimeError):
    """Raised when the gateway cannot be reached or refuses the request."""


class HubAIUnavailable(HubAIError):
    """Gateway is not configured. Callers should degrade, not fabricate."""


def _headers(session_token: Optional[str] = None) -> Dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if session_token:
        headers["Authorization"] = f"Bearer {session_token}"
    elif HUB_AI_KEY:
        headers["Authorization"] = f"Bearer {HUB_AI_KEY}"
    return headers


def _extract_text(payload: Any) -> Optional[str]:
    """Pull the assistant text out of whatever shape the gateway returns.

    The hub proxies several providers, so the response envelope is not guaranteed.
    Try the common shapes and give up honestly rather than guessing.
    """
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return None

    # OpenAI-compatible
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message")
            if isinstance(msg, dict) and msg.get("content"):
                return msg["content"]
            if first.get("text"):
                return first["text"]

    # Flatter shapes some gateways use
    for key in ("content", "response", "text", "message", "output", "reply"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict) and isinstance(value.get("content"), str):
            return value["content"]

    return None


async def chat(
    messages: List[Dict[str, str]],
    *,
    session_token: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.4,
    max_tokens: int = 800,
) -> str:
    """Send a chat request to the hub and return the assistant text.

    Raises rather than returning a placeholder. A caller that cannot get a real
    answer must say so; inventing one is what this project has spent its time
    removing.
    """
    if not HUB_URL:
        raise HubAIUnavailable("HUB_AUTH_URL is not set")

    body: Dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # Omit the model unless asked, so the hub's own route_order decides.
    if model:
        body["model"] = model

    url = f"{HUB_URL}{AI_PATH}"
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            resp = await client.post(url, json=body, headers=_headers(session_token))
    except Exception as e:
        raise HubAIError(f"hub AI unreachable: {e}") from e

    if resp.status_code in (401, 403):
        raise HubAIUnavailable(
            f"hub AI rejected the request ({resp.status_code}). "
            "Set YABBAI_API_KEY or forward a director session."
        )
    if resp.status_code >= 400:
        raise HubAIError(f"hub AI returned {resp.status_code}: {resp.text[:200]}")

    try:
        payload = resp.json()
    except Exception as e:
        raise HubAIError(f"hub AI returned non-JSON: {e}") from e

    text = _extract_text(payload)
    if not text:
        raise HubAIError(
            f"could not find assistant text in gateway response; keys={list(payload)[:8]}"
        )
    return text.strip()


async def available(session_token: Optional[str] = None) -> Dict[str, Any]:
    """Report whether the gateway is reachable. Never raises."""
    try:
        text = await chat(
            [{"role": "user", "content": "Reply with the single word: ok"}],
            session_token=session_token,
            max_tokens=8,
            temperature=0,
        )
        return {"available": True, "sample": text[:40], "endpoint": f"{HUB_URL}{AI_PATH}"}
    except HubAIUnavailable as e:
        return {"available": False, "reason": "not_configured", "detail": str(e)}
    except HubAIError as e:
        return {"available": False, "reason": "error", "detail": str(e)[:200]}
