"""The cheap per-moment call, the Jev boundary question, and live moment detection."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from config import episodes as config
from utils.episodes import incremental, live
from utils.episodes import service  # noqa: F401 -- warms live's deferred import outside the timed call
from utils.episodes.live import MomentTracker

NOW = datetime(2026, 10, 20, 17, 0, tzinfo=timezone.utc)


def test_render_moment_joins_voices_and_bounds_long_text():
    rendered = incremental.render_moment(
        [
            {'text': 'hello there', 'is_user': True},
            {'text': 'still me', 'is_user': True},
            {'text': 'hi', 'speaker_id': 2},
            {'text': 'named', 'person_name': 'Minh', 'person_id': 'minh'},
            {'text': '   '},
        ]
    )
    assert rendered.text == 'You: hello there still me\nUnknown speaker: hi\nMinh: named'
    assert rendered.words == 6
    long = incremental.render_moment([{'text': 'word ' * 4000, 'is_user': True}])
    assert len(long.text) <= config.MOMENT_TEXT_MAX_CHARS and '[…]' in long.text


def test_prompt_keeps_the_fixed_prefix_first_and_volatile_parts_last():
    first = incremental.build_messages('{"topic":"A"}', 'Owner: x', now=NOW, tz_name='America/Los_Angeles')
    second = incremental.build_messages('{"topic":"B"}', 'Owner: y', now=NOW, tz_name='Not/AZone')
    assert first[0] == second[0] == ('system', incremental.PROMPT_PREFIX)
    body = first[1][1]
    assert body.index('Local time now: 2026-10-20 10:00') < body.index('{"topic":"A"}') < body.index('Owner: x')
    assert '(UTC)' in second[1][1]


def test_run_incremental_update_reports_tokens_and_parses():
    seen = []

    def invoke(uid, messages):
        seen.append((uid, messages))
        return SimpleNamespace(
            content=[{'text': '{"title": "Lunch", "bullets": ["A"], "items": [{"text": "Book table"}]}'}],
            usage_metadata={'input_tokens': 321, 'output_tokens': 45},
        )

    result = incremental.run_incremental_update(
        'uid', '{}', 'Owner: book a table', known_item_ids=[], now=NOW, tz_name='UTC', invoke=invoke
    )
    assert result.update.title == 'Lunch' and result.update.new_items[0]['text'] == 'Book table'
    assert (result.input_tokens, result.output_tokens) == (321, 45)
    assert seen[0][0] == 'uid'


@pytest.mark.parametrize(
    'invoke,outcome',
    [
        (lambda uid, messages: (_ for _ in ()).throw(TimeoutError('slow')), 'llm_error'),
        (lambda uid, messages: SimpleNamespace(content='I cannot help', usage_metadata=None), 'parse_error'),
    ],
)
def test_run_incremental_update_failures_are_typed(invoke, outcome):
    with pytest.raises(incremental.ModelCallFailed) as raised:
        incremental.run_incremental_update('uid', '{}', 'x', known_item_ids=[], now=NOW, tz_name='UTC', invoke=invoke)
    assert raised.value.outcome == outcome


def test_ask_same_occasion_uses_the_episode_lane_and_fails_open():
    calls = []

    def ask(state, questions, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(noul=lambda name: 0.7)

    assert incremental.ask_same_occasion('state', ask=ask) == 0.7
    assert calls[0]['lane'] == config.JEV_LANE and calls[0]['max_attempts'] == 1
    assert incremental.ask_same_occasion('state', ask=lambda *a, **k: None) is None
    assert incremental.ask_same_occasion('state', ask=lambda *a, **k: SimpleNamespace(noul=lambda n: 3.0)) is None

    def broken(*args, **kwargs):
        raise RuntimeError('boom')

    assert incremental.ask_same_occasion('state', ask=broken) is None


def test_boundary_state_is_compact_and_names_the_signals():
    state = incremental.boundary_state(
        {'title': 'Lunch', 'bullets': [str(i) for i in range(9)], 'people': ['Huong']},
        'Owner: new topic ' * 400,
        gap_seconds=600,
        source_changed=True,
        episode_source='omi',
        moment_source='phone',
        speakers_changed=True,
    )
    assert '"minutes_since_last_speech": 10.0' in state and '"device_changed": true' in state
    assert '"episode_bullets": ["4", "5", "6", "7", "8"]' in state
    assert len(state) < 3_200


def _segs(words, *, text='word'):
    return [{'text': ' '.join([text] * words)}]


def test_tracker_flushes_on_pause_rollover_and_conversation_change():
    tracker = MomentTracker()
    assert tracker.observe('u', _segs(30), 'c1', 'omi', now=1000) == []
    # A short gap keeps accumulating.
    assert tracker.observe('u', _segs(5), 'c1', 'omi', now=1010) == []
    paused = tracker.observe('u', _segs(5), 'c1', 'omi', now=1010 + config.MOMENT_PAUSE_SECONDS)
    assert [m.trigger for m in paused] == ['pause'] and len(paused[0].segments) == 2
    # The new batch starts the next moment.
    moved = tracker.observe('u', _segs(5), 'c2', 'omi', now=1100)
    assert [(m.trigger, m.conversation_id) for m in moved] == [('rollover', 'c1')]
    big = tracker.observe('u', _segs(config.MOMENT_MAX_WORDS), 'c2', 'omi', now=1110)
    assert [m.trigger for m in big] == ['rollover'] and big[0].conversation_id == 'c2'
    assert tracker.observe('u', [], None, 'omi', now=1120) == []


def test_tracker_does_not_spend_a_call_on_a_short_or_too_soon_moment():
    tracker = MomentTracker()
    tracker.observe('u', _segs(3), 'c1', 'omi', now=0)
    # Paused, but under the minimum words: still accumulating.
    assert tracker.observe('u', _segs(3), 'c1', 'omi', now=100) == []
    tracker.observe('u', _segs(30), 'c1', 'omi', now=110)
    first = tracker.observe('u', _segs(30), 'c1', 'omi', now=200)
    assert len(first) == 1
    # Paused again within the minimum interval since the last flush: keep accumulating.
    assert tracker.observe('u', _segs(30), 'c1', 'omi', now=200 + config.MOMENT_PAUSE_SECONDS) == []


def test_tracker_evicts_stale_buffers():
    tracker = MomentTracker()
    tracker.observe('u', _segs(30), 'c1', 'omi', now=0)
    tracker.observe('v', _segs(1), 'c9', 'omi', now=live.BUFFER_TTL_SECONDS + 10)
    assert 'u' not in tracker._buffers


def test_on_realtime_segments_schedules_a_background_update(monkeypatch):
    scheduled = []
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)
    tracker = MomentTracker()
    monkeypatch.setattr(live, 'tracker', tracker)
    live.sessions.clear()

    def fake_start(coro, *, name):
        scheduled.append(name)
        coro.close()

    monkeypatch.setattr(live.executors, 'start_background_task', fake_start)
    tracker.observe('u', _segs(30), 'c1', 'omi', now=0)
    monkeypatch.setattr(live.time, 'time', lambda: 1000.0)
    monkeypatch.setattr(live.time, 'monotonic', lambda: 1000.0)
    asyncio.run(live.on_realtime_segments('u', _segs(3), 'c2', 'omi'))
    # The new conversation attaches at its first words; the old one's moment ends.
    assert scheduled == ['episode_attach', 'episode_moment']
    asyncio.run(live.on_realtime_segments('u', _segs(3), 'c2', 'omi'))
    # Activity is independent of the word budget, coalesced to one write a minute.
    assert scheduled == ['episode_attach', 'episode_moment']
    monkeypatch.setattr(live.time, 'monotonic', lambda: 1060.0)
    asyncio.run(live.on_realtime_segments('u', _segs(3), 'c2', 'omi'))
    assert scheduled == ['episode_attach', 'episode_moment', 'episode_attach']
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    asyncio.run(live.on_realtime_segments('u', _segs(3), 'c3', 'omi'))
    assert scheduled == ['episode_attach', 'episode_moment', 'episode_attach']


def test_the_first_moment_comes_early_then_the_interval_holds():
    tracker = MomentTracker()
    ended = []
    for wall in range(0, 40, 10):
        ended += tracker.observe('u', _segs(20), 'c1', 'omi', now=wall)
    assert [m.trigger for m in ended] == ['interval']
    assert ended[0].segments and (ended[0].ended_at - ended[0].started_at).total_seconds() >= 30
    # After that first flush the ordinary interval applies.
    assert tracker.observe('u', _segs(80), 'c1', 'omi', now=60) == []


def test_steady_talk_ends_a_moment_on_the_interval():
    tracker = MomentTracker()
    tracker._buffers['u'] = live._Buffer('c1', 'omi', 0.0, 0.0, last_flush_wall=-1.0)
    wall = 0
    ended = []
    # Twelve words every ten seconds: never a 45 s pause, 600 words only after eight minutes.
    while wall <= config.MOMENT_MAX_SECONDS + 10:
        ended += tracker.observe('u', _segs(12), 'c1', 'omi', now=wall)
        wall += 10
    assert [m.trigger for m in ended] == ['interval']
    assert (ended[0].ended_at - ended[0].started_at).total_seconds() >= config.MOMENT_MAX_SECONDS


def test_session_end_flushes_the_buffer(monkeypatch):
    tracker = MomentTracker()
    tracker.observe('u', _segs(30), 'c1', 'omi', now=0)
    # Another session's conversation (a parallel capture on this pod) keeps its buffer.
    assert tracker.flush('u', 'c-other') is None
    moment = tracker.flush('u', 'c1')
    assert moment.trigger == 'session_end' and moment.conversation_id == 'c1'
    assert tracker.flush('u', 'c1') is None and tracker.flush('u', None) is None

    scheduled = []
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.setattr(live, 'tracker', tracker)
    monkeypatch.setattr(
        live.executors, 'start_background_task', lambda coro, *, name: scheduled.append(name) or coro.close()
    )
    tracker.observe('u', _segs(30), 'c1', 'omi', now=0)
    asyncio.run(live.on_session_end('u', 'c1'))
    asyncio.run(live.on_session_end('u', 'c1'))
    assert scheduled == ['episode_moment']


def test_alternating_devices_attach_each_conversation_once():
    counter = live._SessionCounter()
    seen = [counter.first_moment('u', cid) for cid in ['phone', 'omi', 'phone', 'omi', 'phone']]
    assert seen == [True, True, False, False, False]
