from __future__ import annotations

from dataclasses import replace

import json
import os

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from llm_gateway.gateway.accounting import CacheStatus, PricedUsage, ProviderResponseMetadata, ProviderUsage
from routers import desktop_realtime
from utils.llm.realtime_usage import (
    DEFAULT_REALTIME_MODELS,
    GEMINI_LIVE_PROVIDER,
    OPENAI_REALTIME_PROVIDER,
    REALTIME_COST_BASIS,
    RealtimeRelayObserver,
    RealtimeTurnUsage,
    _MAX_PARSED_FRAME_BYTES,
    client_reported_cost_usd,
    client_reported_turn,
    price_realtime_turn,
    realtime_rates_for,
    realtime_turn_cost_micro_usd,
    realtime_turn_cost_usd,
    realtime_turn_metadata,
)

_UNSET = object()

# Shared priced-turn mix: 100 text (40 cached), 200 audio (50 cached), 30 image,
# 20 out text, 100 out audio, 10 reasoning (billed as text output).
_PRICED_COUNTS = dict(
    input_text_tokens=100,
    input_audio_tokens=200,
    input_image_tokens=30,
    cached_text_tokens=40,
    cached_audio_tokens=50,
    cached_image_tokens=0,
    output_text_tokens=20,
    output_audio_tokens=100,
    reasoning_tokens=10,
    usage_reported=True,
    modality_split_reported=True,
    cached_split_reported=True,
)
# gpt-realtime-2: 60*4e6 + 40*4e5 + 150*32e6 + 50*4e5 + 30*5e6 + (20+10)*24e6 + 100*64e6
_OPENAI_PRICED_NUMERATOR = (
    60 * 4_000_000
    + 40 * 400_000
    + 150 * 32_000_000
    + 50 * 400_000
    + 30 * 5_000_000
    + (20 + 10) * 24_000_000
    + 100 * 64_000_000
)
# gemini-3.1-flash-live-preview (cached rate == full): 0.75/3/1 / 4.5/12
_GEMINI_31_PRICED_NUMERATOR = (
    60 * 750_000
    + 40 * 750_000
    + 150 * 3_000_000
    + 50 * 3_000_000
    + 30 * 1_000_000
    + (20 + 10) * 4_500_000
    + 100 * 12_000_000
)
# gemini-2.5-flash-native-audio-preview-12-2025: 0.5/3/3 / 2/12
_GEMINI_25_PRICED_NUMERATOR = (
    60 * 500_000
    + 40 * 500_000
    + 150 * 3_000_000
    + 50 * 3_000_000
    + 30 * 3_000_000
    + (20 + 10) * 2_000_000
    + 100 * 12_000_000
)


def _micro(numerator: int) -> int:
    return (numerator + 500_000) // 1_000_000


def _frame(payload: dict, *, as_bytes: bool = False) -> str | bytes:
    raw = json.dumps(payload)
    return raw.encode('utf-8') if as_bytes else raw


def _bytes_frame(payload: dict) -> bytes:
    return json.dumps(payload).encode('utf-8')


def _only(turns: tuple[RealtimeTurnUsage, ...]) -> RealtimeTurnUsage:
    assert len(turns) == 1
    return turns[0]


def _openai_done(
    *,
    response_id: str | None = 'resp_abc',
    usage: object = _UNSET,
    status: object = _UNSET,
    extra_response: dict | None = None,
) -> dict:
    response: dict = {}
    if response_id is not None:
        response['id'] = response_id
    if usage is not _UNSET:
        response['usage'] = usage
    if status is not _UNSET:
        response['status'] = status
    if extra_response:
        response.update(extra_response)
    return {'type': 'response.done', 'response': response}


def _openai_created(*, response_id: str | None = 'resp_abc') -> dict:
    response: dict = {}
    if response_id is not None:
        response['id'] = response_id
    return {'type': 'response.created', 'response': response}


def _openai_full_usage() -> dict:
    return {
        'input_token_details': {
            'text_tokens': 80,
            'audio_tokens': 40,
            'image_tokens': 10,
            'cached_tokens': 999,
            'cached_tokens_details': {'text_tokens': 30, 'audio_tokens': 12, 'image_tokens': 4},
        },
        'output_token_details': {'text_tokens': 5, 'audio_tokens': 7},
    }


def _gemini_usage(
    *,
    prompt_details: list | None = None,
    response_details: list | None = None,
    cache_tokens_details: list | None = None,
    prompt_token_count: int | None = None,
    candidates_token_count: int | None = None,
    response_token_count: int | None = None,
    cached_content_token_count: int | None = None,
    thoughts_token_count: int | None = None,
    tool_use_prompt_token_count: int | None = None,
) -> dict:
    usage: dict = {}
    if prompt_details is not None:
        usage['promptTokensDetails'] = prompt_details
    if response_details is not None:
        usage['responseTokensDetails'] = response_details
    if cache_tokens_details is not None:
        usage['cacheTokensDetails'] = cache_tokens_details
    if prompt_token_count is not None:
        usage['promptTokenCount'] = prompt_token_count
    if candidates_token_count is not None:
        usage['candidatesTokenCount'] = candidates_token_count
    if response_token_count is not None:
        usage['responseTokenCount'] = response_token_count
    if cached_content_token_count is not None:
        usage['cachedContentTokenCount'] = cached_content_token_count
    if thoughts_token_count is not None:
        usage['thoughtsTokenCount'] = thoughts_token_count
    if tool_use_prompt_token_count is not None:
        usage['toolUsePromptTokenCount'] = tool_use_prompt_token_count
    return usage


def _gemini_server(
    *,
    usage: dict | None = None,
    turn_complete: object = _UNSET,
    interrupted: object = _UNSET,
) -> dict:
    payload: dict = {}
    if usage is not None:
        payload['usageMetadata'] = usage
    server: dict = {}
    if turn_complete is not _UNSET:
        server['turnComplete'] = turn_complete
    if interrupted is not _UNSET:
        server['interrupted'] = interrupted
    if server:
        payload['serverContent'] = server
    return payload


def _gemini_model_turn_audio() -> bytes:
    return _bytes_frame(
        {
            'serverContent': {
                'modelTurn': {
                    'parts': [{'inlineData': {'mimeType': 'audio/pcm', 'data': 'AAAA'}}],
                }
            }
        }
    )


def _priced_turn(provider: str) -> RealtimeTurnUsage:
    return RealtimeTurnUsage(provider=provider, **_PRICED_COUNTS)


def _gemini_padded_turn_frame(padding: int) -> bytes:
    return (
        b'{"usageMetadata":{"promptTokenCount":11,"candidatesTokenCount":2},'
        b'"serverContent":{"turnComplete":true},"pad":"' + (b'A' * padding) + b'"}'
    )


def _complete_gemini(observer: RealtimeRelayObserver, payload: dict) -> RealtimeTurnUsage:
    """Drive a Gemini turnComplete frame and release the held row via flush."""
    assert observer.observe_upstream_frame(_bytes_frame(payload)) == ()
    return _only(observer.flush())


# -- OpenAI --------------------------------------------------------------------


@pytest.mark.parametrize('as_bytes', [False, True], ids=['str', 'bytes'])
def test_openai_response_done_with_cached_tokens_details_is_priceable_and_records_id(as_bytes: bool) -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    turn = _only(observer.observe_upstream_frame(_frame(_openai_done(usage=_openai_full_usage()), as_bytes=as_bytes)))

    assert replace(turn, ordinal=0) == RealtimeTurnUsage(
        provider=OPENAI_REALTIME_PROVIDER,
        input_text_tokens=80,
        input_audio_tokens=40,
        input_image_tokens=10,
        cached_text_tokens=30,
        cached_audio_tokens=12,
        cached_image_tokens=4,
        output_text_tokens=5,
        output_audio_tokens=7,
        usage_reported=True,
        modality_split_reported=True,
        cached_split_reported=True,
        provider_response_id='resp_abc',
    )
    assert turn.priceable is True
    assert observer.turns == 1


def test_openai_two_response_done_frames_are_separate_turns_not_summed() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    first = _only(
        observer.observe_upstream_frame(
            _frame(
                _openai_done(
                    response_id='resp_1',
                    usage={
                        'input_token_details': {'text_tokens': 10, 'audio_tokens': 0, 'image_tokens': 0},
                        'output_token_details': {'text_tokens': 4, 'audio_tokens': 0},
                    },
                )
            )
        )
    )
    second = _only(
        observer.observe_upstream_frame(
            _frame(
                _openai_done(
                    response_id='resp_2',
                    usage={
                        'input_token_details': {'text_tokens': 20, 'audio_tokens': 0, 'image_tokens': 0},
                        'output_token_details': {'text_tokens': 6, 'audio_tokens': 0},
                    },
                )
            )
        )
    )

    assert observer.turns == 2
    assert first.provider_response_id == 'resp_1'
    assert second.provider_response_id == 'resp_2'
    assert first.input_text_tokens == 10
    assert second.input_text_tokens == 20


def test_openai_two_input_modalities_without_cached_tokens_details_are_unpriced() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    turn = _only(
        observer.observe_upstream_frame(
            _frame(
                _openai_done(
                    usage={
                        'input_token_details': {
                            'text_tokens': 100,
                            'audio_tokens': 200,
                            'cached_tokens': 150,
                        },
                        'output_token_details': {'text_tokens': 1, 'audio_tokens': 0},
                    }
                )
            )
        )
    )

    assert turn.cached_text_tokens == 100
    assert turn.cached_audio_tokens == 50
    assert turn.modality_split_reported is True
    assert turn.cached_split_reported is False
    assert turn.priceable is False
    assert price_realtime_turn(turn, 'gpt-realtime-2') is None


def test_openai_single_input_modality_without_cached_tokens_details_is_priced() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    turn = _only(
        observer.observe_upstream_frame(
            _frame(
                _openai_done(
                    usage={
                        'input_token_details': {
                            'text_tokens': 100,
                            'audio_tokens': 0,
                            'cached_tokens': 40,
                        },
                        'output_token_details': {'text_tokens': 1, 'audio_tokens': 0},
                    }
                )
            )
        )
    )

    assert turn.cached_text_tokens == 40
    assert turn.cached_audio_tokens == 0
    assert turn.cached_split_reported is True
    assert turn.priceable is True
    priced = price_realtime_turn(turn, 'gpt-realtime-2')
    assert priced is not None
    assert priced.micro_usd == _micro(60 * 4_000_000 + 40 * 400_000 + 1 * 24_000_000)


def test_openai_response_done_without_token_details_carries_aggregates_but_is_unpriced() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    turn = _only(observer.observe_upstream_frame(_frame(_openai_done(usage={'input_tokens': 40, 'output_tokens': 15}))))

    assert replace(turn, ordinal=0) == RealtimeTurnUsage(
        provider=OPENAI_REALTIME_PROVIDER,
        input_text_tokens=40,
        output_text_tokens=15,
        usage_reported=True,
        modality_split_reported=False,
        cached_split_reported=True,
        provider_response_id='resp_abc',
    )
    assert turn.priceable is False
    assert price_realtime_turn(turn, 'gpt-realtime-2') is None


def test_openai_empty_token_details_with_aggregates_are_unpriced() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    turn = _only(
        observer.observe_upstream_frame(
            _frame(
                _openai_done(
                    usage={
                        'input_tokens': 40,
                        'output_tokens': 15,
                        'input_token_details': {},
                        'output_token_details': {},
                    }
                )
            )
        )
    )

    assert turn.input_text_tokens == 40
    assert turn.output_text_tokens == 15
    assert turn.modality_split_reported is False
    assert turn.priceable is False


def test_openai_reasoning_tokens_are_carried_and_priced_at_text_output_rate() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    turn = _only(
        observer.observe_upstream_frame(
            _frame(
                _openai_done(
                    usage={
                        'input_token_details': {'text_tokens': 0, 'audio_tokens': 0},
                        'output_token_details': {'text_tokens': 20, 'audio_tokens': 0, 'reasoning_tokens': 10},
                    }
                )
            )
        )
    )
    rates = realtime_rates_for(OPENAI_REALTIME_PROVIDER, 'gpt-realtime-2')
    assert rates is not None
    text_only = RealtimeTurnUsage(
        provider=OPENAI_REALTIME_PROVIDER,
        output_text_tokens=30,
        usage_reported=True,
        modality_split_reported=True,
        cached_split_reported=True,
    )

    assert turn.reasoning_tokens == 10
    assert turn.output_text_tokens == 20
    assert turn.priceable is True
    assert realtime_turn_cost_micro_usd(turn, rates) == realtime_turn_cost_micro_usd(text_only, rates)
    assert realtime_turn_cost_micro_usd(turn, rates) == _micro(30 * 24_000_000)


def test_openai_response_done_without_usage_reports_unreported_zero_tokens() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    turn = _only(observer.observe_upstream_frame(_frame(_openai_done())))

    assert replace(turn, ordinal=0) == RealtimeTurnUsage(
        provider=OPENAI_REALTIME_PROVIDER,
        usage_reported=False,
        provider_response_id='resp_abc',
    )
    assert observer.turns == 1
    assert turn.has_tokens is False
    assert turn.priceable is False


@pytest.mark.parametrize(
    'status, extra_response, outcome, error_class',
    [
        (None, None, 'success', 'none'),
        ('completed', None, 'success', 'none'),
        ('cancelled', None, 'cancelled', 'client_cancelled'),
        ('cancelled', {'status_details': {'reason': 'turn_detected'}}, 'cancelled', 'interrupted'),
        ('incomplete', None, 'error', 'incomplete'),
        ('failed', None, 'error', 'provider_error'),
    ],
    ids=['none', 'completed', 'cancelled', 'cancelled_turn_detected', 'incomplete', 'failed'],
)
def test_openai_response_done_maps_status_to_outcome(
    status: str | None, extra_response: dict | None, outcome: str, error_class: str
) -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    turn = _only(observer.observe_upstream_frame(_frame(_openai_done(status=status, extra_response=extra_response))))

    assert turn.outcome == outcome
    assert turn.error_class == error_class


@pytest.mark.parametrize(
    'payload',
    [
        {'type': 'response.output_audio.delta', 'delta': 'AAAA'},
        {'type': 'session.updated', 'session': {'voice': 'alloy'}},
        {'type': 'error', 'error': {'message': 'boom'}},
    ],
    ids=['output_audio_delta', 'session_updated', 'error'],
)
def test_openai_non_turn_frames_yield_empty_and_do_not_increment_turns(payload: dict) -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)

    assert observer.observe_upstream_frame(_frame(payload)) == ()
    assert observer.turns == 0


def test_openai_created_a_created_b_done_a_emits_only_a() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)

    assert observer.observe_upstream_frame(_frame(_openai_created(response_id='resp_a'))) == ()
    assert observer.observe_upstream_frame(_frame(_openai_created(response_id='resp_b'))) == ()
    done = _only(observer.observe_upstream_frame(_frame(_openai_done(response_id='resp_a'))))

    assert done.provider_response_id == 'resp_a'
    assert observer.turns == 1


def test_openai_flush_after_done_a_cancels_only_still_open_b() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    observer.observe_upstream_frame(_frame(_openai_created(response_id='resp_a')))
    observer.observe_upstream_frame(_frame(_openai_created(response_id='resp_b')))
    observer.observe_upstream_frame(_frame(_openai_done(response_id='resp_a')))
    cancelled = _only(observer.flush())

    assert replace(cancelled, ordinal=0) == RealtimeTurnUsage(
        provider=OPENAI_REALTIME_PROVIDER,
        outcome='cancelled',
        error_class='client_disconnected',
        provider_response_id='resp_b',
    )
    assert observer.turns == 2


def test_openai_created_without_id_then_flush_emits_one_anonymous_cancelled_row() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)

    assert observer.observe_upstream_frame(_frame(_openai_created(response_id=None))) == ()
    cancelled = _only(observer.flush())

    assert cancelled.outcome == 'cancelled'
    assert cancelled.error_class == 'client_disconnected'
    assert cancelled.provider_response_id is None  # tracking keys never reach the ledger
    assert observer.turns == 1


def test_openai_response_done_clears_its_id_so_flush_is_empty() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    observer.observe_upstream_frame(_frame(_openai_created(response_id='resp_live')))
    done = _only(observer.observe_upstream_frame(_frame(_openai_done(response_id='resp_live'))))

    assert done.provider_response_id == 'resp_live'
    assert observer.flush() == ()
    assert observer.turns == 1


def test_openai_flush_with_nothing_in_flight_returns_empty() -> None:
    assert RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER).flush() == ()


# -- Gemini --------------------------------------------------------------------


def test_gemini_two_turn_cumulative_sequence_holds_until_next_activity_or_flush() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)

    assert (
        observer.observe_upstream_frame(
            _bytes_frame(
                _gemini_server(
                    usage=_gemini_usage(prompt_token_count=100, candidates_token_count=20),
                    turn_complete=True,
                )
            )
        )
        == ()
    )
    first = _only(observer.observe_upstream_frame(_gemini_model_turn_audio()))
    assert (first.input_text_tokens, first.output_text_tokens) == (100, 20)
    assert first.outcome == 'success'
    assert (
        observer.observe_upstream_frame(
            _bytes_frame(
                _gemini_server(
                    usage=_gemini_usage(prompt_token_count=260, candidates_token_count=50),
                    turn_complete=True,
                )
            )
        )
        == ()
    )
    second = _only(observer.flush())

    assert (second.input_text_tokens, second.output_text_tokens) == (160, 30)
    assert second.outcome == 'success'
    assert observer.turns == 2


def test_gemini_trailing_usage_after_turn_complete_folds_into_held_row() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)

    assert observer.observe_upstream_frame(_bytes_frame(_gemini_server(turn_complete=True))) == ()
    assert (
        observer.observe_upstream_frame(
            _bytes_frame(_gemini_server(usage=_gemini_usage(prompt_token_count=100, candidates_token_count=20)))
        )
        == ()
    )
    held = _only(observer.flush())

    assert (held.input_text_tokens, held.output_text_tokens) == (100, 20)
    assert held.outcome == 'success'
    assert held.usage_reported is True
    assert observer.turns == 1


def test_gemini_usage_decrease_is_taken_as_absolute_reset() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    observer.observe_upstream_frame(
        _bytes_frame(
            _gemini_server(
                usage=_gemini_usage(prompt_token_count=260, candidates_token_count=50),
                turn_complete=True,
            )
        )
    )
    first = _only(
        observer.observe_upstream_frame(
            _bytes_frame(
                _gemini_server(
                    usage=_gemini_usage(prompt_token_count=40, candidates_token_count=8),
                    turn_complete=True,
                )
            )
        )
    )
    second = _only(observer.flush())

    assert (first.input_text_tokens, first.output_text_tokens) == (260, 50)
    assert (second.input_text_tokens, second.output_text_tokens) == (40, 8)


def test_gemini_modality_and_cache_tokens_details_are_honoured() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(
        observer,
        _gemini_server(
            usage=_gemini_usage(
                prompt_token_count=9999,
                candidates_token_count=9999,
                cached_content_token_count=9999,
                prompt_details=[
                    {'modality': 'TEXT', 'tokenCount': 10},
                    {'modality': 'AUDIO', 'tokenCount': 20},
                    {'modality': 'IMAGE', 'tokenCount': 5},
                ],
                cache_tokens_details=[
                    {'modality': 'TEXT', 'tokenCount': 4},
                    {'modality': 'AUDIO', 'tokenCount': 6},
                    {'modality': 'IMAGE', 'tokenCount': 2},
                ],
                response_details=[
                    {'modality': 'TEXT', 'tokenCount': 7},
                    {'modality': 'AUDIO', 'tokenCount': 11},
                    {'modality': 'IMAGE', 'tokenCount': 2},
                ],
            ),
            turn_complete=True,
        ),
    )

    assert replace(turn, ordinal=0) == RealtimeTurnUsage(
        provider=GEMINI_LIVE_PROVIDER,
        input_text_tokens=10,
        input_audio_tokens=20,
        input_image_tokens=5,
        cached_text_tokens=4,
        cached_audio_tokens=6,
        cached_image_tokens=2,
        output_text_tokens=9,
        output_audio_tokens=11,
        usage_reported=True,
        modality_split_reported=True,
        cached_split_reported=True,
    )
    assert turn.priceable is True


def test_gemini_cached_content_token_count_two_input_modalities_is_unpriceable() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(
        observer,
        _gemini_server(
            usage=_gemini_usage(
                prompt_details=[
                    {'modality': 'TEXT', 'tokenCount': 100},
                    {'modality': 'AUDIO', 'tokenCount': 200},
                ],
                cached_content_token_count=150,
                response_details=[{'modality': 'TEXT', 'tokenCount': 1}],
            ),
            turn_complete=True,
        ),
    )

    assert turn.cached_text_tokens == 100
    assert turn.cached_audio_tokens == 50
    assert turn.modality_split_reported is True
    assert turn.cached_split_reported is False
    assert turn.priceable is False
    assert price_realtime_turn(turn, 'gemini-3.1-flash-live-preview') is None


def test_gemini_cached_content_token_count_single_input_modality_is_priceable() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(
        observer,
        _gemini_server(
            usage=_gemini_usage(
                prompt_details=[{'modality': 'TEXT', 'tokenCount': 100}],
                cached_content_token_count=40,
                response_details=[{'modality': 'TEXT', 'tokenCount': 1}],
            ),
            turn_complete=True,
        ),
    )

    assert turn.cached_text_tokens == 40
    assert turn.cached_split_reported is True
    assert turn.priceable is True
    assert price_realtime_turn(turn, 'gemini-3.1-flash-live-preview') is not None


def test_gemini_prompt_and_candidates_count_fallbacks_mark_modality_split_unreported() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(
        observer,
        _gemini_server(
            usage=_gemini_usage(prompt_token_count=100, candidates_token_count=40),
            turn_complete=True,
        ),
    )

    assert replace(turn, ordinal=0) == RealtimeTurnUsage(
        provider=GEMINI_LIVE_PROVIDER,
        input_text_tokens=100,
        output_text_tokens=40,
        usage_reported=True,
        modality_split_reported=False,
        cached_split_reported=True,
    )
    assert turn.priceable is False


def test_gemini_response_token_count_fallback_marks_modality_split_unreported() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(
        observer,
        _gemini_server(
            usage=_gemini_usage(prompt_token_count=80, response_token_count=33),
            turn_complete=True,
        ),
    )

    assert turn.input_text_tokens == 80
    assert turn.output_text_tokens == 33
    assert turn.modality_split_reported is False
    assert turn.priceable is False


def test_gemini_video_modality_counts_as_image_input() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(
        observer,
        _gemini_server(
            usage=_gemini_usage(prompt_details=[{'modality': 'VIDEO', 'tokenCount': 15}]),
            turn_complete=True,
        ),
    )

    assert turn.input_image_tokens == 15
    assert turn.input_text_tokens == 0
    assert turn.input_audio_tokens == 0


def test_gemini_empty_details_with_aggregate_tokens_are_unpriced() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(
        observer,
        _gemini_server(
            usage=_gemini_usage(
                prompt_details=[],
                response_details=[],
                prompt_token_count=100,
                candidates_token_count=40,
            ),
            turn_complete=True,
        ),
    )

    assert turn.input_text_tokens == 100
    assert turn.output_text_tokens == 40
    assert turn.modality_split_reported is False
    assert turn.priceable is False


def test_gemini_unknown_positive_modality_is_unpriced() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(
        observer,
        _gemini_server(
            usage=_gemini_usage(
                prompt_details=[{'modality': 'UNKNOWN', 'tokenCount': 100}],
                response_details=[{'modality': 'TEXT', 'tokenCount': 40}],
            ),
            turn_complete=True,
        ),
    )

    assert turn.input_text_tokens == 0
    assert turn.input_audio_tokens == 0
    assert turn.input_image_tokens == 0
    assert turn.modality_split_reported is False
    assert turn.priceable is False


def test_gemini_thoughts_and_tool_use_are_carried_and_tool_use_makes_turn_unpriceable() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(
        observer,
        _gemini_server(
            usage=_gemini_usage(
                prompt_details=[{'modality': 'TEXT', 'tokenCount': 10}],
                response_details=[{'modality': 'TEXT', 'tokenCount': 4}],
                thoughts_token_count=8,
                tool_use_prompt_token_count=3,
            ),
            turn_complete=True,
        ),
    )

    assert turn.reasoning_tokens == 8
    assert turn.tool_use_prompt_tokens == 3
    assert turn.total_tokens == 10 + 4 + 8 + 3
    assert turn.modality_split_reported is True
    assert turn.cached_split_reported is True
    assert turn.priceable is False
    assert price_realtime_turn(turn, 'gemini-3.1-flash-live-preview') is None


def test_gemini_interrupted_then_turn_complete_holds_cancelled_interrupted_and_clears_flag() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    observer.observe_upstream_frame(
        _bytes_frame(_gemini_server(usage=_gemini_usage(prompt_token_count=50, candidates_token_count=3)))
    )
    assert observer.observe_upstream_frame(_bytes_frame(_gemini_server(interrupted=True))) == ()
    assert observer.observe_upstream_frame(_bytes_frame(_gemini_server(turn_complete=True))) == ()
    cancelled = _only(observer.observe_upstream_frame(_bytes_frame(_gemini_server(turn_complete=True))))
    nxt = _only(observer.flush())

    assert replace(cancelled, ordinal=0) == RealtimeTurnUsage(
        provider=GEMINI_LIVE_PROVIDER,
        outcome='cancelled',
        error_class='interrupted',
        input_text_tokens=50,
        output_text_tokens=3,
        usage_reported=True,
        modality_split_reported=False,
        cached_split_reported=True,
    )
    assert replace(nxt, ordinal=0) == RealtimeTurnUsage(
        provider=GEMINI_LIVE_PROVIDER,
        usage_reported=False,
        modality_split_reported=False,
        cached_split_reported=False,
    )
    assert nxt.outcome == 'success'
    assert observer.turns == 2


def test_gemini_interrupted_with_usage_then_disconnect_flushes_cancelled_interrupted() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    observer.observe_upstream_frame(
        _bytes_frame(_gemini_server(usage=_gemini_usage(prompt_token_count=50, candidates_token_count=3)))
    )
    observer.observe_upstream_frame(_bytes_frame(_gemini_server(interrupted=True)))
    turn = _only(observer.flush())

    assert turn.outcome == 'cancelled'
    assert turn.error_class == 'interrupted'
    assert turn.input_text_tokens == 50
    assert turn.output_text_tokens == 3
    assert turn.usage_reported is True


def test_gemini_malformed_model_turn_is_not_parsed_but_marks_in_flight() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    frame = b'{"serverContent": {"modelTurn": not-json'

    assert observer.observe_upstream_frame(frame) == ()
    turn = _only(observer.flush())

    assert turn.outcome == 'cancelled'
    assert turn.error_class == 'client_disconnected'
    assert turn.usage_reported is False


def test_gemini_turn_complete_without_usage_flushes_unreported_zero_tokens() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    turn = _complete_gemini(observer, _gemini_server(turn_complete=True))

    assert replace(turn, ordinal=0) == RealtimeTurnUsage(
        provider=GEMINI_LIVE_PROVIDER,
        usage_reported=False,
        modality_split_reported=False,
        cached_split_reported=False,
    )
    assert observer.turns == 1


def test_gemini_usage_only_before_complete_accumulates_into_pending_turn() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)

    assert (
        observer.observe_upstream_frame(
            _bytes_frame(_gemini_server(usage=_gemini_usage(prompt_token_count=100, candidates_token_count=20)))
        )
        == ()
    )
    assert observer.turns == 0
    assert observer.observe_upstream_frame(_bytes_frame(_gemini_server(turn_complete=True))) == ()
    turn = _only(observer.flush())

    assert replace(turn, ordinal=0) == RealtimeTurnUsage(
        provider=GEMINI_LIVE_PROVIDER,
        input_text_tokens=100,
        output_text_tokens=20,
        usage_reported=True,
        modality_split_reported=False,
        cached_split_reported=True,
    )


def test_gemini_flush_with_nothing_pending_returns_empty() -> None:
    assert RealtimeRelayObserver(GEMINI_LIVE_PROVIDER).flush() == ()


def test_gemini_frame_over_one_mib_with_turn_complete_and_usage_is_parsed() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    frame = _gemini_padded_turn_frame(1024 * 1024 + 1)
    assert len(frame) > 1024 * 1024
    assert len(frame) < _MAX_PARSED_FRAME_BYTES

    assert observer.observe_upstream_frame(frame) == ()
    turn = _only(observer.flush())

    assert replace(turn, ordinal=0) == RealtimeTurnUsage(
        provider=GEMINI_LIVE_PROVIDER,
        input_text_tokens=11,
        output_text_tokens=2,
        usage_reported=True,
        modality_split_reported=False,
        cached_split_reported=True,
    )


def test_gemini_frame_over_eight_mib_ceiling_is_ignored() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    frame = b'{"serverContent":{"turnComplete":true}}' + (b'A' * _MAX_PARSED_FRAME_BYTES)
    assert len(frame) > _MAX_PARSED_FRAME_BYTES

    assert observer.observe_upstream_frame(frame) == ()
    assert observer.flush() == ()
    assert observer.turns == 0


# -- Robustness ----------------------------------------------------------------


def test_malformed_json_with_marker_yields_empty() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)

    assert observer.observe_upstream_frame(b'{"serverContent": {"turnComplete": true,') == ()
    assert observer.turns == 0


@pytest.mark.parametrize(
    'literal',
    ['1e309', 'Infinity', '-7', 'true', '"12"'],
    ids=['overflow_float', 'infinity', 'negative', 'bool', 'string'],
)
def test_non_finite_or_invalid_token_counts_become_zero(literal: str) -> None:
    frame = (
        '{"type":"response.done","response":{"id":"resp_x","usage":{"input_tokens":'
        + literal
        + ',"output_tokens":'
        + literal
        + '}}}'
    )
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)
    turn = _only(observer.observe_upstream_frame(frame))

    assert turn.input_text_tokens == 0
    assert turn.output_text_tokens == 0
    assert turn.usage_reported is True


def test_deeply_nested_json_with_marker_yields_empty_without_raising() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)
    frame = (b'[' * 100_000) + b'turnComplete'

    assert observer.observe_upstream_frame(frame) == ()
    assert observer.turns == 0


@pytest.mark.parametrize('frame', [None, 1, ['turnComplete']])
def test_observer_non_str_bytes_input_yields_empty(frame: object) -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)

    assert observer.observe_upstream_frame(frame) == ()  # type: ignore[arg-type]
    assert observer.turns == 0


@pytest.mark.parametrize(
    'garbage',
    [None, 1, b'not json but "setup"', b'\xff\xfe "session"', '{"setup":'],
    ids=['none', 'int', 'setup_garbage', 'binary_session', 'truncated_json'],
)
def test_observe_client_frame_on_garbage_never_raises(garbage: object) -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER, model='seeded')

    observer.observe_client_frame(garbage)

    assert observer.model == 'seeded'


# -- Model capture -------------------------------------------------------------


def test_observe_client_frame_learns_gemini_setup_model_stripping_models_prefix() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER)

    observer.observe_client_frame(_frame({'setup': {'model': 'models/gemini-3.1-flash-live-preview'}}))

    assert observer.model == 'gemini-3.1-flash-live-preview'


def test_observe_client_frame_learns_openai_session_model() -> None:
    observer = RealtimeRelayObserver(OPENAI_REALTIME_PROVIDER)

    observer.observe_client_frame(_frame({'session': {'model': 'gpt-realtime-2'}}))

    assert observer.model == 'gpt-realtime-2'


@pytest.mark.parametrize(
    'payload',
    [
        {'setup': {'model': '   '}},
        {'setup': {'model': '\n\t'}},
        {'setup': {'model': 123}},
        {'setup': {'model': None}},
        {'setup': {'model': ['models/x']}},
    ],
    ids=['spaces', 'whitespace', 'int', 'none', 'list'],
)
def test_observe_client_frame_ignores_whitespace_only_and_non_string_models(payload: dict) -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER, model='seeded')

    observer.observe_client_frame(_frame(payload))

    assert observer.model == 'seeded'


def test_observe_client_frame_ignores_frame_without_setup_or_session_markers() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER, model='seeded')

    observer.observe_client_frame(_frame({'model': 'models/should-not-apply', 'config': {'voice': 'aoede'}}))

    assert observer.model == 'seeded'


def test_constructor_model_seeds_and_canonicalises_models_prefix() -> None:
    observer = RealtimeRelayObserver(GEMINI_LIVE_PROVIDER, model='models/gemini-3.1-flash-live-preview')

    observer.observe_client_frame(_frame({'type': 'input_audio_buffer.append', 'audio': 'AAAA'}))

    assert observer.model == 'gemini-3.1-flash-live-preview'


def test_constructor_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unsupported realtime provider: 'anthropic'"):
        RealtimeRelayObserver('anthropic')


# -- Pricing -------------------------------------------------------------------


@pytest.mark.parametrize(
    'provider, model, numerator',
    [
        (OPENAI_REALTIME_PROVIDER, 'gpt-realtime-2', _OPENAI_PRICED_NUMERATOR),
        (GEMINI_LIVE_PROVIDER, 'gemini-3.1-flash-live-preview', _GEMINI_31_PRICED_NUMERATOR),
        (GEMINI_LIVE_PROVIDER, 'gemini-2.5-flash-native-audio-preview-12-2025', _GEMINI_25_PRICED_NUMERATOR),
    ],
    ids=['openai_gpt_realtime_2', 'gemini_31_flash_live', 'gemini_25_native_audio'],
)
def test_realtime_turn_cost_micro_usd_matches_hand_computed_cached_subset_and_reasoning(
    provider: str, model: str, numerator: int
) -> None:
    rates = realtime_rates_for(provider, model)
    assert rates is not None
    expected = _micro(numerator)

    assert realtime_turn_cost_micro_usd(_priced_turn(provider), rates) == expected
    assert realtime_turn_cost_usd(_priced_turn(provider), rates) == expected / 1_000_000


def test_realtime_turn_cost_micro_usd_rounds_half_up_on_gemini_31_one_text_output_token() -> None:
    turn = RealtimeTurnUsage(
        provider=GEMINI_LIVE_PROVIDER,
        output_text_tokens=1,
        usage_reported=True,
        modality_split_reported=True,
        cached_split_reported=True,
    )
    rates = realtime_rates_for(GEMINI_LIVE_PROVIDER, 'gemini-3.1-flash-live-preview')
    assert rates is not None
    assert rates.output_text == 4_500_000

    assert realtime_turn_cost_micro_usd(turn, rates) == 5


@pytest.mark.parametrize(
    'provider, model, numerator, rate_card_id',
    [
        (
            OPENAI_REALTIME_PROVIDER,
            'gpt-realtime-2',
            _OPENAI_PRICED_NUMERATOR,
            'openai.gpt-realtime-2.modality.2026-09-01',
        ),
        (
            GEMINI_LIVE_PROVIDER,
            'gemini-3.1-flash-live-preview',
            _GEMINI_31_PRICED_NUMERATOR,
            'gemini.gemini-3.1-flash-live-preview.modality.2026-09-01',
        ),
        (
            GEMINI_LIVE_PROVIDER,
            'gemini-2.5-flash-native-audio-preview-12-2025',
            _GEMINI_25_PRICED_NUMERATOR,
            'gemini.gemini-2.5-flash-native-audio-preview-12-2025.modality.2026-09-01',
        ),
    ],
    ids=['openai_gpt_realtime_2', 'gemini_31_flash_live', 'gemini_25_native_audio'],
)
def test_price_realtime_turn_returns_micro_usd_rate_card_and_cost_basis(
    provider: str, model: str, numerator: int, rate_card_id: str
) -> None:
    priced = price_realtime_turn(_priced_turn(provider), model)

    assert priced == PricedUsage(
        micro_usd=_micro(numerator),
        rate_card_id=rate_card_id,
        cost_basis=REALTIME_COST_BASIS,
    )


def test_price_realtime_turn_returns_none_when_unpriceable() -> None:
    turn = RealtimeTurnUsage(provider=OPENAI_REALTIME_PROVIDER, input_text_tokens=10, usage_reported=False)

    assert turn.priceable is False
    assert price_realtime_turn(turn, 'gpt-realtime-2') is None


def test_price_realtime_turn_returns_none_for_unknown_model() -> None:
    turn = RealtimeTurnUsage(
        provider=OPENAI_REALTIME_PROVIDER,
        input_text_tokens=10,
        usage_reported=True,
        modality_split_reported=True,
        cached_split_reported=True,
    )

    assert turn.priceable is True
    assert price_realtime_turn(turn, 'gpt-realtime-mini') is None


def test_client_reported_turn_attributes_cached_text_first_and_marks_split_reported() -> None:
    turn = client_reported_turn(
        OPENAI_REALTIME_PROVIDER,
        input_text_tokens=100,
        input_audio_tokens=200,
        input_cached_tokens=150,
        output_text_tokens=1,
        output_audio_tokens=0,
    )

    assert turn.cached_text_tokens == 100
    assert turn.cached_audio_tokens == 50
    assert turn.usage_reported is True
    assert turn.modality_split_reported is True
    assert turn.cached_split_reported is True
    assert turn.priceable is True


def test_client_reported_cost_usd_unknown_model_falls_back_to_provider_default() -> None:
    turn = client_reported_turn(
        OPENAI_REALTIME_PROVIDER,
        input_text_tokens=100,
        input_audio_tokens=0,
        input_cached_tokens=40,
        output_text_tokens=0,
        output_audio_tokens=0,
    )
    default_model = DEFAULT_REALTIME_MODELS[OPENAI_REALTIME_PROVIDER]

    assert client_reported_cost_usd(OPENAI_REALTIME_PROVIDER, 'gpt-realtime-mini', turn) == client_reported_cost_usd(
        OPENAI_REALTIME_PROVIDER, default_model, turn
    )
    assert client_reported_cost_usd(OPENAI_REALTIME_PROVIDER, 'gpt-realtime-mini', turn) == 0.000256


def test_client_reported_cost_usd_unknown_provider_prices_as_gemini() -> None:
    turn = client_reported_turn(
        'anthropic',
        input_text_tokens=10,
        input_audio_tokens=0,
        input_cached_tokens=0,
        output_text_tokens=8,
        output_audio_tokens=0,
    )

    assert client_reported_cost_usd('anthropic', None, turn) == client_reported_cost_usd(
        GEMINI_LIVE_PROVIDER, DEFAULT_REALTIME_MODELS[GEMINI_LIVE_PROVIDER], turn
    )


def test_desktop_realtime_usage_cost_openai_audio_ten_output_text_five_is_00044() -> None:
    report = desktop_realtime.UsageReport(provider='openai', input_audio_tokens=10, output_text_tokens=5)

    assert desktop_realtime._usage_cost(report) == 0.00044


def test_desktop_realtime_usage_cost_discounts_cached_subset_not_added() -> None:
    report = desktop_realtime.UsageReport(provider='openai', input_text_tokens=100, input_cached_tokens=40)

    assert desktop_realtime._usage_cost(report) == 0.000256


# -- Metadata ------------------------------------------------------------------


def test_realtime_turn_metadata_without_usage_reported_has_none_usage() -> None:
    turn = RealtimeTurnUsage(provider=OPENAI_REALTIME_PROVIDER, provider_response_id='resp_abc', usage_reported=False)

    assert realtime_turn_metadata(turn) == ProviderResponseMetadata(provider_response_id='resp_abc')


def test_realtime_turn_metadata_maps_prompt_cached_output_reasoning_tool_use_and_total() -> None:
    turn = RealtimeTurnUsage(
        provider=OPENAI_REALTIME_PROVIDER,
        input_text_tokens=10,
        input_audio_tokens=20,
        input_image_tokens=5,
        cached_text_tokens=3,
        cached_audio_tokens=2,
        output_text_tokens=7,
        output_audio_tokens=11,
        reasoning_tokens=4,
        tool_use_prompt_tokens=2,
        usage_reported=True,
        provider_response_id='resp_abc',
    )

    assert realtime_turn_metadata(turn) == ProviderResponseMetadata(
        usage=ProviderUsage(
            prompt_tokens=35,
            cached_input_tokens=5,
            uncached_input_tokens=30,
            output_tokens=18,
            reasoning_tokens=4,
            output_tokens_include_reasoning=False,
            tool_use_prompt_tokens=2,
            total_tokens=59,
            cache_status=CacheStatus.PARTIAL_HIT,
        ),
        provider_response_id='resp_abc',
    )


def test_realtime_turn_metadata_clamps_cached_tokens_to_prompt() -> None:
    turn = RealtimeTurnUsage(
        provider=OPENAI_REALTIME_PROVIDER,
        input_text_tokens=4,
        input_audio_tokens=1,
        cached_text_tokens=99,
        usage_reported=True,
    )
    metadata = realtime_turn_metadata(turn)

    assert metadata.usage is not None
    assert metadata.usage.prompt_tokens == 5
    assert metadata.usage.cached_input_tokens == 5
    assert metadata.usage.uncached_input_tokens == 0
    assert metadata.usage.cache_status == CacheStatus.HIT


@pytest.mark.parametrize(
    'input_text, input_audio, cached_text, expected_status',
    [
        (10, 0, 10, CacheStatus.HIT),
        (8, 2, 4, CacheStatus.PARTIAL_HIT),
        (6, 4, 0, CacheStatus.MISS),
        (0, 0, 0, CacheStatus.NOT_APPLICABLE),
        (0, 0, 9, CacheStatus.NOT_APPLICABLE),
    ],
    ids=['hit', 'partial_hit', 'miss', 'not_applicable_prompt_zero', 'not_applicable_cached_clamped'],
)
def test_realtime_turn_metadata_cache_status(
    input_text: int, input_audio: int, cached_text: int, expected_status: CacheStatus
) -> None:
    turn = RealtimeTurnUsage(
        provider=OPENAI_REALTIME_PROVIDER,
        input_text_tokens=input_text,
        input_audio_tokens=input_audio,
        cached_text_tokens=cached_text,
        output_text_tokens=1,
        reasoning_tokens=3,
        tool_use_prompt_tokens=2,
        usage_reported=True,
    )
    metadata = realtime_turn_metadata(turn)

    assert metadata.usage is not None
    assert metadata.usage.cache_status == expected_status
    assert metadata.usage.output_tokens_include_reasoning is False
    prompt = input_text + input_audio
    cached = min(prompt, cached_text)
    assert metadata.usage.prompt_tokens == prompt
    assert metadata.usage.cached_input_tokens == cached
    assert metadata.usage.uncached_input_tokens == prompt - cached
    assert metadata.usage.output_tokens == 1
    assert metadata.usage.reasoning_tokens == 3
    assert metadata.usage.tool_use_prompt_tokens == 2
    assert metadata.usage.total_tokens == prompt + 1 + 3 + 2


# --- round-three regressions: ordinals, tool calls, caps, id bounds ----------------------


def test_each_emitted_turn_carries_its_own_ordinal_even_from_one_flush() -> None:
    observer = RealtimeRelayObserver('openai')
    observer.observe_upstream_frame(json.dumps({'type': 'response.created', 'response': {'id': 'a'}}))
    observer.observe_upstream_frame(json.dumps({'type': 'response.created', 'response': {'id': 'b'}}))
    flushed = observer.flush()
    assert [(t.ordinal, t.provider_response_id) for t in flushed] == [(1, 'a'), (2, 'b')]
    assert observer.turns == 2


def test_gemini_tool_call_is_activity_that_opens_a_turn_and_releases_a_held_one() -> None:
    observer = RealtimeRelayObserver('gemini')
    done = observer.observe_upstream_frame(
        b'{"serverContent": {"turnComplete": true}, "usageMetadata": {"promptTokenCount": 10, "responseTokenCount": 2}}'
    )
    assert done == ()
    released = observer.observe_upstream_frame(b'{"toolCall": {"functionCalls": [{"name": "x"}]}}')
    assert [(t.ordinal, t.input_tokens, t.outcome) for t in released] == [(1, 10, 'success')]
    flushed = observer.flush()  # the tool-call turn was in flight with no usage
    assert [(t.ordinal, t.outcome, t.error_class, t.usage_reported) for t in flushed] == [
        (2, 'cancelled', 'client_disconnected', False)
    ]


def test_usage_alongside_a_tool_call_belongs_to_the_new_turn_not_the_held_one() -> None:
    observer = RealtimeRelayObserver('gemini')
    observer.observe_upstream_frame(
        b'{"serverContent": {"turnComplete": true}, "usageMetadata": {"promptTokenCount": 10}}'
    )
    released = observer.observe_upstream_frame(
        b'{"toolCall": {"functionCalls": []}, "usageMetadata": {"promptTokenCount": 25}}'
    )
    assert [t.input_tokens for t in released] == [10]
    flushed = observer.flush()
    assert [(t.input_tokens, t.outcome) for t in flushed] == [(15, 'cancelled')]


def test_responses_opened_past_the_tracking_cap_are_still_flushed_as_attempts() -> None:
    observer = RealtimeRelayObserver('openai')
    for index in range(70):
        observer.observe_upstream_frame(json.dumps({'type': 'response.created', 'response': {'id': f'r{index}'}}))
    # One overflow response finishes normally: it must not steal a tracked id.
    observer.observe_upstream_frame(
        json.dumps({'type': 'response.done', 'response': {'id': 'r69', 'status': 'completed'}})
    )
    flushed = observer.flush()
    # Flush is budgeted: the first 16 open responses become rows, the rest are counted.
    assert len(flushed) == 16
    assert all(t.provider_response_id is not None for t in flushed)
    assert observer.dropped_at_flush == 53
    assert observer.turns == 17


def test_flush_past_the_budget_still_covers_untracked_overflow_in_the_drop_count() -> None:
    observer = RealtimeRelayObserver('openai')
    for index in range(66):
        observer.observe_upstream_frame(json.dumps({'type': 'response.created', 'response': {'id': f'r{index}'}}))
    flushed = observer.flush()
    assert len(flushed) == 16
    assert observer.dropped_at_flush == 50  # 48 tracked beyond the budget + 2 overflow


def test_gemini_tool_call_cancellation_is_an_interruption() -> None:
    observer = RealtimeRelayObserver('gemini')
    assert observer.observe_upstream_frame(b'{"toolCall": {"functionCalls": [{"name": "x"}]}}') == ()
    assert observer.observe_upstream_frame(b'{"toolCallCancellation": {"ids": ["call-1"]}}') == ()
    flushed = observer.flush()
    assert [(t.outcome, t.error_class, t.usage_reported) for t in flushed] == [('cancelled', 'interrupted', False)]


def test_oversized_response_ids_are_not_retained_or_reported() -> None:
    observer = RealtimeRelayObserver('openai')
    huge = 'x' * 10_000
    observer.observe_upstream_frame(json.dumps({'type': 'response.created', 'response': {'id': huge}}))
    (done,) = observer.observe_upstream_frame(
        json.dumps({'type': 'response.done', 'response': {'id': huge, 'status': 'completed'}})
    )
    assert done.provider_response_id is None
    assert observer.flush() == ()  # the anonymous entry was closed by the matching done
