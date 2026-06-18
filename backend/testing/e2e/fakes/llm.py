"""
Fake LLM HTTP server using pytest-httpserver.

Provides deterministic responses for OpenAI, Anthropic, and OpenRouter
LLM endpoints. Every request returns the same structured JSON response
so tests are fully reproducible.
"""

import json

# Deterministic LLM responses — these are returned for every LLM call
DEFAULT_STRUCTURED_RESPONSE = {
    "title": "Test Conversation Title",
    "overview": "A test conversation about project planning and action items.",
    "emoji": "🧠",
    "category": "other",
    "action_items": [
        {
            "description": "Review the quarterly report",
            "completed": False,
            "created_at": "2025-01-15T10:00:00Z",
        },
        {
            "description": "Schedule follow-up meeting",
            "completed": False,
            "created_at": "2025-01-15T10:00:00Z",
        },
    ],
    "events": [],
}

DEFAULT_MEMORY_EXTRACTION = [
    {"content": "User is working on a quarterly report review", "category": "system"},
    {"content": "Follow-up meeting needs to be scheduled", "category": "interesting"},
]

DEFAULT_SUMMARY = "Discussion about Q4 planning and deliverables."


def make_openai_chat_response(content: str = None) -> dict:
    """Build a fake OpenAI /v1/chat/completions response."""
    if content is None:
        content = json.dumps(DEFAULT_STRUCTURED_RESPONSE)
    return {
        "id": "chatcmpl-fake-e2e-test",
        "object": "chat.completion",
        "model": "gpt-4.1-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


def make_anthropic_response(content: str = None) -> dict:
    """Build a fake Anthropic /v1/messages response."""
    if content is None:
        content = json.dumps(DEFAULT_STRUCTURED_RESPONSE)
    return {
        "id": "msg_fake-e2e-test",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


def make_openrouter_response(content: str = None) -> dict:
    """Build a fake OpenRouter (OpenAI-compatible) response."""
    return make_openai_chat_response(content)


def configure_llm_fakes(httpserver):
    """
    Register deterministic LLM handlers on a pytest-httpserver instance.

    All common LLM endpoints (OpenAI, Anthropic, OpenRouter) return
    the same structured output so conversation processing produces
    predictable results.
    """

    # OpenAI chat completions
    httpserver.expect_request("/v1/chat/completions").respond_with_json(
        make_openai_chat_response(), status=200, content_type="application/json"
    )

    # Anthropic messages
    httpserver.expect_request("/v1/messages").respond_with_json(
        make_anthropic_response(), status=200, content_type="application/json"
    )

    # OpenRouter (uses OpenAI-compatible format)
    httpserver.expect_request("/api/v1/chat/completions").respond_with_json(
        make_openrouter_response(), status=200, content_type="application/json"
    )

    # OpenAI embeddings
    httpserver.expect_request("/v1/embeddings").respond_with_json(
        {
            "object": "list",
            "data": [{"embedding": [0.1] * 1536, "index": 0}],
            "model": "text-embedding-3-small",
            "usage": {"prompt_tokens": 10, "total_tokens": 10},
        },
        status=200,
        content_type="application/json",
    )


def configure_llm_error(httpserver, status_code: int = 500):
    """
    Configure the LLM fake server to return errors.
    Used by failure-mode tests to verify graceful degradation.
    """
    # Clear existing handlers and add error responses
    for endpoint in ["/v1/chat/completions", "/v1/messages", "/api/v1/chat/completions"]:
        httpserver.expect_request(endpoint).respond_with_json(
            {"error": {"message": "LLM service unavailable", "type": "server_error"}},
            status=status_code,
            content_type="application/json",
        )
