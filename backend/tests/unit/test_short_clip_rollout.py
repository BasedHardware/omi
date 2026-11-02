"""Short-recording compute policy, persisted minimum admission and creation effects."""

import sys

from concurrent.futures import Future
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.structured import Structured
from utils.llm import notes_short_clip
from utils.llm.notes_refactor_metrics import RESULTS
from utils.conversations.minimum_derived import is_server_minimum
from utils.conversations import demand_processing
from utils.sync import reprocess
from tests.unit.test_process_conversation_free_tier_branch import (
    pc,
    _omi_create,
    _spy_managed_effects,
    _stub_completed_for_normal_path,
)

START = datetime(2026, 10, 31, 6, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.delenv('NOTES_SHORT_CLIP_FLOOR', raising=False)
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_PERCENT', raising=False)
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S', raising=False)


@pytest.fixture(autouse=True)
def no_summary_app(pc, monkeypatch):
    monkeypatch.setattr(pc.redis_db, 'get_user_preferred_app', lambda _uid: None)


def capture(text='A tiny recording', **kwargs):
    kwargs.setdefault('language', 'en')
    return SimpleNamespace(
        transcript_segments=[SimpleNamespace(text=text, start=0.0, end=2.0)],
        started_at=START,
        finished_at=START,
        photos=[],
        source='omi',
        **kwargs,
    )


@pytest.mark.parametrize('switch', [None, 'on', 'true', '1', 'yes', 'typo'])
def test_floor_serves_independently_of_notes_v2_and_counts_only_served_decisions(monkeypatch, switch):
    if switch is not None:
        monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', switch)
    metric = RESULTS.labels(check='short_clip', outcome='minimum')._value
    before = metric.get()
    minimum = notes_short_clip.quiet_minimum('synthetic-account', capture(), tz='UTC')
    assert minimum.title and minimum.title_provenance == 'server_minimum'
    assert minimum.overview == '' and minimum.action_items == []
    assert metric.get() == before + 1


@pytest.mark.parametrize('mode,minimum', [('off', False), ('shadow', False), ('serve', True)])
@pytest.mark.parametrize('switch', ['off', 'false', '0', 'no'])
def test_rollback_restores_legacy_admission_and_notes_v2_still_implies_floor(monkeypatch, mode, minimum, switch):
    monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', switch)
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', mode)
    metric = RESULTS.labels(check='short_clip', outcome='minimum')._value
    before = metric.get()
    assert (notes_short_clip.quiet_minimum('synthetic-account', capture()) is not None) is minimum
    assert metric.get() == before + int(minimum)


def test_existing_notes_v2_shadow_serve_cohort_retains_floor(monkeypatch):
    monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', 'off')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'shadow')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE_SERVE_PERCENT', '100')
    assert notes_short_clip.quiet_minimum('synthetic-account', capture()).title


@pytest.mark.parametrize('mode', ['off', 'serve'])
@pytest.mark.parametrize(
    'text',
    [
        'remind me to call mom',
        "don't forget milk",
        'don’t forget milk',
        'don‘t forget milk',
        'don`t forget milk',
        'Ｒｅｍｉｎｄ ｍｅ to call mom',
        'note to self: buy bread',
    ],
)
def test_explicit_reminders_bypass_both_floor_measures(monkeypatch, mode, text):
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', mode)
    assert notes_short_clip.quiet_minimum('synthetic-account', capture(text)) is None


def test_reminder_split_across_segments_is_also_exempt():
    row = capture()
    row.transcript_segments = [{'text': 'remind'}, {'text': 'me to call mom'}]
    assert notes_short_clip.quiet_minimum('synthetic-account', row) is None


@pytest.mark.parametrize('authority', ['user_kept', 'sync_relevance_user_kept', 'user_title', 'photos', 'has_photos'])
def test_user_authority_and_photos_bypass_floor(authority):
    row = capture()
    kwargs = {'user_kept': True} if authority == 'user_kept' else {}
    if not kwargs:
        setattr(row, authority, ['photo'] if authority == 'photos' else 'kept')
    assert notes_short_clip.quiet_minimum('synthetic-account', row, **kwargs) is None


@pytest.mark.parametrize('text', ['...', 'A tiny recording'])
def test_nonempty_capture_always_has_a_nonempty_title_even_without_selected_text(text, monkeypatch):
    monkeypatch.setattr(notes_short_clip, 'in_profile_segments', lambda _segments: [])
    result = notes_short_clip.quiet_minimum('synthetic-account', capture(text), tz='UTC')
    assert result.title.strip() and result.title_provenance == 'server_minimum'


def test_real_structure_boundary_serves_floor_before_any_notes_or_relevance_call(pc, monkeypatch):
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda *_args: 'UTC')
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda *_args: 'en')
    paid = MagicMock(side_effect=AssertionError('paid notes or relevance'))
    monkeypatch.setattr(pc, 'get_conversation_notes', paid)
    monkeypatch.setattr(pc, 'should_discard_conversation', paid)
    observed = []
    structured, discarded = pc._get_structured('synthetic-account', 'en', capture(), relevance_observer=observed.append)
    assert structured.title and is_server_minimum(SimpleNamespace(structured=structured)) and not discarded
    assert [decision.reason for decision in observed] == ['content_below_floor']
    paid.assert_not_called()


@pytest.mark.parametrize(
    'reason,trigger',
    [
        ('reminder', 'CAPTURE_END'),
        ('reminder', 'SERVER_RECOVERY'),
        ('reminder_curly', 'CAPTURE_END'),
        ('reminder_curly', 'SERVER_RECOVERY'),
        ('user_kept', 'CAPTURE_END'),
        ('user_kept', 'SERVER_RECOVERY'),
        ('switch_off', 'CAPTURE_END'),
    ],
)
def test_real_structure_boundary_reaches_real_notes_admission_when_exempt(pc, monkeypatch, reason, trigger):
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda *_args: 'UTC')
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda *_args: 'en')
    # Sentinel at the notes boundary avoids a provider call while proving the
    # existing notes/tasks path is reached rather than returning a minimum.
    paid = MagicMock(side_effect=RuntimeError('notes boundary reached'))
    monkeypatch.setattr(pc, 'get_conversation_notes', paid)
    monkeypatch.setattr(pc, 'should_discard_conversation', lambda *_a, **_k: False)
    monkeypatch.setattr(pc, '_calendar_overlap_retains_conversation', lambda *_a, **_k: False)
    if reason == 'switch_off':
        monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', 'off')
    row = capture(
        'don’t forget milk'
        if reason == 'reminder_curly'
        else 'remind me to call mom' if reason == 'reminder' else 'A tiny recording'
    )
    with pytest.raises(RuntimeError, match='notes boundary reached'):
        pc._get_structured(
            'synthetic-account',
            'en',
            row,
            user_kept=reason == 'user_kept',
            trigger=getattr(pc.ProcessingTrigger, trigger),
        )
    paid.assert_called_once()


@pytest.mark.parametrize('minimum', [True, False])
def test_memory_boundary_skips_all_l1_l2_work_only_for_persisted_minimum(pc, monkeypatch, minimum):
    row = SimpleNamespace(
        id='synthetic-conversation',
        structured=Structured(title='Recording', title_provenance='server_minimum' if minimum else None),
        transcript_segments=[],
        source='omi',
    )
    service = MagicMock()
    monkeypatch.setattr(pc, 'MemoryService', lambda **_kw: service)
    monkeypatch.setattr(pc, '_sweep_owned_writer_mode', lambda _uid: None)
    extraction = MagicMock(return_value=SimpleNamespace(count=0, path='synthetic'))
    monkeypatch.setattr(pc, '_extract_memories_inner', extraction)
    pc.extract_memories('synthetic-account', row)
    assert service.ensure_canonical_mutation_ready.call_count == int(not minimum)
    assert extraction.call_count == int(not minimum)


@pytest.mark.parametrize('minimum', [True, False])
@pytest.mark.parametrize('explicit', [True, False])
@pytest.mark.parametrize('app_result', ['Summary result', ''])
def test_summary_app_boundary_honors_explicit_selection_on_minimum_rows(pc, monkeypatch, minimum, explicit, app_result):
    row = capture()
    row.id, row.language, row.apps_results = 'synthetic-conversation', 'en', []
    row.started_at = None
    row.structured = Structured(title='Recording', title_provenance='server_minimum' if minimum else None)
    app = SimpleNamespace(id='synthetic-app', name='Summary', enabled=True, works_with_memories=lambda: True)
    available = MagicMock(return_value=[app])
    monkeypatch.setattr(pc, 'get_available_apps', available)
    monkeypatch.setattr(pc, 'conversation_transcript_for_llm', lambda *_args: 'Synthetic workshop discussion')
    row.apps_results = [SimpleNamespace(app_id=app.id, content='Old app result')]
    model = MagicMock(return_value=app_result)
    monkeypatch.setattr(pc, 'get_app_result', model)

    def inline(_executor, fn, *args):
        future = Future()
        future.set_result(fn(*args))
        return future

    monkeypatch.setattr(pc, 'submit_with_context', inline)
    monkeypatch.setattr(pc.redis_db, 'get_user_preferred_app', lambda _uid: app.id)
    kwargs = dict(
        app_id=app.id if explicit else None, explicit_app=app if explicit else None, replace_selected_result=True
    )
    if explicit and not app_result:
        with pytest.raises(pc.ExplicitAppSelectionFailedError):
            pc.trigger_conversation_apps('synthetic-account', row, **kwargs)
    else:
        assert pc.trigger_conversation_apps('synthetic-account', row, **kwargs)
    assert available.call_count == model.call_count == int(explicit or not minimum)
    expected = app_result if app_result and (explicit or not minimum) else 'Old app result'
    assert row.apps_results[0].content == expected


@pytest.mark.parametrize('deferred', [False, True])
@pytest.mark.parametrize('lazy', [False, True])
def test_minimum_creation_preserves_webhook_and_audio_without_llm_derived_work(pc, monkeypatch, deferred, lazy):
    assert sys.modules['utils.conversations.demand_processing'] is demand_processing
    assert sys.modules['utils.sync.reprocess'] is reprocess

    monkeypatch.setattr(demand_processing, 'lazy_enrichment_enabled', lambda _uid: lazy)
    mark_effects = MagicMock(side_effect=AssertionError('minimum queued lazy enrichment'))
    monkeypatch.setattr(reprocess, 'mark_effects', mark_effects)
    structure_boundary = pc._get_structured
    memory_boundary, app_boundary = pc.extract_memories, pc.trigger_conversation_apps
    spies = _spy_managed_effects(monkeypatch, pc)
    completed = _stub_completed_for_normal_path(monkeypatch, pc)
    minimum = notes_short_clip.quiet_minimum('synthetic-account', capture(), tz='UTC')
    completed.structured = minimum
    completed.private_cloud_sync_enabled = True
    monkeypatch.setattr(pc, '_get_structured', structure_boundary)
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda *_args: 'UTC')
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda *_args: 'en')
    # Keep the real guarded boundaries inside the production effect bundle.
    monkeypatch.setattr(pc, 'extract_memories', memory_boundary)
    monkeypatch.setattr(pc, '_extract_memories', memory_boundary)
    monkeypatch.setattr(pc, 'trigger_conversation_apps', app_boundary)
    paid = MagicMock(side_effect=AssertionError('minimum attempted derived intelligence'))
    monkeypatch.setattr(pc, '_extract_memories_inner', paid)
    monkeypatch.setattr(pc, 'get_available_apps', paid)
    monkeypatch.setattr(pc.redis_db, 'try_acquire_conversation_goal_lock', paid)
    webhook = AsyncMock()
    monkeypatch.setattr(pc, 'conversation_created_webhook', webhook)
    submitted = []

    def inline(_executor, fn, *args):
        submitted.append(fn.__name__)
        if fn.__name__ in ('_run_webhook', 'update_goal_progress'):
            fn(*args)

    monkeypatch.setattr(pc, 'submit_with_context', inline)
    pc.conversations_db.create_audio_files_from_chunks.return_value = []
    effects, dispositions = [], []
    pc.process_conversation(
        'synthetic-account',
        'en',
        _omi_create(),
        defer_derived_effects=deferred,
        derived_effects_observer=effects.append,
        derived_effects_disposition_observer=dispositions.append,
    )
    if deferred:
        webhook.assert_not_called()
        assert len(effects) == 1
        effects[0]()
    assert 'save_structured_vector' not in submitted
    assert dispositions == [pc.DerivedEffectsDisposition.RUN]
    spies['assign_folder'].assert_not_called()
    pc.conversations_db.create_audio_files_from_chunks.assert_called()
    webhook.assert_awaited_once()
    paid.assert_not_called()
    mark_effects.assert_not_called()


def test_minimum_marker_supports_stored_dicts_and_enriched_replacement():
    row = {'structured': {'title_provenance': 'server_minimum'}}
    assert is_server_minimum(row)
    row['structured'] = {'title_provenance': None}
    assert not is_server_minimum(row)


@pytest.mark.parametrize(
    'language,text',
    [
        ('th', 'วันนี้เราจะประชุมเรื่องแผนงานและกำหนดส่งโครงการในเดือนหน้า'),
        ('lo', 'ມື້ນີ້ພວກເຮົາຈະປະຊຸມເພື່ອວາງແຜນວຽກໃນເດືອນໜ້າ'),
        ('km', 'ថ្ងៃនេះយើងនឹងប្រជុំដើម្បីពិភាក្សាអំពីផែនការការងារសម្រាប់ខែក្រោយ'),
        ('my', 'ဒီနေ့အစည်းအဝေးမှာနောက်လအတွက်စီမံကိန်းနဲ့အချိန်ဇယားကိုဆွေးနွေးမယ်'),
        ('ja', '来月のプロジェクトの計画と納期について今日の会議で話し合います'),
        ('zh', '今天我们讨论下个月的项目计划和交付时间然后确认每个人负责的工作'),
        ('zh', '\U00020000\U00020001\U00020002\U00020003\U00020004'),
        ('ko', '다음달프로젝트일정과담당업무를오늘회의에서논의하겠습니다'),
    ],
)
@pytest.mark.parametrize('capture_tag', ['actual', 'en', 'multi'])
def test_unspaced_scripts_use_duration_even_when_capture_is_mistagged(language, text, capture_tag):
    row = capture(text, language=language if capture_tag == 'actual' else capture_tag)
    row.transcript_segments[0].end = 60.0
    assert notes_short_clip.quiet_minimum('synthetic-account', row) is None


@pytest.mark.parametrize('language', ['fr', 'es', 'vi', 'th', 'ja', 'zh', 'multi', 'auto', None])
@pytest.mark.parametrize('seconds,minimum', [(None, False), (3.9, True), (4.0, False), (60.0, False)])
def test_word_rule_is_english_only_and_unknown_duration_never_floors_other_languages(language, seconds, minimum):
    row = capture('Un court rappel', language=language)
    row.transcript_segments[0].end = seconds
    assert (notes_short_clip.quiet_minimum('synthetic-account', row) is not None) is minimum


@pytest.mark.parametrize('language', ['en', 'en-US', 'en-GB'])
def test_known_english_still_uses_word_rule(language):
    row = capture(language=language)
    row.transcript_segments[0].end = 60.0
    assert notes_short_clip.quiet_minimum('synthetic-account', row) is not None


def _notes_boundary(pc, monkeypatch):
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda *_args: 'UTC')
    # An English output preference must never enable the word rule on other speech.
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda *_args: 'en')
    monkeypatch.setattr(pc, 'should_discard_conversation', lambda *_a, **_k: False)
    monkeypatch.setattr(pc, '_calendar_overlap_retains_conversation', lambda *_a, **_k: False)
    notes = MagicMock(side_effect=RuntimeError('notes boundary reached'))
    monkeypatch.setattr(pc, 'get_conversation_notes', notes)
    return notes


@pytest.mark.parametrize(
    'language,text',
    [
        ('fr', 'Rappelle-moi de téléphoner à maman'),
        ('ja', '明日母に電話するのを忘れないで'),
        (None, 'Call mom tomorrow'),
    ],
)
def test_non_english_reminder_reaches_full_notes_despite_english_output_preference(pc, monkeypatch, language, text):
    notes = _notes_boundary(pc, monkeypatch)
    row = capture(text, language=language)
    row.transcript_segments[0].end = 5.0
    with pytest.raises(RuntimeError, match='notes boundary reached'):
        pc._get_structured('synthetic-account', language or 'en', row)
    notes.assert_called_once()


@pytest.mark.parametrize(
    'structured',
    [
        Structured(title='Earlier model title'),
        Structured(title='Earlier model title', overview='Previously enriched notes'),
        Structured(title='Recording', title_provenance='server_minimum', overview='Preserved overview'),
        Structured(
            title='Recording',
            title_provenance='server_minimum',
            sections=[{'heading': 'Plan', 'body_markdown': 'Ship it'}],
        ),
    ],
)
def test_user_reprocess_of_enriched_short_row_reaches_notes_instead_of_replacing_with_minimum(
    pc, monkeypatch, structured
):
    notes = _notes_boundary(pc, monkeypatch)
    row = capture(structured=structured)
    with pytest.raises(RuntimeError, match='notes boundary reached'):
        pc._get_structured('synthetic-account', 'en', row, trigger=pc.ProcessingTrigger.USER_REPROCESS, user_kept=False)
    notes.assert_called_once()
    assert row.structured == structured


def test_empty_structure_and_prior_minimum_remain_eligible():
    for structured in (Structured(), Structured(title='Recording', title_provenance='server_minimum')):
        assert notes_short_clip.quiet_minimum('synthetic-account', capture(structured=structured)) is not None


@pytest.mark.parametrize('selection', ['app_id', 'preferred', 'omi', 'stored_app'])
def test_selected_summary_app_bypasses_floor_and_reaches_full_notes(pc, monkeypatch, selection):
    notes = _notes_boundary(pc, monkeypatch)
    row = capture()
    if selection == 'preferred':
        monkeypatch.setattr(pc.redis_db, 'get_user_preferred_app', lambda _uid: 'chosen-app')
    if selection == 'stored_app':
        row.app_id = 'chosen-app'
    with pytest.raises(RuntimeError, match='notes boundary reached'):
        pc._get_structured(
            'synthetic-account',
            'en',
            row,
            trigger=pc.ProcessingTrigger.USER_REPROCESS,
            summary_app_selected=selection in ('app_id', 'omi'),
        )
    notes.assert_called_once()


def test_explicit_app_request_is_passed_from_processing_to_floor_admission(pc, monkeypatch):
    spies = _spy_managed_effects(monkeypatch, pc)
    _stub_completed_for_normal_path(monkeypatch, pc)
    pc.process_conversation(
        'synthetic-account', 'en', _omi_create(), app_id='chosen-app', trigger=pc.ProcessingTrigger.USER_REPROCESS
    )
    assert spies['get_structured'].call_args.kwargs['summary_app_selected'] is True
    assert spies['trigger_apps'].call_args.kwargs['app_id'] == 'chosen-app'


def test_app_lookup_failure_preserves_full_notes_and_reports_fallback(monkeypatch):
    from utils.llm import notes_short_clip_policy as policy

    fallback = MagicMock()
    monkeypatch.setattr(policy, 'record_fallback', fallback)
    assert policy.selected_summary_app('synthetic-account', False, MagicMock(side_effect=ConnectionError()))
    fallback.assert_called_once()


def test_later_sync_speech_promotes_prior_minimum_to_full_notes_admission(pc, monkeypatch):
    notes = _notes_boundary(pc, monkeypatch)
    row = capture()
    row.structured = notes_short_clip.quiet_minimum('synthetic-account', row)
    row.transcript_segments.append(
        SimpleNamespace(
            text='We decided to deliver the updated project plan next Monday morning together', start=2.0, end=20.0
        )
    )
    with pytest.raises(RuntimeError, match='notes boundary reached'):
        pc._get_structured('synthetic-account', 'en', row, trigger=pc.ProcessingTrigger.SYNC_UPDATE)
    notes.assert_called_once()


@pytest.mark.parametrize('update_only', [False, True])
def test_minimum_vector_writer_skips_embedding_and_index_work(pc, monkeypatch, update_only):
    row = capture(structured=Structured(title='Recording', title_provenance='server_minimum'))
    embedding, upsert, metadata = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(pc, 'generate_embedding', embedding)
    monkeypatch.setattr(pc, 'upsert_vector2', upsert)
    monkeypatch.setattr(pc, 'update_vector_metadata', metadata)
    assert pc.save_structured_vector('synthetic-account', row, update_only=update_only)
    embedding.assert_not_called()
    upsert.assert_not_called()
    metadata.assert_not_called()
