"""The desktop proxy's per-attempt Gemini wire adapter must tolerate explicit-null optional fields.

`request_body` runs on the raw client body. A body with `generationConfig: null` (or a null
`thinkingConfig`, or a non-object JSON document) previously raised AttributeError/TypeError and
500'd the streaming proxy instead of passing the body through.
"""

from utils.llm import vertex_direct_attempt

URL = 'https://x/v1/models/gemini-2.5-flash:generateContent'


def test_null_generation_config_is_passed_through():
    body = b'{"contents": [], "generationConfig": null}'
    assert vertex_direct_attempt.request_body(body, URL) == body


def test_null_thinking_config_is_passed_through():
    body = b'{"generationConfig": {"thinkingConfig": null}}'
    assert vertex_direct_attempt.request_body(body, URL) == body


def test_non_object_body_is_passed_through():
    body = b'[]'
    assert vertex_direct_attempt.request_body(body, URL) == body


def test_payload_without_thinking_level_is_passed_through():
    body = b'{"contents": []}'
    assert vertex_direct_attempt.request_body(body, URL) == body


def test_non_gemini_url_is_passed_through():
    body = b'not json at all'
    assert vertex_direct_attempt.request_body(body, 'https://x/v1/other') == body
