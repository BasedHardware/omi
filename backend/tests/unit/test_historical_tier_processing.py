"""Historical-tier (T1+) rows through process_conversation.

Automatic triggers store the row without a model call, before the funded-budget
block; owner triggers generate a summary that takes no derived effects.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.conversation import Conversation
from models.conversation_enums import ConversationStatus
from models.structured import Structured
from tests.unit.test_process_conversation_free_tier_branch import (  # noqa: F401  (module fixture)
    _capture_all_persists,
    _existing_desktop,
    _spy_managed_effects,
    _stub_completed_for_normal_path,
    pc,
)
from utils.conversations import historical_minimum
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.conversations.processing_trigger import ProcessingTrigger

AUTOMATIC = sorted(set(ProcessingTrigger) - historical_minimum.SUMMARY_TRIGGERS, key=lambda t: t.value)
OWNER = sorted(historical_minimum.SUMMARY_TRIGGERS, key=lambda t: t.value)


def _historical(**updates) -> Conversation:
    row = _existing_desktop('historical-row').model_copy(update={'processing_tier': 'historical', **updates})
    return row


def _forbid_funded_block(monkeypatch, pc):
    # Funded admission is on and the budget is gone: the funded block would store a
    # budget-waiting shell. The historical short-circuit must answer before it asks.
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda *_: True)
    allowed = MagicMock(side_effect=AssertionError('the historical short-circuit runs before the funded block'))
    monkeypatch.setattr(pc.funded_processing, 'processing_allowed', allowed)
    return allowed


def test_trigger_table_splits_owner_and_automatic_triggers():
    assert ProcessingTrigger.HISTORICAL_OPEN in historical_minimum.SUMMARY_TRIGGERS
    assert ProcessingTrigger.USER_REPROCESS in historical_minimum.SUMMARY_TRIGGERS
    assert ProcessingTrigger.MERGE in historical_minimum.SUMMARY_TRIGGERS
    for trigger in (
        ProcessingTrigger.SYNC_UPDATE,
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.SERVER_RECOVERY,
        ProcessingTrigger.SILENT_BACKFILL,
        ProcessingTrigger.CAPTURE_END,
    ):
        assert historical_minimum.short_circuits({'processing_tier': 'historical'}, trigger)
        assert not historical_minimum.short_circuits({'processing_tier': None}, trigger)


@pytest.mark.parametrize('trigger', AUTOMATIC, ids=lambda t: t.value)
def test_automatic_triggers_store_without_a_model_before_the_funded_block(monkeypatch, pc, trigger):
    spies = _spy_managed_effects(monkeypatch, pc)
    _forbid_funded_block(monkeypatch, pc)
    payloads = _capture_all_persists(monkeypatch, pc)
    submitted = MagicMock(side_effect=AssertionError('no derived work for a historical row'))
    monkeypatch.setattr(pc, 'submit_with_context', submitted)
    disposition = []
    row = _historical(structured=Structured(title=''), status=ConversationStatus.processing, deferred=True)

    result = pc.process_conversation(
        'uid', 'en', row, trigger=trigger, derived_effects_disposition_observer=disposition.append
    )

    spies['get_structured'].assert_not_called()
    for key in ('extract_memories', 'extract_memories_inner', 'trigger_apps', 'assign_folder'):
        spies[key].assert_not_called()
    submitted.assert_not_called()
    assert disposition == [pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS]
    payload = payloads[-1]
    assert payload['status'] == 'completed' and payload['deferred'] is False
    assert payload[pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD] is True
    assert payload['summary_blocked_reason'] == 'historical_on_open'
    assert payload['processing_tier'] == 'historical'
    # The final deterministic title carries no provenance, so it owes no summary.
    assert result.structured.title and result.structured.title_provenance is None
    assert 'title_provenance' not in (payload['structured'] or {}) or payload['structured']['title_provenance'] is None


def test_a_later_append_keeps_the_open_time_summary(monkeypatch, pc):
    spies = _spy_managed_effects(monkeypatch, pc)
    _forbid_funded_block(monkeypatch, pc)
    payloads = _capture_all_persists(monkeypatch, pc)
    summary = Structured(title='Opened earlier', overview='The summary written on open')
    pc.process_conversation('uid', 'en', _historical(structured=summary), trigger=ProcessingTrigger.SYNC_UPDATE)
    spies['get_structured'].assert_not_called()
    assert payloads[-1]['structured']['overview'] == 'The summary written on open'
    assert 'summary_blocked_reason' not in payloads[-1]


@pytest.mark.parametrize('trigger', OWNER, ids=lambda t: t.value)
def test_owner_triggers_generate_a_summary_with_no_derived_effects(monkeypatch, pc, trigger):
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda *_: False)
    spies = _spy_managed_effects(monkeypatch, pc)
    spies['get_structured'].return_value = (Structured(title='Real title', overview='A real summary'), False)
    completed = _stub_completed_for_normal_path(monkeypatch, pc)
    completed.sync_content_revision = 3
    payloads = _capture_all_persists(monkeypatch, pc)
    submitted = MagicMock(side_effect=AssertionError('no derived work for a historical row'))
    monkeypatch.setattr(pc, 'submit_with_context', submitted)
    explicit = MagicMock()
    monkeypatch.setattr(pc, 'complete_explicit', explicit)
    disposition = []

    pc.process_conversation(
        'uid', 'en', _historical(), trigger=trigger, derived_effects_disposition_observer=disposition.append
    )

    spies['get_structured'].assert_called_once()
    for key in ('extract_memories', 'extract_memories_inner', 'trigger_apps', 'assign_folder'):
        spies[key].assert_not_called()
    submitted.assert_not_called()
    assert payloads[-1][pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD] is True
    assert disposition[-1] is pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS
    # The open-time summary settles an outstanding sync hold inside the historical seam.
    explicit.assert_called_once_with('uid', completed, trigger)


def test_an_explicit_template_on_a_historical_row_writes_only_that_result(monkeypatch, pc):
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda *_: False)
    spies = _spy_managed_effects(monkeypatch, pc)
    spies['get_structured'].return_value = (Structured(title='Real title', overview='A real summary'), False)
    completed = _stub_completed_for_normal_path(monkeypatch, pc)
    _capture_all_persists(monkeypatch, pc)
    monkeypatch.setattr(pc, 'submit_with_context', MagicMock(side_effect=AssertionError('no derived work')))
    monkeypatch.setattr(pc, 'complete_explicit', MagicMock())
    update = MagicMock()
    monkeypatch.setattr(pc.conversations_db, 'update_conversation', update)
    app = MagicMock()

    pc.process_conversation(
        'uid', 'en', _historical(), trigger=ProcessingTrigger.USER_REPROCESS, app_id='template', explicit_app=app
    )

    spies['trigger_apps'].assert_called_once()
    assert spies['trigger_apps'].call_args.args[3:5] == ('template', app)
    update.assert_called_once_with('uid', completed.id, {'apps_results': []})
    for key in ('extract_memories', 'extract_memories_inner', 'assign_folder'):
        spies[key].assert_not_called()


def test_a_non_historical_row_still_takes_the_funded_block(monkeypatch, pc):
    _spy_managed_effects(monkeypatch, pc)
    enabled = MagicMock(return_value=False)
    monkeypatch.setattr(pc.funded_processing, 'enabled', enabled)
    _stub_completed_for_normal_path(monkeypatch, pc)
    _capture_all_persists(monkeypatch, pc)
    monkeypatch.setattr(pc, 'submit_with_context', MagicMock())
    pc.process_conversation('uid', 'en', _existing_desktop(), trigger=ProcessingTrigger.SYNC_UPDATE)
    enabled.assert_called()


def test_minimum_without_provenance_has_no_title_marker():
    row = _existing_desktop()
    assert build_deterministic_minimum_structured(row, uid='uid').title_provenance == 'server_minimum'
    assert build_deterministic_minimum_structured(row, uid='uid', provenance=False).title_provenance is None
