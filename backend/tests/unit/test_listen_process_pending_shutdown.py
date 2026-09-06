"""Regression: a listen session ending inside the 7s window must still finalize pending work.

LiveConversationController.process_pending defers finalization by 7 seconds, then finalizes the
timed-out conversation and re-dispatches anything still stuck in `processing`. The listen split
turned the original unconditional `await asyncio.sleep(7.0)` into `if await self.host.wait(7):
return`. host.wait is wait_for_event(shutdown_event, seconds), which returns True when woken
early by shutdown, and runtime sets shutdown_event immediately before draining background tasks
without cancelling them. So any session ending inside that window returned early and skipped both
the timed-out conversation's finalization and the processing re-dispatch.

The `if ...: return` form is the polling-loop idiom (lifecycle_loop correctly uses
`if await self.host.wait(5): break`). process_pending is a one-shot deferred action, so an early
wake must shorten the wait, not cancel the work.

Seam: the controller takes only a host, so this subclasses it to record the two finalization
calls and drives the real process_pending. No patching and no sys.modules mutation.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from database import conversations as conversations_db
from database.conversations import select_stale_in_progress
from routers.listen.conversations import LiveConversationController


class _Host:
    """Minimal listen host. wait() returns True to mean 'woken early by shutdown'."""

    def __init__(
        self,
        *,
        woken_by_shutdown: bool,
        processing: list[dict[str, str]],
        stale_in_progress: list[dict[str, str]] | None = None,
        current_conversation_id: str | None = None,
    ) -> None:
        self.request = SimpleNamespace(uid='uid-1')
        self.state = SimpleNamespace(current_conversation_id=current_conversation_id)
        self._woken_by_shutdown = woken_by_shutdown
        self._results_by_function = {
            'get_processing_conversations': processing,
            'get_stale_in_progress_conversations': stale_in_progress or [],
        }
        self.waited: list[float] = []
        self.persistence = SimpleNamespace(call=self._call)

    async def wait(self, seconds: float) -> bool:
        self.waited.append(seconds)
        return self._woken_by_shutdown

    async def _call(self, fn, *_args, **_kwargs):
        return self._results_by_function[fn.__name__]


class _RecordingController(LiveConversationController):
    """Records the finalization calls instead of touching Firestore."""

    def __init__(self, host: _Host) -> None:
        super().__init__(host)
        self.processed: list[str] = []
        self.scheduled: list[str] = []

    async def process_conversation(self, conversation_id: str) -> bool:
        self.processed.append(conversation_id)
        return True

    async def schedule_finalization(self, conversation_id: str) -> bool:
        self.scheduled.append(conversation_id)
        return True


async def test_session_ending_inside_the_window_still_finalizes():
    host = _Host(woken_by_shutdown=True, processing=[{'id': 'conv-processing'}])
    controller = _RecordingController(host)

    await controller.process_pending('conv-timed-out')

    # An early shutdown wake must not drop the pending finalization work.
    assert controller.processed == ['conv-timed-out']
    assert controller.scheduled == ['conv-processing']
    assert host.waited == [7]


async def test_normal_session_finalizes_after_the_full_delay():
    host = _Host(woken_by_shutdown=False, processing=[{'id': 'conv-processing'}])
    controller = _RecordingController(host)

    await controller.process_pending('conv-timed-out')

    assert controller.processed == ['conv-timed-out']
    assert controller.scheduled == ['conv-processing']


async def test_no_timed_out_conversation_still_redispatches_processing():
    host = _Host(woken_by_shutdown=True, processing=[{'id': 'conv-a'}, {'id': 'conv-b'}])
    controller = _RecordingController(host)

    await controller.process_pending(None)

    assert controller.processed == []
    assert controller.scheduled == ['conv-a', 'conv-b']


# ── Stale in_progress recovery (#9809) ──────────────────────────────────────


async def test_process_pending_recovers_stale_in_progress_conversations():
    """Orphaned in_progress rows route through process_conversation, which already
    finalizes content and deletes empty rows — the same call a live timeout makes."""
    host = _Host(
        woken_by_shutdown=False,
        processing=[{'id': 'conv-processing'}],
        stale_in_progress=[{'id': 'conv-orphan-old'}, {'id': 'conv-orphan-newer'}],
    )
    controller = _RecordingController(host)

    await controller.process_pending(None)

    assert controller.scheduled == ['conv-processing']
    assert controller.processed == ['conv-orphan-old', 'conv-orphan-newer']


async def test_recovery_never_touches_the_sessions_current_conversation():
    host = _Host(
        woken_by_shutdown=False,
        processing=[],
        stale_in_progress=[{'id': 'conv-live'}, {'id': 'conv-orphan'}],
        current_conversation_id='conv-live',
    )
    controller = _RecordingController(host)

    await controller.process_pending(None)

    assert controller.processed == ['conv-orphan']


def test_select_stale_in_progress_filters_sorts_and_bounds():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=1)
    conversations = [
        {'id': 'fresh', 'finished_at': now - timedelta(minutes=5)},
        {'id': 'oldest', 'finished_at': now - timedelta(days=120)},
        {'id': 'old', 'finished_at': now - timedelta(days=2)},
        # No trustworthy idle clock — cannot be proven orphaned.
        {'id': 'no-clock'},
        {'id': 'bad-clock', 'finished_at': 'not-a-datetime'},
    ]

    selected = select_stale_in_progress(conversations, cutoff, limit=10)
    assert [c['id'] for c in selected] == ['oldest', 'old']

    bounded = select_stale_in_progress(conversations, cutoff, limit=1)
    assert [c['id'] for c in bounded] == ['oldest']


class _QueryDocument:
    def __init__(self, data: dict):
        self._data = data

    def to_dict(self):
        return self._data


class _StaleRecoveryQuery:
    def __init__(self, documents: list[_QueryDocument]):
        self.documents = documents
        self.ordering = None
        self.limit_value = None

    def where(self, **_kwargs):
        return self

    def order_by(self, field_path, direction):
        self.ordering = (field_path, direction)
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def stream(self):
        return iter(self.documents)


class _StaleRecoveryClient:
    def __init__(self, query: _StaleRecoveryQuery):
        self.query = query

    def collection(self, _name):
        return _StaleRecoveryUserRef(self.query)


class _StaleRecoveryUserRef:
    def __init__(self, query: _StaleRecoveryQuery):
        self.query = query

    def document(self, _uid):
        return self

    def collection(self, _name):
        return self.query


def test_stale_recovery_queries_oldest_rows_before_bounding_the_read():
    now = datetime.now(timezone.utc)
    query = _StaleRecoveryQuery(
        [
            _QueryDocument({'id': 'oldest', 'finished_at': now - timedelta(days=2)}),
            _QueryDocument({'id': 'old', 'finished_at': now - timedelta(hours=2)}),
        ]
    )
    client = _StaleRecoveryClient(query)

    selected = conversations_db.get_stale_in_progress_conversations(
        'uid-1',
        older_than_seconds=3600,
        limit=1,
        firestore_client=client,
    )

    assert [conversation['id'] for conversation in selected] == ['oldest']
    assert query.ordering[0] == 'finished_at'
    assert query.limit_value == 1


# ── Custom-STT marker on session resume (#7690) ─────────────────────────────


class _ResumeHost:
    """Minimal host for create_new_in_progress_conversation's resume branch."""

    def __init__(self, *, existing_conversation: dict | None, use_custom_stt: bool) -> None:
        self.request = SimpleNamespace(uid='uid-1', source='omi')
        self.client_device_context = SimpleNamespace(client_device_id='dev-1', platform='desktop')
        self.language = 'en'
        self.use_custom_stt = use_custom_stt
        self.client_conversation_id = None
        self.recording_session_id = 'session-1'
        self.is_multi_channel = False
        self.state = SimpleNamespace(current_conversation_id=None)
        self.recording_session_ids_by_conversation = {}
        self.persistence = SimpleNamespace(call=self._call)
        self.calls: list[tuple] = []
        self._existing = existing_conversation

    async def _call(self, fn, *_args, **_kwargs):
        self.calls.append((fn.__name__, _args, _kwargs))
        if fn.__name__ == 'open_live_recording_session':
            return {'requires_rollover': False, 'conversation_id': 'conv-1'}
        if fn.__name__ == 'get_conversation':
            return self._existing
        if fn.__name__ == 'set_in_progress_conversation_id':
            return None
        if fn.__name__ == 'update_conversation':
            return None
        return None


class _ResumeController(LiveConversationController):
    def __init__(self, host: _ResumeHost) -> None:
        super().__init__(host)
        self.session_events: list[str] = []

    def send_conversation_session(self, *args, **kwargs) -> None:
        self.session_events.append('sent')


async def test_resume_persists_custom_stt_marker_when_session_uses_custom_stt():
    """A conversation that started under normal STT but resumes under custom STT
    must get the durable uses_custom_stt marker, or its custom-STT provenance is
    lost for metering and the fair-use lane (#7690)."""
    host = _ResumeHost(
        existing_conversation={'id': 'conv-1', 'status': 'in_progress', 'discarded': False, 'uses_custom_stt': False},
        use_custom_stt=True,
    )
    controller = _ResumeController(host)

    await controller.create_new_in_progress_conversation()

    updates = [c for c in host.calls if c[0] == 'update_conversation']
    assert len(updates) == 1, f'expected one update_conversation call, got {host.calls}'
    assert updates[0][1][2] == {'uses_custom_stt': True}, f'wrong update payload: {updates[0]}'


async def test_resume_does_not_rewrite_marker_for_normal_stt_session():
    """A normal-STT resume of a normal-STT conversation must not write anything."""
    host = _ResumeHost(
        existing_conversation={'id': 'conv-1', 'status': 'in_progress', 'discarded': False, 'uses_custom_stt': False},
        use_custom_stt=False,
    )
    controller = _ResumeController(host)

    await controller.create_new_in_progress_conversation()

    updates = [c for c in host.calls if c[0] == 'update_conversation']
    assert updates == [], f'unexpected update_conversation call: {host.calls}'


# ── Skip the guaranteed-miss existence read for server-generated ids ────────
#
# `users/{uid}/conversations/{id}` is the single largest slice of prod
# single-document reads (38.3%), and a fresh server-generated id can never
# already have a document under it. See conversation-existence-read.


class _CreateConversationHost:
    """Host for create_new_in_progress_conversation covering the existence-read
    skip (a server-generated id can't already have a document) and the
    lifecycle-snapshot reuse (open_live_recording_session already read the
    document once while resolving the binding)."""

    def __init__(
        self,
        *,
        client_conversation_id: str | None = None,
        existing_conversation: dict | None = None,
        conversation_snapshot: dict | None = None,
        conversation_snapshot_known: bool = False,
        binding_conversation_id: str | None = None,
    ) -> None:
        self.request = SimpleNamespace(
            uid='uid-1', source='omi', call_id=None, conversation_role=None, geolocation=None
        )
        self.client_device_context = SimpleNamespace(client_device_id='dev-1', platform='desktop')
        self.language = 'en'
        self.use_custom_stt = False
        self.private_cloud_sync_enabled = False
        self.client_conversation_id = client_conversation_id
        self.recording_session_id = 'session-1'
        self.is_multi_channel = False
        self.state = SimpleNamespace(current_conversation_id=None)
        self.recording_session_ids_by_conversation = {}
        self.persistence = SimpleNamespace(call=self._call)
        self.calls: list[tuple] = []
        self._existing = existing_conversation
        self._conversation_snapshot = conversation_snapshot
        self._conversation_snapshot_known = conversation_snapshot_known
        self._binding_conversation_id_override = binding_conversation_id

    async def _call(self, fn, *args, **kwargs):
        self.calls.append((fn.__name__, args, kwargs))
        if fn.__name__ == 'open_live_recording_session':
            proposed_id = args[2]
            conversation_id = self._binding_conversation_id_override or proposed_id
            binding = {'requires_rollover': False, 'conversation_id': conversation_id}
            if self._conversation_snapshot_known:
                binding['conversation_snapshot'] = self._conversation_snapshot
                binding['conversation_snapshot_known'] = True
            return binding
        if fn.__name__ == 'get_conversation':
            return self._existing
        if fn.__name__ in ('set_in_progress_conversation_id', 'update_conversation', 'create_in_progress_conversation'):
            return None
        return None


class _CreateConversationController(LiveConversationController):
    def __init__(self, host: _CreateConversationHost) -> None:
        super().__init__(host)
        self.session_events: list[str] = []

    def send_conversation_session(self, *args, **kwargs) -> None:
        self.session_events.append('sent')


async def test_fresh_server_generated_id_skips_the_existence_read():
    """No client_conversation_id: proposed_id is a freshly minted uuid4 and the
    binding adopts it verbatim, so get_conversation for that id is a guaranteed
    NOT_FOUND and must not be called."""
    host = _CreateConversationHost(client_conversation_id=None)
    controller = _CreateConversationController(host)

    await controller.create_new_in_progress_conversation()

    get_conversation_calls = [c for c in host.calls if c[0] == 'get_conversation']
    assert get_conversation_calls == [], f'unexpected get_conversation call(s): {get_conversation_calls}'
    create_calls = [c for c in host.calls if c[0] == 'create_in_progress_conversation']
    assert len(create_calls) == 1, f'expected the new-conversation path to run, got {host.calls}'
    assert host.state.current_conversation_id is not None


async def test_rollover_generation_skips_the_existence_read():
    """rollover=True always mints a fresh server-generated id even when a
    client_conversation_id is present (silence/status rollovers must not reuse
    or mutate the prior binding), so the existence read must still be skipped."""
    host = _CreateConversationHost(client_conversation_id='client-supplied-id')
    controller = _CreateConversationController(host)

    await controller.create_new_in_progress_conversation(rollover=True)

    get_conversation_calls = [c for c in host.calls if c[0] == 'get_conversation']
    assert get_conversation_calls == [], f'unexpected get_conversation call(s): {get_conversation_calls}'
    open_calls = [c for c in host.calls if c[0] == 'open_live_recording_session']
    assert len(open_calls) == 1
    proposed_id = open_calls[0][1][2]
    assert proposed_id != 'client-supplied-id', 'rollover must not reuse the client-supplied id as proposed_id'


async def test_resume_with_client_id_naming_existing_conversation_still_reads_it():
    """A client-supplied id can legitimately name an existing conversation
    (resume/idempotency), so the existence read is load-bearing here and must
    not be skipped; the same reconnect action must still be taken."""
    host = _CreateConversationHost(
        client_conversation_id='conv-1',
        existing_conversation={'id': 'conv-1', 'status': 'in_progress', 'discarded': False},
    )
    controller = _CreateConversationController(host)

    await controller.create_new_in_progress_conversation()

    get_conversation_calls = [c for c in host.calls if c[0] == 'get_conversation']
    assert len(get_conversation_calls) == 1, f'expected one get_conversation call, got {host.calls}'
    assert get_conversation_calls[0][1][1] == 'conv-1'
    assert host.state.current_conversation_id == 'conv-1'
    assert controller.session_events == ['sent']
    create_calls = [c for c in host.calls if c[0] == 'create_in_progress_conversation']
    assert create_calls == [], 'a resumed conversation must not be recreated'


async def test_resume_with_client_id_naming_missing_conversation_behaves_as_before():
    """A client-supplied id naming no existing conversation must still be
    looked up (it is not server-generated) and then fall through to the normal
    new-conversation creation path, exactly as before this change."""
    host = _CreateConversationHost(client_conversation_id='conv-missing', existing_conversation=None)
    controller = _CreateConversationController(host)

    await controller.create_new_in_progress_conversation()

    get_conversation_calls = [c for c in host.calls if c[0] == 'get_conversation']
    assert len(get_conversation_calls) == 1, f'expected one get_conversation call, got {host.calls}'
    assert get_conversation_calls[0][1][1] == 'conv-missing'
    create_calls = [c for c in host.calls if c[0] == 'create_in_progress_conversation']
    assert len(create_calls) == 1
    assert create_calls[0][2].get('idempotent') is True
    assert host.state.current_conversation_id == 'conv-missing'
