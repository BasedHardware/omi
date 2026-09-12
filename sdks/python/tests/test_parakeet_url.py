from urllib.parse import parse_qs, urlsplit

import pytest

from omi.stt.parakeet import parakeet_ws_url


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        (
            "https://parakeet.example/",
            "wss://parakeet.example/v3/stream?sample_rate=16000",
        ),
        (
            "http://localhost:8080/proxy/",
            "ws://localhost:8080/proxy/v3/stream?sample_rate=16000",
        ),
        (
            "wss://parakeet.example",
            "wss://parakeet.example/v3/stream?sample_rate=16000",
        ),
    ],
)
def test_plain_base_urls_remain_supported(base, expected):
    assert parakeet_ws_url(base) == expected


def test_query_belongs_after_stream_path():
    result = urlsplit(
        parakeet_ws_url("https://parakeet.example/proxy?tenant=demo", 8000)
    )
    assert result.path == "/proxy/v3/stream"
    assert parse_qs(result.query) == {"tenant": ["demo"], "sample_rate": ["8000"]}


def test_url_inside_query_is_not_rewritten():
    result = urlsplit(
        parakeet_ws_url("https://parakeet.example?origin=https://demo.example/")
    )
    assert parse_qs(result.query)["origin"] == ["https://demo.example/"]


def test_query_preserves_repeated_and_blank_values():
    result = urlsplit(
        parakeet_ws_url("https://parakeet.example?tag=a&tag=b&empty=&token=a%2Bb%2F")
    )
    assert parse_qs(result.query, keep_blank_values=True) == {
        "tag": ["a", "b"],
        "empty": [""],
        "token": ["a+b/"],
        "sample_rate": ["16000"],
    }


def test_explicit_sample_rate_replaces_existing_query_value():
    result = urlsplit(
        parakeet_ws_url(
            "https://parakeet.example?sample_rate=8000&sample_rate=44100", 16000
        )
    )
    assert parse_qs(result.query) == {"sample_rate": ["16000"]}


def test_fragment_is_not_sent_to_websocket():
    result = urlsplit(
        parakeet_ws_url("https://parakeet.example/proxy?tenant=demo#section")
    )
    assert result.fragment == ""
    assert result.path == "/proxy/v3/stream"
    assert parse_qs(result.query) == {"tenant": ["demo"], "sample_rate": ["16000"]}
