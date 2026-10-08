"""The v2 request signature that chat-tool calls carry (#20939).

v2 signs the whole request (method, path, canonical query, body, delivery id and event) so a
captured call cannot be replayed with other arguments, against a sibling tool, with another
method or as a webhook. These tests pin the receiver contract byte for byte; the plugin SDK's copy
(``plugins/omi-plugin-sdk``) asserts the same golden vectors, so the two cannot drift.
"""

import hashlib
import hmac
from urllib.parse import parse_qsl

import pytest

from utils import webhook_signing as signing

SECRET = 'whsec_example_secret_do_not_use'
PREVIOUS = 'whsec_previous_secret'
T = 1760000000
DELIVERY = '6f1c2a9e-4b7d-4e2a-9c1f-0d3b5a7e8f21'
GET_PATH = '/api/tools/search_notes'
GET_QUERY = 'app_id=01KAPP&limit=5&query=caf%C3%A9%20%26%20tea%2Bmilk&tags=b&tags=a&tool_name=search_notes&uid=u1AbC'
GET_SIGNATURE = '0157d30339830cdd2fb5511bb6068af79ba301437c4da0751a887f612e2ea8ed'
POST_PATH = '/tools/like_tweet'
POST_BODY = b'{"tweet_id":"1850000000000000000","uid":"u1AbC","app_id":"01KAPP","tool_name":"like_tweet"}'
POST_SIGNATURE = '9d3ed16fc991fc13e7ad331370b40bce79b174cc60865b7c919033e7c6163452'


def _headers(signature_value, *, delivery=DELIVERY, event='chat_tool'):
    return {
        'X-Omi-Signature': signature_value,
        'X-Omi-Delivery': delivery,
        'X-Omi-Event': event,
    }


def _verify(headers, body=b'', *, method='GET', path=GET_PATH, query=GET_QUERY, secret=SECRET, now=T + 10):
    return signing.verify_request(headers, body, secret, method=method, path=path, query=query, now=now)


GET_HEADERS = _headers(f't={T},v2={GET_SIGNATURE}')
POST_HEADERS = _headers(f't={T},v2={POST_SIGNATURE}')


@pytest.mark.parametrize(
    'pairs, expected',
    [
        ([('q', 'a b')], 'q=a%20b'),
        ([('q', 'a+b')], 'q=a%2Bb'),
        ([('q', 'x&y=z')], 'q=x%26y%3Dz'),
        ([('q', 'café')], 'q=caf%C3%A9'),
        ([('q', 'café')], 'q=cafe%CC%81'),
        ([('q', '\U0001f642')], 'q=%F0%9F%99%82'),
        ([('q', "it's (ok)!*")], 'q=it%27s%20%28ok%29%21%2A'),
        ([('q', '~-._')], 'q=~-._'),
        ([('b', '2'), ('a', '1'), ('b', '1')], 'a=1&b=2&b=1'),
        ([('flag', '')], 'flag='),
        ([], ''),
        ([('a b', '1')], 'a%20b=1'),
        ([('Z', '1'), ('a', '1'), ('_', '1'), ('é', '1')], '%C3%A9=1&Z=1&_=1&a=1'),
    ],
)
def test_canonical_query_vectors(pairs, expected):
    assert signing.canonical_query(pairs) == expected


def test_canonical_query_keeps_nfc_and_nfd_apart():
    assert signing.canonical_query([('q', 'café')]) != signing.canonical_query([('q', 'café')])


def test_canonical_query_refuses_a_lone_surrogate():
    with pytest.raises(UnicodeEncodeError):
        signing.canonical_query([('q', '\ud800')])


@pytest.mark.parametrize(
    'path, expected',
    [
        ('/tools/get_recovery', '/tools/get_recovery'),
        ('/tools/%7Euser', '/tools/~user'),
        ('/tools/%7euser', '/tools/~user'),
        ('/tools/a%2fb', '/tools/a%2Fb'),
        ('/tools/caf%c3%a9', '/tools/caf%C3%A9'),
        ('/tools/café', '/tools/caf%C3%A9'),
        ('/tools/a b', '/tools/a%20b'),
        ('/a//b', '/a//b'),
        ('/a/../b', '/a/../b'),
        ('/tools\\x', '/tools%5Cx'),
        ('', '/'),
        ('/', '/'),
    ],
)
def test_canonical_path_vectors(path, expected):
    assert signing.canonical_path(path) == expected


def test_string_to_sign_is_eight_parts_with_the_v2_label_first():
    message = signing.request_string_to_sign(
        timestamp=T, delivery_id=DELIVERY, event='chat_tool', method='post', path=POST_PATH, query='', body=POST_BODY
    )
    assert message == (
        b'v2\n1760000000\n' + DELIVERY.encode() + b'\nchat_tool\nPOST\n/tools/like_tweet\n\n' + POST_BODY
    )


def test_golden_vectors_match_the_sdk_and_the_docs():
    get = signing.compute_request_signature(
        SECRET,
        timestamp=T,
        delivery_id=DELIVERY,
        event='chat_tool',
        method='GET',
        path=GET_PATH,
        query=GET_QUERY,
        body=b'',
    )
    post = signing.compute_request_signature(
        SECRET,
        timestamp=T,
        delivery_id=DELIVERY,
        event='chat_tool',
        method='POST',
        path=POST_PATH,
        query='',
        body=POST_BODY,
    )
    assert (get, post) == (GET_SIGNATURE, POST_SIGNATURE)


@pytest.mark.parametrize('part', ['delivery_id', 'event', 'method'])
@pytest.mark.parametrize('bad', ['', 'a\nb', 'a\rb', 'café'])
def test_string_to_sign_refuses_header_parts_that_could_break_the_framing(part, bad):
    parts = {'delivery_id': DELIVERY, 'event': 'chat_tool', 'method': 'GET'}
    parts[part] = bad
    with pytest.raises(ValueError):
        signing.request_string_to_sign(timestamp=T, path='/', query='', body=b'', **parts)


def test_verify_accepts_the_golden_requests_with_raw_or_parsed_queries():
    assert _verify(GET_HEADERS) is True
    assert _verify(GET_HEADERS, query=parse_qsl(GET_QUERY, keep_blank_values=True)) is True
    assert _verify(POST_HEADERS, POST_BODY, method='POST', path=POST_PATH, query='') is True


@pytest.mark.parametrize(
    'query',
    [
        GET_QUERY.replace('limit=5', 'limit=500'),
        GET_QUERY.replace('uid=u1AbC', 'uid=victim'),
        GET_QUERY + '&uid=victim',
        GET_QUERY + '&extra=1',
        GET_QUERY.replace('tags=b&tags=a', 'tags=a&tags=b'),
        GET_QUERY.replace('&limit=5', ''),
    ],
    ids=['altered-argument', 'swapped-uid', 'appended-uid', 'added-argument', 'reordered-list', 'dropped-argument'],
)
def test_a_captured_get_replayed_with_altered_arguments_fails(query):
    assert _verify(GET_HEADERS, query=query) is False


@pytest.mark.parametrize(
    'query',
    [
        GET_QUERY.replace('%20', '+'),
        'uid=u1AbC&' + GET_QUERY.replace('&uid=u1AbC', ''),
        GET_QUERY.replace('caf%C3%A9', 'caf%c3%a9'),
    ],
    ids=['plus-for-space', 'distinct-key-moved', 'lowercase-hex'],
)
def test_rewrites_that_do_not_change_the_decoded_request_still_verify(query):
    assert _verify(GET_HEADERS, query=query) is True


def test_a_captured_post_replayed_against_a_sibling_tool_fails():
    assert _verify(POST_HEADERS, POST_BODY, method='POST', path='/tools/unlike_tweet', query='') is False
    assert _verify(POST_HEADERS, POST_BODY, method='POST', path='/tools/delete_tweet', query='') is False


@pytest.mark.parametrize(
    'path',
    [
        '/tools/x/../like_tweet',
        '/tools/x/%2e%2e/like_tweet',
        '/tools/./like_tweet',
        '/tools\\like_tweet',
        '/tools//like_tweet',
        '/tools/like_tweet/',
    ],
)
def test_paths_that_a_url_parser_would_normalise_to_the_signed_path_fail(path):
    # Dot segments and backslashes are not resolved: a receiver must verify the raw path it routes on.
    assert _verify(POST_HEADERS, POST_BODY, method='POST', path=path, query='') is False


def test_a_captured_post_with_a_changed_body_or_added_query_fails():
    assert (
        _verify(POST_HEADERS, POST_BODY.replace(b'u1AbC', b'victim'), method='POST', path=POST_PATH, query='') is False
    )
    assert _verify(POST_HEADERS, POST_BODY, method='POST', path=POST_PATH, query='uid=victim') is False


def test_get_and_post_cannot_be_swapped():
    assert _verify(GET_HEADERS, GET_QUERY.encode(), method='POST', query='') is False
    assert _verify(GET_HEADERS, method='POST') is False
    assert _verify(POST_HEADERS, b'', method='GET', path=POST_PATH, query='') is False
    assert _verify(POST_HEADERS, POST_BODY, method='PUT', path=POST_PATH, query='') is False


def test_the_delivery_id_and_event_are_signed():
    assert _verify(_headers(f't={T},v2={GET_SIGNATURE}', delivery='another-delivery')) is False
    assert _verify(_headers(f't={T},v2={GET_SIGNATURE}', event='memory_created')) is False


@pytest.mark.parametrize('now', [T + 301, T - 301])
def test_stale_or_future_timestamps_fail(now):
    assert _verify(GET_HEADERS, now=now) is False


def test_wrong_secret_fails():
    assert _verify(GET_HEADERS, secret=PREVIOUS) is False


def test_rotation_header_verifies_against_either_secret():
    url, headers = signing.signed_request(
        [SECRET, PREVIOUS],
        method='GET',
        url='https://tools.example.com' + GET_PATH + '?' + GET_QUERY,
        body=b'',
        event='chat_tool',
        delivery_id=DELIVERY,
        timestamp=T,
    )
    assert headers['X-Omi-Signature'].count('v2=') == 2
    assert _verify(headers) is True
    assert _verify(headers, secret=PREVIOUS) is True


def test_v1_and_v2_signatures_never_verify_as_each_other():
    v1 = signing.compute_signature(SECRET, T, 'u1AbC', POST_BODY)
    v1_headers = _headers(f't={T},v1={v1}')
    assert _verify(v1_headers, POST_BODY, method='POST', path=POST_PATH, query='') is False
    assert signing.verify(POST_HEADERS, POST_BODY, SECRET, uid='u1AbC', now=T + 10) is False
    # Even a v1 value relabelled as v2 (or the reverse) is a different message, so it cannot verify.
    assert _verify(_headers(f't={T},v2={v1}'), POST_BODY, method='POST', path=POST_PATH, query='') is False
    assert signing.verify(_headers(f't={T},v1={POST_SIGNATURE}'), POST_BODY, SECRET, uid='u1AbC', now=T + 10) is False


@pytest.mark.parametrize(
    'headers',
    [
        {},
        _headers(''),
        _headers(f't={T}'),
        _headers(f'v2={GET_SIGNATURE}'),
        _headers(f't=abc,v2={GET_SIGNATURE}'),
        _headers(f't={T},v2=éé'),
        {'X-Omi-Signature': f't={T},v2={GET_SIGNATURE}', 'X-Omi-Event': 'chat_tool'},
        {'X-Omi-Signature': f't={T},v2={GET_SIGNATURE}', 'X-Omi-Delivery': DELIVERY},
        _headers(f't={T},v2={GET_SIGNATURE}', delivery='a\nb'),
        _headers(f't={T},v2={GET_SIGNATURE}', delivery='café'),
    ],
    ids=[
        'no-headers',
        'empty-signature',
        'no-v2',
        'no-timestamp',
        'bad-timestamp',
        'non-ascii-signature',
        'no-delivery',
        'no-event',
        'newline-delivery',
        'non-ascii-delivery',
    ],
)
def test_malformed_headers_are_a_clean_false(headers):
    assert _verify(headers) is False


def test_headers_are_found_case_insensitively():
    lowered = {key.lower(): value for key, value in GET_HEADERS.items()}
    assert _verify(lowered) is True


def test_a_str_body_is_refused_and_bytes_like_bodies_are_accepted():
    assert _verify(POST_HEADERS, POST_BODY.decode(), method='POST', path=POST_PATH, query='') is False
    assert _verify(POST_HEADERS, bytearray(POST_BODY), method='POST', path=POST_PATH, query='') is True
    assert _verify(POST_HEADERS, memoryview(POST_BODY), method='POST', path=POST_PATH, query='') is True


def test_unencodable_or_malformed_query_input_is_false_not_an_exception():
    assert _verify(GET_HEADERS, query=[('q', '\ud800')]) is False
    assert _verify(GET_HEADERS, query=[('only-one',)]) is False


def test_signed_request_sends_the_canonical_query_and_signs_what_httpx_sends():
    url, headers = signing.signed_request(
        [SECRET],
        method='POST',
        url='https://app.example/a/./tools/../tools/x?b=2&a=caf%c3%a9+x#fragment',
        body=b'{}',
        event='chat_tool',
        delivery_id=DELIVERY,
        timestamp=T,
    )
    assert url == 'https://app.example/a/./tools/../tools/x?a=caf%C3%A9%20x&b=2'
    expected = hmac.new(
        SECRET.encode(),
        b'v2\n1760000000\n' + DELIVERY.encode() + b'\nchat_tool\nPOST\n/a/tools/x\na=caf%C3%A9%20x&b=2\n{}',
        hashlib.sha256,
    ).hexdigest()
    assert headers == {
        'X-Omi-Signature': f't={T},v2={expected}',
        'X-Omi-Event': 'chat_tool',
        'X-Omi-Delivery': DELIVERY,
    }
    assert _verify(headers, b'{}', method='POST', path='/a/tools/x', query='a=caf%C3%A9%20x&b=2') is True


def test_signed_request_replaces_the_query_with_the_given_pairs():
    url, headers = signing.signed_request(
        [SECRET],
        method='GET',
        url='https://app.example/tools/x?stale=1',
        body=b'',
        event='chat_tool',
        delivery_id=DELIVERY,
        query_pairs=[('q', 'a b')],
        timestamp=T,
    )
    assert url == 'https://app.example/tools/x?q=a%20b'
    assert _verify(headers, path='/tools/x', query='q=a%20b') is True


def test_signed_request_requires_a_secret():
    with pytest.raises(ValueError):
        signing.signed_request([], method='GET', url='https://app.example/', body=b'', event='e', delivery_id='d')
