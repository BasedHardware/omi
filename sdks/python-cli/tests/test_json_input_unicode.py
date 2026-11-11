"""JSON input must reach the HTTP encoder without losing Unicode data."""

from __future__ import annotations

import json

import httpx
import pytest

from omi_cli.json_input import load_json_input


@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"])
@pytest.mark.parametrize("location", ["root", "value", "key", "nested"])
def test_rejects_surrogates_before_http_encoding(surrogate, location) -> None:
    values = {
        "root": surrogate,
        "value": {"text": surrogate},
        "key": {surrogate: "text"},
        "nested": {"items": [{"text": surrogate}]},
    }
    with pytest.raises(ValueError, match="surrogates not allowed"):
        load_json_input(json.dumps(values[location]))


@pytest.mark.parametrize("encoding", [None, "utf-8", "utf-16", "utf-32"])
def test_preserves_unicode_and_can_encode_http_request(encoding) -> None:
    value = {"ș😀": ["日本語", "\\ud800", "", None, True, 42, -1.5e2, 1e300]}
    raw = json.dumps(value, ensure_ascii=encoding is None)
    decoded = load_json_input(raw if encoding is None else raw.encode(encoding))
    assert decoded == value
    request = httpx.Request("POST", "https://example.invalid", json=decoded)
    assert json.loads(request.content) == value


@pytest.mark.parametrize("raw", ['"\\ud800"', '{"\\udfff": 1}', '[{"text":"\\ud800"}]'])
def test_byte_inputs_reject_surrogates(raw) -> None:
    with pytest.raises(ValueError, match="surrogates not allowed"):
        load_json_input(raw.encode("utf-16"))


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400"])
def test_preserves_non_finite_number_rejection(number) -> None:
    with pytest.raises(ValueError, match="finite"):
        load_json_input('{"nested":[' + number + ']}')
