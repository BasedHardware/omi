import asyncio
import json
from types import SimpleNamespace

from routers.listen.receiver import ListenReceiver
from utils.translation_demand import DemandPolicy, TranslationDemand


class LegacyTelemetry:
    def observe(self, _payload):
        return False  # Simulates the old 2,000-report lifetime cap.


class Transcripts:
    def __init__(self):
        self.changes = 0

    async def on_translation_demand_changed(self):
        self.changes += 1


def test_existing_client_state_drives_independent_admission_after_telemetry_cap(monkeypatch):
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'true')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_UID_ALLOWLIST', 'u')
    now = [0.0]

    async def run():
        receiver = ListenReceiver.__new__(ListenReceiver)
        transcripts = Transcripts()
        spawned = []

        def spawn(coro, name):
            task = asyncio.create_task(coro, name=name)
            spawned.append(task)
            return task

        receiver.host = SimpleNamespace(
            state=SimpleNamespace(realtime_demand=LegacyTelemetry()),
            transcripts=transcripts,
            client_device_context=SimpleNamespace(platform='ios'),
            spawn=spawn,
        )
        receiver.translation_demand = TranslationDemand(lambda: now[0])
        receiver._translation_expiry_task = None
        await receiver._handle_text(
            json.dumps({'type': 'client_state', 'foreground': True, 'transcript_visible': True})
        )
        await asyncio.sleep(0)
        assert receiver.translation_demand.snapshot(lease_v1_enabled=False).policy == DemandPolicy.viewed
        assert transcripts.changes == 1
        receiver._translation_expiry_task.cancel()
        await asyncio.gather(*spawned, return_exceptions=True)

    asyncio.run(run())


def test_flag_off_report_does_not_start_translation_work(monkeypatch):
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'false')
    monkeypatch.setenv('TRANSLATION_DEMAND_SHADOW_ENABLED', 'false')

    async def run():
        receiver = ListenReceiver.__new__(ListenReceiver)
        transcripts = Transcripts()
        receiver.host = SimpleNamespace(
            state=SimpleNamespace(realtime_demand=LegacyTelemetry()), transcripts=transcripts
        )
        receiver.translation_demand = TranslationDemand(lambda: 0)
        receiver._translation_expiry_task = None
        await receiver._handle_text(
            json.dumps({'type': 'client_state', 'foreground': True, 'transcript_visible': False})
        )
        assert transcripts.changes == 0
        assert receiver._translation_expiry_task is None
        assert receiver.translation_demand.snapshot(lease_v1_enabled=False).policy == DemandPolicy.legacy_unknown

    asyncio.run(run())
