import json
import pytest

from utils.llm.vertex_direct_attempt import request_body


def test_null_generation_config_passes_through():
    body = json.dumps({"generationConfig": None}).encode()
    result = request_body(body)
    assert result == {"generationConfig": None}


def test_null_thinking_config_passes_through():
    body = json.dumps({"generationConfig": {"thinkingConfig": None}}).encode()
    result = request_body(body)
    assert result == {"generationConfig": {"thinkingConfig": None}}


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "",
        123,
        True,
        False,
        None,
    ],
)
def test_non_object_body_passes_through(payload):
    body = json.dumps(payload).encode()
    result = request_body(body)
    assert result == payload


def test_valid_object_unchanged():
    payload = {
        "generationConfig": {
            "thinkingConfig": {"thinkingBudget": 0},
            "temperature": 0.7,
        },
        "other": "value",
    }
    body = json.dumps(payload).encode()
    result = request_body(body)
    assert result == payload
