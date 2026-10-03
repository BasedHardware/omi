"""Offline synthetic catalog: real admission, NLLB adapter, cache and callback.

No model inference: the transport returns authored translations or deliberately
bad English rewrites. Numbers measure pipeline policy, not NLLB model quality.
"""

import json
from types import SimpleNamespace

import httpx
import pytest

from config.translation import TranslationProvider, translation_output_guard_enabled, translation_profile_gate_enabled
from models.transcript_segment import TranscriptSegment
from tests.unit.translation_test_support import DictTranslationStore, profile
from utils.stt.language_policy import LiveLanguageProfile
from utils.translation import TranslationService, TranslationNeed, classify_translation_need
from utils.translation_cache import ConversationLanguageState, should_persist_translation
from utils.translation_coordinator import TranslationCoordinator
from utils.translation_core.cache import CachedTranslation, TranslationCache
from utils.translation_core.metrics import NoopTranslationMetrics, PrometheusTranslationMetrics
from utils.translation_core.planner import fingerprint_text
from utils.translation_core.providers import NllbTranslationProvider, TranslationProviderChain
from utils.translation_core.quality import lexical_overlap, output_rejection_reason

# Authored here; no account transcripts or screenshot text.
ENGLISH = (
    'Please try again.',
    'It looks fine.',
    'Can you hear us?',
    'That sounds good.',
    'Let us begin.',
    'We can start now.',
    'I am ready.',
    'Are we ready?',
    'Just a moment.',
    'Wait a second.',
    'Keep going please.',
    'Go on please.',
    'This looks great.',
    'That is correct.',
    'I think so too.',
    'It works for me.',
    'We should go.',
    'Please carry on.',
    'What happened here?',
    'Where did it go?',
    'Can we move on?',
    'I understand now.',
    'We need more time.',
    'See you tomorrow.',
    'Thanks for coming.',
    'Have a good day.',
    'Let me check.',
    'Give me a minute.',
    'Please sit down.',
    'Close the door.',
    'Open the window.',
    'Turn it off.',
    'Turn it back on.',
    'Is that all?',
    'Anything else?',
    'Maybe next time.',
    'Perhaps it is fine.',
    'Seems fine to me.',
    'Does look correct.',
    'Still looks good.',
    'Please come in.',
    'Call me later.',
    'See you later.',
    'Talk to you soon.',
    'I will be there.',
    'That makes sense.',
    'It is all right.',
    'Let us try once more.',
)
FOREIGN = (
    ('pt', 'Precisamos terminar o trabalho antes do almoço.', 'We need to finish the work before lunch.'),
    ('pt', 'Por favor, feche a janela da cozinha.', 'Please close the kitchen window.'),
    ('es', 'Necesitamos comprar comida para mañana.', 'We need to buy food for tomorrow.'),
    ('es', 'La reunión empieza después del almuerzo.', 'The meeting starts after lunch.'),
    ('hi', 'कृपया बैठक शुरू होने से पहले खिड़की बंद कर दें।', 'Please close the window before the meeting starts.'),
    ('hi', 'हमें कल सुबह जल्दी स्टेशन पहुंचना होगा।', 'We must reach the station early tomorrow morning.'),
    ('zh', '请在会议开始之前把厨房的窗户关上。', 'Please close the kitchen window before the meeting starts.'),
    ('zh', '我们明天早上需要一起去火车站接朋友。', 'We need to meet our friend at the station tomorrow morning.'),
)
MIXED = (
    ('pt', 'Precisamos terminar o trabalho, then we can rest.', 'We need to finish the work, then we can rest.'),
    (
        'es',
        'La reunión empieza después del almuerzo, then we can rest.',
        'The meeting starts after lunch, then we can rest.',
    ),
    (
        'hi',
        'हमें कल सुबह जल्दी स्टेशन पहुंचना होगा, then we can rest.',
        'We must reach the station early tomorrow morning, then we can rest.',
    ),
    (
        'zh',
        '我们明天早上需要一起去火车站接朋友, then we can rest.',
        'We need to meet our friend at the station tomorrow morning, then we can rest.',
    ),
)


def segment(text, identity='segment'):
    return TranscriptSegment(id=identity, text=text, is_user=False, start=0, end=1)


def nllb_service(outputs, store=None):
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                'translations': [
                    {
                        'translated_text': outputs.get(text, 'The meaning has been rewritten in English.'),
                        'detected_language_code': body.get('source_language_code', 'af'),
                    }
                    for text in body['contents']
                ]
            },
        )

    client = httpx.Client(base_url='http://nllb.test', transport=httpx.MockTransport(respond))
    metrics = NoopTranslationMetrics()
    cache = TranslationCache(persistent=store, metrics=metrics)
    chain = TranslationProviderChain(
        {TranslationProvider.nllb: NllbTranslationProvider(client_factory=lambda _: client)},
        metrics,
    )
    return (
        TranslationService(
            cache=cache,
            provider_chain=chain,
            profile_resolver=lambda: profile((TranslationProvider.nllb,)),
            metrics=metrics,
        ),
        calls,
        client,
    )


async def evaluate(texts, expected, outputs, target='en', realtime_interpreter=False):
    service, calls, client = nllb_service(outputs)
    ready = []

    async def callback(*args):
        ready.append(args)

    coordinator = TranslationCoordinator(
        target, service, callback, expected_languages=expected, realtime_interpreter=realtime_interpreter
    )
    for index, text in enumerate(texts):
        await coordinator.observe([segment(text, str(index))], [], 'conversation')
    await coordinator.flush()
    client.close()
    return ready, calls


@pytest.mark.parametrize('texts', [(text,) for text in ENGLISH])
async def test_adversarial_english_catalog_zero_false_badges(monkeypatch, texts):
    monkeypatch.setenv('TRANSLATION_PROFILE_GATE_ENABLED', 'true')
    baseline = sum(classify_translation_need(text, 'en', True) == TranslationNeed.TRANSLATE for text in texts)
    assert len(ENGLISH) >= 36
    ready, calls = await evaluate(texts, LiveLanguageProfile.create('en', multi=True, uid=None).expected, {})
    assert ready == []
    assert calls == []


@pytest.mark.parametrize('language,source,output', FOREIGN + MIXED)
async def test_genuine_and_code_switched_recall(language, source, output):
    expected = LiveLanguageProfile.create(language, multi=True, uid=None).expected
    ready, calls = await evaluate([source], expected, {source: output})
    assert len(ready) == 1, (language, source, calls)
    assert ready[0][1] == output


@pytest.mark.parametrize(
    'source,output',
    [
        ('The device is working correctly.', 'The device is not working correctly.'),
        ('It does appear to work.', 'It does not appear to work.'),
        ('Please leave the window open.', 'Please leave the window open'),
        ('THIS IS THE FINAL VERSION.', 'This is the final version.'),
    ],
)
@pytest.mark.parametrize('cache_hit', [False, True])
async def test_guard_independent_of_echoed_language_and_profile(source, output, cache_hit):
    store = DictTranslationStore()
    service, calls, client = nllb_service({source: output}, store)
    if cache_hit:
        store.values[(fingerprint_text(source), 'en')] = CachedTranslation(output, 'af')
    outcomes = service.translate_outcomes('en', [('one', source)], source_language='af')
    assert outcomes[0].text == source
    assert not should_persist_translation(source, output, 'af', 'en')
    assert store.puts == []
    assert not store.negative
    assert len(calls) == (0 if cache_hit else 1)
    client.close()


@pytest.mark.parametrize(
    'source,output,target',
    [
        ('Please send the final report amanhã.', 'Please send the final report tomorrow.', 'en'),
        ('Please send the final report mañana.', 'Please send the final report tomorrow.', 'en'),
        ('Please send the final report कल.', 'Please send the final report tomorrow.', 'en'),
        ('Please send the final report 明天.', 'Please send the final report tomorrow.', 'en'),
        ('O hotel central é moderno.', 'The central hotel is modern.', 'en'),
        ('La pizza es deliciosa.', 'La pizza è deliziosa.', 'it'),
    ],
)
def test_overlap_does_not_discard_foreign_edits(source, output, target):
    assert should_persist_translation(source, output, 'untrusted', target)


def test_profile_prior_escape_hatches_and_rollback(monkeypatch):
    state = ConversationLanguageState('en')
    unexpected = 'Precisamos terminar o trabalho.'
    assert not state.source_is_plausible(unexpected, ('en',))
    assert not state.source_is_plausible(unexpected, ())
    assert state.source_is_plausible(unexpected, ('pt-BR', 'en'))
    assert state.source_is_plausible(
        'Precisamos terminar todo este trabalho antes de começar a próxima reunião.', ('en',)
    )
    assert state.source_is_plausible(unexpected, ('en',))
    monkeypatch.setenv('TRANSLATION_PROFILE_GATE_ENABLED', 'false')
    assert ConversationLanguageState('en').source_is_plausible(unexpected, ('en',))


def test_flags_default_on_and_read_at_call_boundary(monkeypatch):
    for key in ('TRANSLATION_PROFILE_GATE_ENABLED', 'TRANSLATION_OUTPUT_GUARD_ENABLED'):
        monkeypatch.delenv(key, raising=False)
    assert translation_profile_gate_enabled() and translation_output_guard_enabled()
    source, output = 'The device is working correctly.', 'The device is not working correctly.'
    assert lexical_overlap(source, output) >= 0.80
    assert output_rejection_reason(source, output, 'en') == 'near_copy'
    monkeypatch.setenv('TRANSLATION_OUTPUT_GUARD_ENABLED', 'false')
    assert should_persist_translation(source, output, 'af', 'en')


def test_decision_metrics_wire_existing_skip_counter_with_bounded_reasons():
    metrics = PrometheusTranslationMetrics()
    child = metrics._skips.labels(target_lang='en', reason='out_of_profile')
    before = child._value.get()
    metrics.decision('en-US', 'defer', 'out_of_profile')
    assert child._value.get() == before + 1
    metrics.decision('en', 'user supplied arbitrary decision', 'user supplied arbitrary reason')
    assert metrics._decisions.labels(target_lang='en', decision='other', reason='other')._value.get() >= 1


async def test_defer_never_poison_shared_cache_or_teach_foreign_prior():
    store = DictTranslationStore()
    service, calls, client = nllb_service({}, store)
    ready = []

    async def callback(*args):
        ready.append(args)

    coordinator = TranslationCoordinator('en', service, callback, expected_languages=('en',))
    text = 'Precisamos terminar o trabalho.'
    for _ in range(5):
        await coordinator.observe([segment(text)], [], 'conversation')
    assert not coordinator.language_state.established_languages
    assert not store.negative and not store.puts
    assert not coordinator._batch_buffer
    assert not calls and not ready
    await coordinator.flush()
    client.close()


async def test_prefix_cache_rewrite_cannot_bypass_output_guard():
    source = 'The device is working correctly.'
    output = 'The device is not working correctly.'
    store = DictTranslationStore()
    store.values[(fingerprint_text(source), 'en')] = CachedTranslation(output, 'af')
    service, calls, client = nllb_service({}, store)
    ready = []

    async def callback(*args):
        ready.append(args)

    coordinator = TranslationCoordinator('en', service, callback)
    coordinator._get_or_create_state('segment').committed_text = 'An earlier revision.'
    await coordinator.observe([segment(source)], [], 'conversation')
    await coordinator.flush()
    assert not ready and not calls
    assert store.negative == {(fingerprint_text(source), 'en')}
    assert not coordinator.language_state.established_languages
    client.close()


async def test_conversation_evidence_resets_and_expected_switch_exits_monolingual():
    source, output = FOREIGN[0][1:]
    service, calls, client = nllb_service({source: output})
    ready = []

    async def callback(*args):
        ready.append(args)

    coordinator = TranslationCoordinator('en', service, callback, expected_languages=('pt', 'en'))
    coordinator.language_state.monolingual = True
    coordinator.language_state.consecutive_target = 4
    coordinator.language_state.established_languages.add('da')
    await coordinator.observe([segment(source)], [], 'first')
    await coordinator._flush_batch()
    assert ready and not coordinator.language_state.monolingual
    await coordinator.observe([segment('An ordinary English sentence.', 'next')], [], 'second')
    assert 'da' not in coordinator.language_state.established_languages
    await coordinator.flush()
    client.close()


async def test_profile_flag_off_restores_legacy_admissions(monkeypatch):
    monkeypatch.setenv('TRANSLATION_PROFILE_GATE_ENABLED', 'false')
    # Substantial output edit deliberately outside the lexical guard's scope.
    ready, calls = await evaluate(ENGLISH, ('en',), {})
    baseline = sum(classify_translation_need(text, 'en', True) == TranslationNeed.TRANSLATE for text in ENGLISH)
    assert len(ready) == baseline and calls
    print(f'EVAL English: baseline false admissions/badges={baseline}/{len(ENGLISH)}; profile gate on=0/{len(ENGLISH)}')


async def test_no_profile_english_catalog_has_no_false_admissions():
    ready, calls = await evaluate(ENGLISH, (), {})
    assert not ready and not calls


async def test_no_profile_requires_source_evidence_but_keeps_clear_foreign_speech():
    ambiguous_latin = 'Precisamos terminar o trabalho.'
    substantial_latin = 'Precisamos terminar todo este trabalho antes de começar a próxima reunião.'
    short_non_latin = '请在会议开始之前把厨房的窗户关上。'
    assert not ConversationLanguageState('en').source_is_plausible(ambiguous_latin, ())
    assert ConversationLanguageState('en').source_is_plausible(substantial_latin, ())
    assert ConversationLanguageState('en').source_is_plausible(short_non_latin, ())
    outputs = {
        substantial_latin: 'We need to finish all this work before the next meeting begins.',
        short_non_latin: 'Please close the kitchen window before the meeting starts.',
    }
    ready, _calls = await evaluate([ambiguous_latin, substantial_latin, short_non_latin], (), outputs)
    assert len(ready) == 2


@pytest.mark.parametrize('expected', [(), ('en',)])
async def test_phone_interpreter_keeps_short_foreign_replies(expected):
    source = 'Precisamos terminar o trabalho.'
    output = 'We need to finish the work.'
    ready, calls = await evaluate([source], expected, {source: output}, realtime_interpreter=True)
    assert len(ready) == 1 and calls


@pytest.mark.parametrize(
    'target,expected,source,output',
    [
        (
            'pt',
            ('pt', 'en'),
            'We need to finish this work before lunch.',
            'Precisamos terminar este trabalho antes do almoço.',
        ),
        (
            'pt',
            ('es', 'pt'),
            'Necesitamos terminar este trabajo antes del almuerzo.',
            'Precisamos terminar este trabalho antes do almoço.',
        ),
        ('da', ('no', 'da'), 'Vi må avslutte møtet før middag.', 'Vi skal afslutte mødet inden middag.'),
    ],
)
async def test_non_english_targets_and_close_language_pairs(target, expected, source, output):
    ready, calls = await evaluate([source], expected, {source: output}, target=target)
    assert len(ready) == 1 and calls
    assert ready[0][1] == output


async def test_conversation_change_discards_prior_queued_work_even_with_reused_segment_id():
    source, output = FOREIGN[0][1:]
    service, calls, client = nllb_service({source: output})
    ready = []

    async def callback(*args):
        ready.append(args)

    coordinator = TranslationCoordinator('en', service, callback, expected_languages=('pt', 'en'))
    await coordinator.observe([segment(source)], [], 'old')
    await coordinator.observe([segment('An ordinary English sentence.')], [], 'new')
    await coordinator.flush()
    assert not calls and not ready
    assert coordinator.language_state.established_languages == set()
    client.close()


async def test_echoed_target_code_cannot_negative_cache_foreign_source():
    source = 'Precisamos terminar o trabalho antes do almoço.'
    store = DictTranslationStore()
    service, _calls, client = nllb_service({source: source}, store)
    ready = []

    async def callback(*args):
        ready.append(args)

    coordinator = TranslationCoordinator('en', service, callback, source_language='en', expected_languages=('pt', 'en'))
    await coordinator.observe([segment(source)], [], 'conversation')
    await coordinator.flush()
    assert not ready and not store.negative
    client.close()


def test_ambiguous_code_switch_remains_deferred_not_falsely_proven():
    # The original detector also defers this Spanish/English phrase. Expected
    # language is a prior, not permission to turn low confidence into certainty.
    text = 'Necesitamos comprar comida, then we can rest.'
    assert classify_translation_need(text, 'en', True) != TranslationNeed.TRANSLATE
