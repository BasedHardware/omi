"""Tests for the Omi chat client.

`POST /v2/messages` advertises `text/event-stream` and is not spec SSE: frames
are `\\n\\n`-*separated* records with a bare prefix, `data:`/`think:` carry a
literal `__CRLF__` in place of a newline, and the terminal `done:` frame is
base64 JSON. Every one of those is a place where a plausible-looking
implementation silently corrupts the answer rather than failing, so the tests
below pin the exact bytes rather than the general shape.

Two properties get hammered hardest, because they are the ones a network makes
non-deterministic in production and deterministic here:

* frame boundaries never line up with chunk boundaries;
* a stream can simply stop -- Omi's agent may run to 150s behind a 120s
  request timeout, dying as a bare 504 with no terminal frame.
"""

import asyncio
import base64
import json
import random
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conftest import FakeAuth, install_mock_transport, streaming_body  # noqa: E402
from omi_client import ChatEvent, OmiClient, parse_frame  # noqa: E402


def b64(payload) -> str:
    return base64.b64encode(json.dumps(payload).encode('utf-8')).decode('ascii')


def done_frame(text: str, **extra) -> bytes:
    return b'done: ' + b64({'text': text, 'id': 'msg-1', **extra}).encode('ascii')


# --------------------------------------------------------------------------
# parse_frame -- data / think
# --------------------------------------------------------------------------


def test_data_frame_yields_the_token():
    event = parse_frame('data: The battery regression')
    assert event == ChatEvent('data', 'The battery regression')


def test_data_frame_unescapes_the_literal_crlf_marker():
    """`__CRLF__` is how Omi transports a newline through a `\\n\\n`-framed
    protocol. Leaving it un-substituted puts the literal token on the glasses.
    """
    event = parse_frame('data: Line one__CRLF__Line two')
    assert event.text == 'Line one\nLine two'
    assert '__CRLF__' not in event.text


def test_data_frame_unescapes_every_crlf_marker_not_just_the_first():
    event = parse_frame('data: a__CRLF__b__CRLF__c')
    assert event.text == 'a\nb\nc'


def test_think_frame_unescapes_the_crlf_marker_too():
    event = parse_frame('think: Searching memories__CRLF__Reading conversations')
    assert event.kind == 'think'
    assert event.text == 'Searching memories\nReading conversations'


def test_data_frame_preserves_leading_and_trailing_spaces():
    """Deltas are concatenated verbatim. Stripping them welds words together:
    "The"+"battery" instead of "The battery".
    """
    assert parse_frame('data:  battery').text == ' battery'
    assert parse_frame('data: battery ').text == 'battery '
    assert parse_frame('data:   ').text == '  '


def test_data_frame_with_an_empty_payload_is_still_a_data_event():
    event = parse_frame('data: ')
    assert event == ChatEvent('data', '')


def test_data_frame_keeps_a_colon_in_the_payload():
    assert parse_frame('data: note: ship it').text == 'note: ship it'


# --------------------------------------------------------------------------
# parse_frame -- errors
# --------------------------------------------------------------------------


def test_legacy_402_frame_has_no_space_after_the_colon():
    """`error:402:` is checked before `error: ` and strips the whole prefix.

    A parser that treats the two as one `error:` check leaves `402:` glued to
    the front of the user-visible message.
    """
    event = parse_frame('error:402:You have used all of your credits')
    assert event.kind == 'error'
    assert event.text == 'You have used all of your credits'
    assert not event.text.startswith('402')


def test_402_frame_is_not_confused_with_a_spaced_error_frame():
    spaced = parse_frame('error: 402 payment required')
    assert spaced.text == '402 payment required'
    legacy = parse_frame('error:402:payment required')
    assert legacy.text == 'payment required'


def test_error_frame_strips_surrounding_whitespace():
    assert parse_frame('error: Something broke   ').text == 'Something broke'


def test_empty_error_frame_still_carries_a_message():
    """An empty error would render as a blank screen -- worse than a wrong one."""
    event = parse_frame('error: ')
    assert event.kind == 'error'
    assert event.text.strip(), 'an error frame must never yield an empty message'
    assert event.text == 'Omi returned an unspecified error'


def test_whitespace_only_error_frame_still_carries_a_message():
    assert parse_frame('error:    \t ').text == 'Omi returned an unspecified error'


def test_error_without_a_space_and_without_402_is_unrecognized():
    """Pins the prefix set exactly: only `error: ` and `error:402:` are errors.

    Anything else is dropped, which surfaces as a truncated stream rather than
    a mislabelled one.
    """
    assert parse_frame('error:no space here') is None


# --------------------------------------------------------------------------
# parse_frame -- terminal frames
# --------------------------------------------------------------------------


def test_done_frame_decodes_base64_json():
    event = parse_frame('done: ' + b64({'text': 'All clear.', 'id': 'msg-9'}))
    assert event.kind == 'done'
    assert event.text == 'All clear.'
    assert event.message == {'text': 'All clear.', 'id': 'msg-9'}


def test_message_frame_decodes_base64_json():
    event = parse_frame('message: ' + b64({'text': 'what is on my plate', 'sender': 'human'}))
    assert event.kind == 'message'
    assert event.text == 'what is on my plate'
    assert event.message['sender'] == 'human'


def test_done_frame_without_a_text_key_yields_empty_text_not_a_crash():
    event = parse_frame('done: ' + b64({'id': 'msg-9'}))
    assert event.kind == 'done'
    assert event.text == ''
    assert event.message == {'id': 'msg-9'}


@pytest.mark.parametrize(
    'payload',
    [
        'not base64 at all!!',
        '',
        '=====',
        base64.b64encode(b'\xff\xfe\xfd not utf-8').decode('ascii'),
        base64.b64encode(b'{not json}').decode('ascii'),
        base64.b64encode(b'{"text": "unterminated').decode('ascii'),
    ],
)
def test_malformed_terminal_payloads_never_raise(payload):
    """A corrupt terminal frame must degrade to "no answer", not an exception:
    `parse_frame` runs inside the stream loop with no handler around it.
    """
    event = parse_frame('done: ' + payload)
    assert event.kind == 'done'
    assert event.text == ''
    assert event.message is None


@pytest.mark.parametrize('payload', ['[1, 2, 3]', '"a bare string"', '123', 'null', 'true'])
def test_terminal_frame_that_is_valid_json_but_not_an_object_never_raises(payload):
    """Regression: `_decode_b64_json` is typed `dict | None` but `json.loads`
    happily returns lists, strings and numbers, and `parse_frame` then called
    `.get()` on them -- an AttributeError straight out of the stream loop.
    """
    encoded = base64.b64encode(payload.encode()).decode('ascii')
    for prefix in ('done: ', 'message: '):
        event = parse_frame(prefix + encoded)
        assert event.text == ''
        assert event.message is None


def test_done_frame_carries_the_full_decoded_message_for_the_caller():
    body = {'text': 'ok', 'id': 'm1', 'memories': [{'id': 'x'}], 'type': 'text'}
    event = parse_frame('done: ' + b64(body))
    assert event.message == body


# --------------------------------------------------------------------------
# parse_frame -- unrecognized input
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    'frame',
    [
        '',
        '   ',
        'ping',
        ': keepalive',
        'event: message',
        'id: 42',
        'retry: 3000',
        'data:no space',
        'think:no space',
        'done:no space',
        'DATA: uppercase',
        '{"text": "raw json, not a frame"}',
        'garbage',
    ],
)
def test_unrecognized_frames_return_none(frame):
    assert parse_frame(frame) is None


def test_parse_frame_never_raises_on_random_input():
    rng = random.Random(20240727)
    prefixes = ['data: ', 'think: ', 'done: ', 'message: ', 'error: ', 'error:402:', '', 'x: ']
    alphabet = 'abz09 :\n\t=+/{}"[]' + '__CRLF__'
    for _ in range(2000):
        frame = rng.choice(prefixes) + ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        result = parse_frame(frame)
        assert result is None or isinstance(result, ChatEvent)


# --------------------------------------------------------------------------
# chat_stream -- request shape
# --------------------------------------------------------------------------


def make_client(monkeypatch, chunks, status=200, auth=None):
    """An OmiClient whose one HTTP call replays `chunks` as the response body."""

    def handler(request):
        return httpx.Response(status, content=streaming_body(chunks))

    requests = install_mock_transport(monkeypatch, handler)
    return OmiClient(auth or FakeAuth(), 'https://api.omi.me'), requests


async def collect(stream):
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_chat_stream_posts_the_expected_request(monkeypatch):
    client, requests = make_client(monkeypatch, [done_frame('hi')])
    await collect(client.chat_stream('what is on my plate'))

    assert len(requests) == 1
    request = requests[0]
    assert request.method == 'POST'
    assert str(request.url) == 'https://api.omi.me/v2/messages'
    assert request.headers['authorization'] == 'Bearer fake-id-token'
    assert request.headers['content-type'] == 'application/json'
    assert json.loads(request.content) == {'text': 'what is on my plate', 'file_ids': []}
    # Deliberately absent: only `desktop` is trial-paywalled, and a skewed
    # X-Request-Start-Time is rejected with a 408.
    assert 'x-app-platform' not in request.headers
    assert 'x-request-start-time' not in request.headers


@pytest.mark.asyncio
async def test_chat_stream_passes_app_id_as_a_query_param(monkeypatch):
    client, requests = make_client(monkeypatch, [done_frame('hi')])
    await collect(client.chat_stream('hello', app_id='omi-standup'))
    assert requests[0].url.params['app_id'] == 'omi-standup'


@pytest.mark.asyncio
async def test_chat_stream_omits_the_query_string_without_an_app_id(monkeypatch):
    client, requests = make_client(monkeypatch, [done_frame('hi')])
    await collect(client.chat_stream('hello'))
    assert requests[0].url.query == b''


@pytest.mark.asyncio
async def test_base_url_trailing_slash_is_normalised(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=streaming_body([done_frame('hi')]))

    requests = install_mock_transport(monkeypatch, handler)
    client = OmiClient(FakeAuth(), 'https://api.omi.me/')
    await collect(client.chat_stream('hello'))
    assert str(requests[0].url) == 'https://api.omi.me/v2/messages'


# --------------------------------------------------------------------------
# chat_stream -- framing
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_several_frames_in_one_chunk_are_all_emitted(monkeypatch):
    chunk = b'think: Searching\n\ndata: All\n\ndata:  clear.\n\n' + done_frame('All clear.') + b'\n\n'
    client, _ = make_client(monkeypatch, [chunk])
    events = await collect(client.chat_stream('hi'))
    assert [(e.kind, e.text) for e in events] == [
        ('think', 'Searching'),
        ('data', 'All'),
        ('data', ' clear.'),
        ('done', 'All clear.'),
    ]


@pytest.mark.asyncio
async def test_a_frame_split_across_two_chunks_is_reassembled(monkeypatch):
    client, _ = make_client(monkeypatch, [b'data: All cl', b'ear.\n\n'])
    events = await collect(client.chat_stream('hi'))
    assert [(e.kind, e.text) for e in events] == [('data', 'All clear.')]


@pytest.mark.asyncio
async def test_a_separator_split_across_two_chunks_is_reassembled(monkeypatch):
    """The nastiest boundary: the `\\n\\n` itself straddles two TCP reads."""
    client, _ = make_client(monkeypatch, [b'data: one\n', b'\ndata: two\n\n'])
    events = await collect(client.chat_stream('hi'))
    assert [e.text for e in events] == ['one', 'two']


@pytest.mark.asyncio
async def test_a_final_frame_with_no_trailing_separator_is_still_emitted(monkeypatch):
    """Frames are separated, not terminated -- the tail is a real frame."""
    client, _ = make_client(monkeypatch, [b'data: All clear.\n\n' + done_frame('All clear.')])
    events = await collect(client.chat_stream('hi'))
    assert [e.kind for e in events] == ['data', 'done']
    assert events[-1].text == 'All clear.'


@pytest.mark.asyncio
async def test_a_lone_trailing_separator_does_not_emit_an_empty_frame(monkeypatch):
    client, _ = make_client(monkeypatch, [b'data: hi\n\n\n\n'])
    events = await collect(client.chat_stream('hi'))
    assert [e.text for e in events] == ['hi']


@pytest.mark.asyncio
async def test_whitespace_only_tail_is_not_emitted(monkeypatch):
    client, _ = make_client(monkeypatch, [b'data: hi\n\n   \n  '])
    events = await collect(client.chat_stream('hi'))
    assert [e.text for e in events] == ['hi']


@pytest.mark.asyncio
async def test_unrecognized_frames_are_skipped_without_stopping_the_stream(monkeypatch):
    body = b': keepalive\n\ndata: one\n\nevent: noise\n\ndata: two\n\n'
    client, _ = make_client(monkeypatch, [body])
    events = await collect(client.chat_stream('hi'))
    assert [e.text for e in events] == ['one', 'two']


@pytest.mark.asyncio
async def test_a_single_newline_does_not_terminate_a_frame(monkeypatch):
    """Frames are `\\n\\n`-delimited; a lone `\\n` is content.

    Splitting on `\\n` would truncate this think line at "Searching" and then
    drop "your memories" as an unrecognized frame.
    """
    client, _ = make_client(monkeypatch, [b'think: Searching\nyour memories\n\ndata: hi\n\n'])
    events = await collect(client.chat_stream('hi'))
    assert [(e.kind, e.text) for e in events] == [
        ('think', 'Searching\nyour memories'),
        ('data', 'hi'),
    ]


# A small but complete stream, with every trap in it: a multi-byte character
# (so a naive per-chunk decode corrupts it), a lone newline inside a frame, a
# `__CRLF__` escape, a leading-space delta, and a terminal `done:`.
BOUNDARY_BODY = (
    'think: Searching\nyour memories\n\n'
    'data: The battery\n\n'
    'data:  regression—open\n\n'
    'data: __CRLF__Owner: Sarah\n\n'
    'done: ' + b64({'text': 'The battery regression—open.\nOwner: Sarah'}) + '\n\n'
).encode('utf-8')

BOUNDARY_EXPECTED = [
    ('think', 'Searching\nyour memories'),
    ('data', 'The battery'),
    ('data', ' regression—open'),
    ('data', '\nOwner: Sarah'),
    ('done', 'The battery regression—open.\nOwner: Sarah'),
]


@pytest.mark.asyncio
@pytest.mark.parametrize('split', range(len(BOUNDARY_BODY) + 1))
async def test_every_possible_two_chunk_split_decodes_identically(monkeypatch, split):
    """Exhaustive: the network may break the body at any byte, including in the
    middle of a separator, a base64 payload or a UTF-8 sequence.
    """
    chunks = [c for c in (BOUNDARY_BODY[:split], BOUNDARY_BODY[split:]) if c]
    client, _ = make_client(monkeypatch, chunks)
    events = await collect(client.chat_stream('hi'))
    assert [(e.kind, e.text) for e in events] == BOUNDARY_EXPECTED


@pytest.mark.asyncio
async def test_one_byte_at_a_time_decodes_identically(monkeypatch):
    chunks = [BOUNDARY_BODY[i : i + 1] for i in range(len(BOUNDARY_BODY))]
    client, _ = make_client(monkeypatch, chunks)
    events = await collect(client.chat_stream('hi'))
    assert [(e.kind, e.text) for e in events] == BOUNDARY_EXPECTED


@pytest.mark.asyncio
async def test_random_multi_chunk_splits_decode_identically(monkeypatch):
    rng = random.Random(99)
    for _ in range(40):
        cuts = sorted(rng.sample(range(1, len(BOUNDARY_BODY)), rng.randint(1, 6)))
        bounds = [0, *cuts, len(BOUNDARY_BODY)]
        chunks = [BOUNDARY_BODY[a:b] for a, b in zip(bounds, bounds[1:]) if b > a]
        client, _ = make_client(monkeypatch, chunks)
        events = await collect(client.chat_stream('hi'))
        assert [(e.kind, e.text) for e in events] == BOUNDARY_EXPECTED, f'cuts={cuts}'


@pytest.mark.asyncio
async def test_empty_body_yields_no_events(monkeypatch):
    client, _ = make_client(monkeypatch, [])
    assert await collect(client.chat_stream('hi')) == []


# --------------------------------------------------------------------------
# chat_stream -- transport failures
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_200_yields_exactly_one_error_event(monkeypatch):
    client, _ = make_client(monkeypatch, [b'{"detail": "boom"}'], status=500)
    events = await collect(client.chat_stream('hi'))
    assert len(events) == 1
    assert events[0].kind == 'error'
    assert events[0].text.startswith('HTTP 500:')
    assert 'boom' in events[0].text


@pytest.mark.asyncio
async def test_non_200_body_is_truncated_so_a_html_error_page_cannot_flood_the_glasses(monkeypatch):
    client, _ = make_client(monkeypatch, [b'x' * 100_000], status=502)
    events = await collect(client.chat_stream('hi'))
    assert len(events) == 1
    assert len(events[0].text) <= len('HTTP 502: ') + 300


@pytest.mark.asyncio
async def test_non_200_does_not_parse_the_body_as_frames(monkeypatch):
    """A 401 page that happens to contain `data: ` must not look like an answer."""
    client, _ = make_client(monkeypatch, [b'data: you are not signed in\n\n'], status=401)
    events = await collect(client.chat_stream('hi'))
    assert [e.kind for e in events] == ['error']


@pytest.mark.asyncio
async def test_a_204_with_no_body_is_still_an_error(monkeypatch):
    client, _ = make_client(monkeypatch, [], status=204)
    events = await collect(client.chat_stream('hi'))
    assert [e.kind for e in events] == ['error']
    assert 'HTTP 204' in events[0].text


# --------------------------------------------------------------------------
# chat -- accumulation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_joins_deltas_in_order(monkeypatch):
    body = b'data: The\n\ndata:  battery\n\ndata:  regression.\n\n' + done_frame('') + b'\n\n'
    client, _ = make_client(monkeypatch, [body])
    result = await client.chat('hi')
    assert result.text == 'The battery regression.'
    assert result.error is None
    assert result.truncated is False
    assert result.ok is True


@pytest.mark.asyncio
async def test_done_text_is_authoritative_over_the_deltas(monkeypatch):
    """The deltas can be a partial or re-written draft; `done:` is the answer."""
    body = b'data: partial dr\n\ndata: aft\n\n' + done_frame('The final, corrected answer.') + b'\n\n'
    client, _ = make_client(monkeypatch, [body])
    result = await client.chat('hi')
    assert result.text == 'The final, corrected answer.'
    assert 'partial' not in result.text


@pytest.mark.asyncio
async def test_empty_done_text_falls_back_to_the_deltas(monkeypatch):
    body = b'data: from the deltas\n\n' + done_frame('') + b'\n\n'
    client, _ = make_client(monkeypatch, [body])
    assert (await client.chat('hi')).text == 'from the deltas'


@pytest.mark.asyncio
async def test_chat_collects_thinking_lines_separately_from_the_answer(monkeypatch):
    body = b'think: Searching memories\n\nthink: Reading conversations\n\ndata: Done.\n\n' + done_frame('Done.') + b'\n\n'
    client, _ = make_client(monkeypatch, [body])
    result = await client.chat('hi')
    assert result.thinking == ['Searching memories', 'Reading conversations']
    assert result.text == 'Done.'


@pytest.mark.asyncio
async def test_chat_strips_surrounding_whitespace_from_the_answer(monkeypatch):
    body = b'data: \n\ndata:   All clear.  \n\n'
    client, _ = make_client(monkeypatch, [body])
    assert (await client.chat('hi')).text == 'All clear.'


@pytest.mark.asyncio
async def test_chat_stops_consuming_after_the_terminal_frame(monkeypatch):
    body = done_frame('final') + b'\n\ndata: this must never be read\n\n'
    client, _ = make_client(monkeypatch, [body])
    result = await client.chat('hi')
    assert result.text == 'final'
    assert 'never' not in result.text


@pytest.mark.asyncio
async def test_error_frame_populates_error_and_is_terminal(monkeypatch):
    body = b'data: partial\n\nerror: quota exhausted\n\ndata: after the error\n\n'
    client, _ = make_client(monkeypatch, [body])
    result = await client.chat('hi')
    assert result.error == 'quota exhausted'
    assert result.truncated is False, 'an error frame is a terminal frame'
    assert result.ok is False
    assert 'after the error' not in result.text


@pytest.mark.asyncio
async def test_a_402_quota_frame_surfaces_as_an_error(monkeypatch):
    client, _ = make_client(monkeypatch, [b'error:402:Out of credits\n\n'])
    result = await client.chat('hi')
    assert result.error == 'Out of credits'


@pytest.mark.asyncio
async def test_a_stream_that_ends_without_a_terminal_frame_is_truncated(monkeypatch):
    """The agent's 150s cap sits behind a 120s request timeout, so a slow answer
    dies as a bare 504 mid-stream. That is a real outcome, not an impossibility.
    """
    client, _ = make_client(monkeypatch, [b'data: The battery reg\n\n'])
    result = await client.chat('hi')
    assert result.text == 'The battery reg'
    assert result.truncated is True
    assert result.error is None
    assert result.ok is True, 'a partial answer is still an answer'


@pytest.mark.asyncio
async def test_an_entirely_empty_stream_is_truncated_and_not_ok(monkeypatch):
    client, _ = make_client(monkeypatch, [])
    result = await client.chat('hi')
    assert result.text == ''
    assert result.truncated is True
    assert result.ok is False


@pytest.mark.asyncio
async def test_chat_reports_elapsed_time(monkeypatch):
    client, _ = make_client(monkeypatch, [done_frame('hi') + b'\n\n'])
    result = await client.chat('hi')
    assert 0 <= result.elapsed_s < 5


@pytest.mark.asyncio
async def test_http_error_becomes_a_chat_error_not_an_exception(monkeypatch):
    client, _ = make_client(monkeypatch, [b'nope'], status=503)
    result = await client.chat('hi')
    assert result.error and 'HTTP 503' in result.error
    assert result.ok is False


# --------------------------------------------------------------------------
# chat -- the deadline
# --------------------------------------------------------------------------


def make_stalling_client(monkeypatch, first: bytes, stall_seconds: float = 5.0):
    """A stream that emits `first`, then hangs -- Omi's slow-agent failure mode."""

    def handler(request):
        async def body():
            yield first
            await asyncio.sleep(stall_seconds)
            yield b'done: never arrives\n\n'

        return httpx.Response(200, content=body())

    install_mock_transport(monkeypatch, handler)
    return OmiClient(FakeAuth(), 'https://api.omi.me')


@pytest.mark.asyncio
async def test_deadline_returns_the_partial_answer_instead_of_hanging(monkeypatch):
    client = make_stalling_client(monkeypatch, b'data: The battery regression is\n\n')
    # The outer wait_for turns "it hangs" into a failure rather than a hung suite.
    result = await asyncio.wait_for(client.chat('hi', deadline_s=0.1), timeout=5)
    assert result.text == 'The battery regression is'
    assert result.truncated is True
    assert result.error is None
    assert result.elapsed_s < 2, 'the deadline must cut the stream, not wait it out'


@pytest.mark.asyncio
async def test_deadline_keeps_every_delta_received_before_it_fired(monkeypatch):
    client = make_stalling_client(monkeypatch, b'data: one\n\ndata:  two\n\ndata:  three\n\n')
    result = await asyncio.wait_for(client.chat('hi', deadline_s=0.1), timeout=5)
    assert result.text == 'one two three'
    assert result.truncated is True


@pytest.mark.asyncio
async def test_an_already_expired_deadline_returns_immediately(monkeypatch):
    client = make_stalling_client(monkeypatch, b'data: never read\n\n')
    result = await asyncio.wait_for(client.chat('hi', deadline_s=0), timeout=5)
    assert result.text == ''
    assert result.truncated is True


@pytest.mark.asyncio
async def test_no_deadline_waits_for_the_terminal_frame(monkeypatch):
    body = b'data: slow\n\n' + done_frame('slow but complete') + b'\n\n'
    client, _ = make_client(monkeypatch, [body])
    result = await asyncio.wait_for(client.chat('hi'), timeout=5)
    assert result.text == 'slow but complete'
    assert result.truncated is False


@pytest.mark.asyncio
async def test_a_generous_deadline_does_not_truncate_a_fast_answer(monkeypatch):
    client, _ = make_client(monkeypatch, [done_frame('quick') + b'\n\n'])
    result = await client.chat('hi', deadline_s=30)
    assert result.text == 'quick'
    assert result.truncated is False


@pytest.mark.asyncio
async def test_the_deadline_bounds_the_whole_turn_not_each_frame(monkeypatch):
    """Three 60ms gaps against a 100ms deadline: a per-frame timeout would let
    the turn run to 180ms+.
    """

    def handler(request):
        async def body():
            for i in range(6):
                yield f'data: {i}'.encode() + b'\n\n'
                await asyncio.sleep(0.06)

        return httpx.Response(200, content=body())

    install_mock_transport(monkeypatch, handler)
    client = OmiClient(FakeAuth(), 'https://api.omi.me')
    result = await asyncio.wait_for(client.chat('hi', deadline_s=0.1), timeout=5)
    assert result.truncated is True
    assert result.elapsed_s < 0.5
    assert len(result.text) < 6


# --------------------------------------------------------------------------
# JSON endpoints
# --------------------------------------------------------------------------


def make_json_client(monkeypatch, payload, status=200):
    def handler(request):
        return httpx.Response(status, json=payload)

    requests = install_mock_transport(monkeypatch, handler)
    return OmiClient(FakeAuth(), 'https://api.omi.me'), requests


@pytest.mark.asyncio
async def test_memories_are_sliced_client_side(monkeypatch):
    """`offset=0` makes the server ignore `limit` and return up to 5000 rows."""
    client, requests = make_json_client(monkeypatch, [{'id': str(i)} for i in range(500)])
    rows = await client.memories(limit=3)
    assert len(rows) == 3
    assert requests[0].url.params['offset'] == '0'
    assert requests[0].url.path == '/v3/memories'


@pytest.mark.asyncio
async def test_memories_tolerates_a_non_list_payload(monkeypatch):
    client, _ = make_json_client(monkeypatch, {'detail': 'nope'})
    assert await client.memories() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'payload,expected',
    [
        ([{'id': 'a'}], [{'id': 'a'}]),
        ({'action_items': [{'id': 'b'}]}, [{'id': 'b'}]),
        ({'items': [{'id': 'c'}]}, [{'id': 'c'}]),
        ({'nothing': 1}, []),
    ],
)
async def test_action_items_unwraps_either_envelope(monkeypatch, payload, expected):
    client, _ = make_json_client(monkeypatch, payload)
    assert await client.action_items() == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'payload,expected',
    [
        ([{'summary': 'a'}], [{'summary': 'a'}]),
        ({'daily_summaries': [{'summary': 'b'}]}, [{'summary': 'b'}]),
        ({'items': [{'summary': 'c'}]}, [{'summary': 'c'}]),
    ],
)
async def test_daily_summaries_unwraps_either_envelope(monkeypatch, payload, expected):
    client, _ = make_json_client(monkeypatch, payload)
    assert await client.daily_summaries() == expected


@pytest.mark.asyncio
async def test_get_messages_returns_the_newest_rows_last(monkeypatch):
    client, _ = make_json_client(monkeypatch, [{'id': str(i)} for i in range(10)])
    rows = await client.get_messages(limit=3)
    assert [r['id'] for r in rows] == ['7', '8', '9']


@pytest.mark.asyncio
async def test_json_endpoints_raise_on_http_errors(monkeypatch):
    client, _ = make_json_client(monkeypatch, {'detail': 'nope'}, status=401)
    with pytest.raises(httpx.HTTPStatusError):
        await client.memories()


@pytest.mark.asyncio
async def test_transcribe_pcm_sends_raw_octets_with_the_g2_audio_parameters(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={'transcript': 'what is on my plate'})

    requests = install_mock_transport(monkeypatch, handler)
    client = OmiClient(FakeAuth(), 'https://api.omi.me')
    pcm = b'\x01\x02' * 100
    assert await client.transcribe_pcm(pcm) == 'what is on my plate'

    request = requests[0]
    assert request.headers['content-type'] == 'application/octet-stream'
    assert request.content == pcm
    # The G2 mic is PCM16 LE mono at 16 kHz -- nothing is resampled.
    assert request.url.params['encoding'] == 'linear16'
    assert request.url.params['sample_rate'] == '16000'
    assert request.url.params['channels'] == '1'


@pytest.mark.asyncio
async def test_transcribe_pcm_raises_a_readable_error_on_failure(monkeypatch):
    def handler(request):
        return httpx.Response(413, text='payload too large')

    install_mock_transport(monkeypatch, handler)
    client = OmiClient(FakeAuth(), 'https://api.omi.me')
    with pytest.raises(RuntimeError, match='413'):
        await client.transcribe_pcm(b'\x00' * 10)


@pytest.mark.asyncio
async def test_auth_failures_propagate_out_of_the_stream(monkeypatch):
    """No token means no request: the caller must see the auth error, not an
    empty answer that looks like Omi had nothing to say.
    """
    boom = RuntimeError('no signed-in session')
    client, requests = make_client(monkeypatch, [done_frame('hi')], auth=FakeAuth(fail=boom))
    with pytest.raises(RuntimeError, match='no signed-in session'):
        await collect(client.chat_stream('hi'))
    assert requests == []
