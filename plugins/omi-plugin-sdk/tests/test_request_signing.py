"""verify_request: the v2 signature Omi puts on chat-tool calls.

The golden vectors are the same ones the backend suite (backend/tests/unit/test_request_signing.py)
and docs/doc/developer/apps/ChatTools.mdx use, so the SDK copy cannot drift from the sender.
"""

import hashlib
import hmac
from urllib.parse import parse_qsl

import pytest

from omi_plugin_sdk import verify_request, verify_signature
from omi_plugin_sdk.webhook_signing import (
    canonical_path,
    canonical_query,
    compute_request_signature,
    compute_signature,
    request_string_to_sign,
)

SECRET = "whsec_example_secret_do_not_use"
PREVIOUS = "whsec_previous_secret"
T = 1760000000
DELIVERY = "6f1c2a9e-4b7d-4e2a-9c1f-0d3b5a7e8f21"
GET_PATH = "/api/tools/search_notes"
GET_QUERY = "app_id=01KAPP&limit=5&query=caf%C3%A9%20%26%20tea%2Bmilk&tags=b&tags=a&tool_name=search_notes&uid=u1AbC"
GET_SIGNATURE = "0157d30339830cdd2fb5511bb6068af79ba301437c4da0751a887f612e2ea8ed"
POST_PATH = "/tools/like_tweet"
POST_BODY = b'{"tweet_id":"1850000000000000000","uid":"u1AbC","app_id":"01KAPP","tool_name":"like_tweet"}'
POST_SIGNATURE = "9d3ed16fc991fc13e7ad331370b40bce79b174cc60865b7c919033e7c6163452"


def _headers(*signatures, delivery=DELIVERY, event="chat_tool", timestamp=T):
    value = ",".join([f"t={timestamp}", *(f"v2={s}" for s in signatures)])
    return {"X-Omi-Signature": value, "X-Omi-Delivery": delivery, "X-Omi-Event": event}


def _verify(headers, body=b"", *, method="GET", path=GET_PATH, query=GET_QUERY, secret=SECRET, now=T + 10):
    return verify_request(headers, body, secret, method=method, path=path, query=query, now=now)


def test_golden_vectors():
    # Built by hand so the test pins the wire format rather than trusting the module under test.
    message = b"v2\n1760000000\n" + DELIVERY.encode() + b"\nchat_tool\nPOST\n/tools/like_tweet\n\n" + POST_BODY
    assert hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest() == POST_SIGNATURE
    common = {"timestamp": T, "delivery_id": DELIVERY, "event": "chat_tool"}
    assert request_string_to_sign(method="POST", path=POST_PATH, query="", body=POST_BODY, **common) == message
    assert compute_request_signature(SECRET, method="POST", path=POST_PATH, query="", body=POST_BODY, **common) == (
        POST_SIGNATURE
    )
    assert compute_request_signature(SECRET, method="GET", path=GET_PATH, query=GET_QUERY, body=b"", **common) == (
        GET_SIGNATURE
    )


@pytest.mark.parametrize(
    "pairs, expected",
    [
        ([("q", "a b")], "q=a%20b"),
        ([("q", "a+b")], "q=a%2Bb"),
        ([("q", "x&y=z")], "q=x%26y%3Dz"),
        ([("q", "café")], "q=caf%C3%A9"),
        ([("q", "café")], "q=cafe%CC%81"),
        ([("q", "\U0001f642")], "q=%F0%9F%99%82"),
        ([("q", "it's (ok)!*")], "q=it%27s%20%28ok%29%21%2A"),
        ([("q", "~-._")], "q=~-._"),
        ([("b", "2"), ("a", "1"), ("b", "1")], "a=1&b=2&b=1"),
        ([("flag", "")], "flag="),
        ([], ""),
        ([("a b", "1")], "a%20b=1"),
        ([("Z", "1"), ("a", "1"), ("_", "1"), ("é", "1")], "%C3%A9=1&Z=1&_=1&a=1"),
    ],
)
def test_canonical_query_vectors(pairs, expected):
    assert canonical_query(pairs) == expected


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/tools/get_recovery", "/tools/get_recovery"),
        ("/tools/%7euser", "/tools/~user"),
        ("/tools/a%2fb", "/tools/a%2Fb"),
        ("/tools/café", "/tools/caf%C3%A9"),
        ("/tools/a b", "/tools/a%20b"),
        ("", "/"),
        ("/a/../b", "/a/../b"),
        ("/tools\\x", "/tools%5Cx"),
    ],
)
def test_canonical_path_vectors(path, expected):
    assert canonical_path(path) == expected


def test_verify_accepts_the_golden_requests():
    assert _verify(_headers(GET_SIGNATURE)) is True
    assert _verify(_headers(GET_SIGNATURE), query=parse_qsl(GET_QUERY, keep_blank_values=True)) is True
    assert _verify(_headers(POST_SIGNATURE), POST_BODY, method="POST", path=POST_PATH, query="") is True


@pytest.mark.parametrize(
    "query",
    [
        GET_QUERY.replace("limit=5", "limit=500"),
        GET_QUERY.replace("uid=u1AbC", "uid=victim"),
        GET_QUERY + "&uid=victim",
        GET_QUERY.replace("tags=b&tags=a", "tags=a&tags=b"),
    ],
)
def test_altered_arguments_fail(query):
    assert _verify(_headers(GET_SIGNATURE), query=query) is False


def test_rewrites_with_the_same_decoded_request_still_verify():
    assert _verify(_headers(GET_SIGNATURE), query=GET_QUERY.replace("%20", "+")) is True
    assert _verify(_headers(GET_SIGNATURE), query="uid=u1AbC&" + GET_QUERY.replace("&uid=u1AbC", "")) is True


def test_sibling_path_method_swap_delivery_and_event_fail():
    post = _headers(POST_SIGNATURE)
    assert _verify(post, POST_BODY, method="POST", path="/tools/unlike_tweet", query="") is False
    assert _verify(post, POST_BODY, method="PUT", path=POST_PATH, query="") is False
    assert _verify(_headers(GET_SIGNATURE), GET_QUERY.encode(), method="POST", query="") is False
    assert _verify(_headers(GET_SIGNATURE, delivery="other")) is False
    assert _verify(_headers(GET_SIGNATURE, event="memory_created")) is False


@pytest.mark.parametrize(
    "path",
    [
        "/tools/x/../like_tweet",
        "/tools/x/%2e%2e/like_tweet",
        "/tools/./like_tweet",
        "/tools\\like_tweet",
        "/tools//like_tweet",
    ],
)
def test_paths_a_url_parser_would_normalise_to_the_signed_path_fail(path):
    # Dot segments and backslashes are not resolved: verify the raw path you route on.
    assert _verify(_headers(POST_SIGNATURE), POST_BODY, method="POST", path=path, query="") is False


@pytest.mark.parametrize("now", [T + 301, T - 301])
def test_stale_and_future_timestamps_fail(now):
    assert _verify(_headers(GET_SIGNATURE), now=now) is False


def test_rotation_header_verifies_against_either_secret():
    common = {"timestamp": T, "delivery_id": DELIVERY, "event": "chat_tool", "method": "GET", "path": GET_PATH}
    previous = compute_request_signature(PREVIOUS, query=GET_QUERY, body=b"", **common)
    headers = _headers(GET_SIGNATURE, previous)
    assert _verify(headers) is True
    assert _verify(headers, secret=PREVIOUS) is True
    assert _verify(headers, secret="whsec_never-issued") is False


def test_v1_and_v2_are_never_accepted_for_each_other():
    v1 = compute_signature(SECRET, T, "u1AbC", POST_BODY)
    v1_headers = {"X-Omi-Signature": f"t={T},v1={v1}", "X-Omi-Delivery": DELIVERY, "X-Omi-Event": "chat_tool"}
    assert _verify(v1_headers, POST_BODY, method="POST", path=POST_PATH, query="") is False
    assert verify_signature(_headers(POST_SIGNATURE), POST_BODY, SECRET, uid="u1AbC", now=T + 10) is False


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Omi-Signature": f"t={T},v2={GET_SIGNATURE}", "X-Omi-Event": "chat_tool"},
        {"X-Omi-Signature": f"t={T},v2={GET_SIGNATURE}", "X-Omi-Delivery": DELIVERY},
        _headers(),
        _headers(GET_SIGNATURE, delivery="a\nb"),
        _headers(GET_SIGNATURE, delivery="café"),
        _headers("éé"),
        {"X-Omi-Signature": f"t=abc,v2={GET_SIGNATURE}", "X-Omi-Delivery": DELIVERY, "X-Omi-Event": "chat_tool"},
    ],
)
def test_malformed_headers_are_a_clean_false(headers):
    assert _verify(headers) is False


def test_headers_are_case_insensitive_and_bodies_must_be_bytes():
    lowered = {key.lower(): value for key, value in _headers(POST_SIGNATURE).items()}
    assert _verify(lowered, POST_BODY, method="POST", path=POST_PATH, query="") is True
    assert _verify(lowered, POST_BODY.decode(), method="POST", path=POST_PATH, query="") is False
    assert _verify(lowered, memoryview(POST_BODY), method="POST", path=POST_PATH, query="") is True


def test_unencodable_or_malformed_query_input_is_false():
    assert _verify(_headers(GET_SIGNATURE), query=[("q", "\ud800")]) is False
    assert _verify(_headers(GET_SIGNATURE), query=[("only-one",)]) is False
