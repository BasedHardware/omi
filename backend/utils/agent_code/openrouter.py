"""
Streaming proxy to OpenRouter chat completions for the coding agent.

Forwards SSE chunks to the client verbatim and parses the final `usage` object
(when stream_options.include_usage=true) into a StreamUsage container so the
caller can debit credits after the stream closes.

OpenRouter returns the actual upstream cost in `usage.cost` (USD); we prefer
that over per-token math since OpenRouter routes to different providers at
different rates.

Env vars (ANTHROPIC_* names match the existing Coolify convention — the project
points the Anthropic SDK at OpenRouter, so the OpenRouter key lives under
ANTHROPIC_API_KEY):

  ANTHROPIC_API_KEY      — OpenRouter API key (fallback: OPENROUTER_API_KEY)
  ANTHROPIC_BASE_URL     — base URL (default: https://openrouter.ai/api/)
"""

import json
import logging
import os
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/"
OPENROUTER_TIMEOUT_SECONDS = 600

LOCAL_MODEL_PREFIX = "local/"


def _resolve_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY (or OPENROUTER_API_KEY) not configured")
    return key


def _resolve_completions_url() -> str:
    base = (os.environ.get("ANTHROPIC_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    return f"{base}/v1/chat/completions"


def _resolve_local_route(model: str) -> Optional[tuple[str, str, str]]:
    """If `model` starts with `local/`, return (url, api_key, real_model_id).

    Routes such requests to AGENT_CODE_LOCAL_LLM_URL (a self-hosted
    OpenAI-compatible endpoint, e.g. vLLM) instead of OpenRouter. The
    `local/` prefix is stripped before forwarding so the upstream sees the
    actual served-model name.
    """
    if not model.startswith(LOCAL_MODEL_PREFIX):
        return None
    base = (os.environ.get("AGENT_CODE_LOCAL_LLM_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError(
            "AGENT_CODE_LOCAL_LLM_URL not configured — model "
            f"{model!r} requires a local LLM endpoint"
        )
    api_key = os.environ.get("AGENT_CODE_LOCAL_LLM_API_KEY") or "EMPTY"
    real_model = model[len(LOCAL_MODEL_PREFIX) :]
    url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
    return url, api_key, real_model


class StreamUsage:
    __slots__ = ("input_tokens", "output_tokens", "model", "cost_usd")

    def __init__(self) -> None:
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.model: Optional[str] = None
        # Raw upstream cost in USD as reported by OpenRouter. None when absent.
        self.cost_usd: Optional[float] = None


async def proxy_chat_completion(payload: dict, usage: StreamUsage) -> AsyncIterator[bytes]:
    requested_model = str(payload.get("model") or "")
    local_route = _resolve_local_route(requested_model)
    if local_route is not None:
        url, api_key, real_model = local_route
        payload = {**payload, "model": real_model}
    else:
        api_key = _resolve_api_key()
        url = _resolve_completions_url()

    payload = {**payload, "stream": True}
    stream_options = dict(payload.get("stream_options") or {})
    stream_options["include_usage"] = True
    payload["stream_options"] = stream_options

    # When the request includes tools, ask OpenRouter to filter routing to
    # providers that support every parameter in the request — otherwise the
    # default route may land on a provider that ignores tools and returns a
    # 404 ("No endpoints found that support tool use").
    # https://openrouter.ai/docs/guides/routing/provider-selection
    if payload.get("tools"):
        provider_cfg = dict(payload.get("provider") or {})
        provider_cfg.setdefault("require_parameters", True)
        payload["provider"] = provider_cfg

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nooto.togodynamics.com",
        "X-Title": "Nooto Coding Agent",
    }

    async with httpx.AsyncClient(timeout=OPENROUTER_TIMEOUT_SECONDS) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            # When OpenRouter returns a non-2xx, raise_for_status() raises mid-stream
            # which FastAPI surfaces as a silent connection close to the client. Read
            # the body and emit it as an SSE error event so Pi can render the failure
            # instead of hanging.
            if resp.status_code >= 400:
                try:
                    body_bytes = await resp.aread()
                    body_text = body_bytes.decode("utf-8", errors="replace")[:1000]
                except Exception:
                    body_text = ""
                logger.error(
                    "agent_code upstream error: status=%s body=%s",
                    resp.status_code,
                    body_text,
                )
                err_payload = json.dumps(
                    {"error": {"message": f"upstream {resp.status_code}: {body_text}", "code": resp.status_code}}
                )
                yield f"data: {err_payload}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
                return
            async for line in resp.aiter_lines():
                if line == "":
                    yield b"\n"
                    continue
                yield (line + "\n").encode("utf-8")
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                try:
                    chunk = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                chunk_usage = chunk.get("usage")
                if isinstance(chunk_usage, dict):
                    usage.input_tokens = int(chunk_usage.get("prompt_tokens") or 0)
                    usage.output_tokens = int(chunk_usage.get("completion_tokens") or 0)
                    cost = chunk_usage.get("cost")
                    if isinstance(cost, (int, float)):
                        usage.cost_usd = float(cost)
                model = chunk.get("model")
                if isinstance(model, str) and model:
                    usage.model = model
