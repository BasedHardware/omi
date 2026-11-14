"""Budget the existing two-unit admit → commit → projection emulator proof."""

import pytest

from testing.firestore_read_budget import assert_read_budget, delta_reads, snapshot_reads
from tests.integration.test_batch_pipeline_intake_firestore import (
    test_accepted_upload_drains_after_rollback_with_encrypted_context_and_accounting as existing_batch_flow,
)
from utils.batch_pipeline import pump as pump_module
from utils.sync.legacy_dark import LegacySyncMode
from utils.sync import legacy_dark

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_batch_unit_end_to_end_read_budget(tmp_path, monkeypatch):
    # The current proof covers the primary unit and one late-capture unit. Keep
    # its full regression flow unchanged and normalize the measured delta by 2.
    accepted_units = 2
    # This proof targets batch admission, not the legacy fallback now selected
    # by the default legacy_sync=on rollout mode.
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: LegacySyncMode.DRAINING)
    # Production batch offline admission defaults on. Exercise the synthetic
    # worker's post-decode, pre-ASR recheck and include its Firestore reads.
    monkeypatch.setattr(pump_module, 'cap_dispatch_enabled', lambda *args: True)
    before = snapshot_reads()
    await existing_batch_flow(tmp_path, monkeypatch)
    delta = delta_reads(before)

    assert delta.reads > 0, 'read-budget harness bug: batch flow recorded zero Firestore reads'
    reads_per_unit = delta.reads / accepted_units
    print(
        f'batch_unit_end_to_end: measured={reads_per_unit:g} reads/batch_unit '
        f'(total={delta.reads:g}, accepted_units={accepted_units})'
    )
    assert_read_budget('batch_unit_end_to_end', reads_per_unit, delta)
