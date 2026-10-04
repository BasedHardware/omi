"""Full legacy writer traces with refresh enabled/disabled versus the original call boundary."""

import pytest

from tests.unit import test_action_item_identity_reprocess as legacy
from utils.conversations import process_conversation as pc
from utils.conversations.action_item_refresh import preserve
from utils.conversations.processing_trigger import ProcessingTrigger as Trigger


@pytest.mark.parametrize(
    'trigger,flag,first',
    [
        (Trigger.USER_REPROCESS, 'true', False),
        (Trigger.SERVER_RECOVERY, 'true', False),
        (Trigger.CAPTURE_END, 'true', False),
        (Trigger.SMART_MERGE, 'false', False),
        (Trigger.SYNC_UPDATE, 'false', False),
        (Trigger.SMART_MERGE, 'misspelled', False),
        (Trigger.SMART_MERGE, 'true', True),
        (Trigger.SYNC_UPDATE, 'true', True),
    ],
)
def test_full_writer_effects_equal_legacy(monkeypatch, trigger, flag, first):
    def trace(enabled):
        with monkeypatch.context() as patch:
            world = legacy.World(patch)
            patch.setenv('ACTION_ITEM_REFRESH_PRESERVE_ENABLED', flag)
            patch.setattr(pc, 'preserve_refresh_tasks', preserve if enabled else lambda *a: False)
            if first:
                # Real no-prior-row decision is separately exercised against the transactional store.
                patch.setattr('utils.conversations.action_item_refresh.refresh_db.reconcile', lambda *a, **k: None)
            else:
                world.process('conv-1', [legacy._item(legacy.BUDGET, legacy.DUE)])
            pc._write_action_items(
                legacy.UID,
                legacy._conversation('conv-1', [legacy._item(legacy.BUDGET, legacy.DUE), legacy._item(legacy.VENUE)]),
                trigger,
            )
            return legacy._scrub(
                (world.events, world.reminders, world.external, world.creates, world.store.docs, world.store.events)
            )

    assert trace(True) == trace(False)
