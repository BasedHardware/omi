"""The `_get_structured` message boundary must not 500 the caller on the background deadline.

Companion to ``test_external_structure_foreground_deadline.py``: drives the REAL
``_get_structured`` coordinator — not the structurers in isolation — along the
``ExternalIntegrationConversationSource.message`` arm the developer
create-from-text endpoint uses, against a provider slower than the background
deadline. This is the exact boundary whose ``except`` mapped the prod timeout to
``conversation_processing_http_exception`` and returned
``HTTPException(500, "Error processing conversation, please try again later")``.

Failure-Class: FC-foreground-call-inherits-background-deadline — guard
surface: restoring the background deadline makes these boundary tests fail with
the prod 500 instead of returning the structured note.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'fake-key-for-hermetic-tests')

from fastapi import HTTPException  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

from models.conversation_enums import (  # noqa: E402
    ExternalIntegrationConversationSource,
)
from testing.import_isolation import (
    AutoMockModule,
    load_module_fresh,
    package_submodule_stubs,
    stub_modules,
)  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[2]

PROVIDER_FIRST_BYTE_SECONDS = 25.0

_MODEL_ANSWER: dict[str, Any] = {
    "title": "Budget Lock-In",
    "overview": "Agreed over message to lock the Q2 budget and send the sheet.",
    "emoji": "🧠",
    "category": "business",
    "sections": [],
    "action_items": [{"description": "Send the landing page copy"}],
    "events": [],
}

_MESSAGE_TEXT = "Message from David: we lock the Q2 budget today and I send the sheet tonight."


def _build_fakes() -> dict[str, ModuleType]:
    """The process_conversation import chain, stubbed the sanctioned way."""
    fakes: dict[str, ModuleType] = {}

    def add(name: str, mod: ModuleType) -> ModuleType:
        fakes[name] = mod
        return mod

    utils_pkg = ModuleType('utils')
    utils_pkg.__path__ = [str(_BACKEND / 'utils')]  # type: ignore[attr-defined]
    add('utils', utils_pkg)
    utils_llm_pkg = ModuleType('utils.llm')
    utils_llm_pkg.__path__ = [str(_BACKEND / 'utils' / 'llm')]  # type: ignore[attr-defined]
    add('utils.llm', utils_llm_pkg)
    utils_conv_pkg = ModuleType('utils.conversations')
    utils_conv_pkg.__path__ = [str(_BACKEND / 'utils' / 'conversations')]  # type: ignore[attr-defined]
    add('utils.conversations', utils_conv_pkg)

    refresh = ModuleType('utils.conversations.action_item_refresh')
    refresh.preserve = lambda *a, **k: False
    add('utils.conversations.action_item_refresh', refresh)

    database_pkg = ModuleType('database')
    database_pkg.__path__ = [str(_BACKEND / 'database')]  # type: ignore[attr-defined]
    add('database', database_pkg)

    client_mod = ModuleType('database._client')
    client_mod.db = MagicMock(name='db')
    client_mod.get_firestore_client = lambda: client_mod.db
    client_mod.get_data_plane_firestore_client = lambda: client_mod.db
    client_mod.document_id_from_seed = lambda seed: 'seed-id'
    client_mod.run_transactional = MagicMock(name='run_transactional')
    client_mod.get_customer_firestore_client = lambda: client_mod.db
    client_mod.data_plane_db = MagicMock(name='data_plane_db')
    # lifecycle (via process_conversation) classifies the retired-transaction
    # 400 through this seam at import time; the availability half of the same
    # classifier rides the same import.
    client_mod.is_expired_transaction_error = lambda error: False
    client_mod.is_transient_availability_error = lambda error: False
    add('database._client', client_mod)

    for name in (
        'database.vector_db',
        'database.apps',
        'database.users',
        'database.screen_activity',
        'database.auth',
        'database.redis_db',
        'database.notifications',
        'database.conversations',
        'database.memories',
        'database.action_items',
        'database.tasks',
        'database.trends',
        'database.folders',
        'database.calendar_meetings',
        'database.short_term_memories',
        'database.review_queue',
        'database.llm_usage',
        'database.entities',
        'database.firestore_read_metrics',
        'database.goals',
    ):
        add(name, AutoMockModule(name))

    users = add('database.users', AutoMockModule('database.users'))
    users.get_user_language_preference = MagicMock(return_value=None)
    users.get_people_by_ids = MagicMock(return_value=[])
    users.get_data_protection_level = MagicMock(return_value='enhanced')
    users.is_byok_active = MagicMock(return_value=False)
    users.get_user_time_zone = MagicMock(return_value=None)

    notification_db = ModuleType('database.notifications')
    notification_db.get_user_time_zone = MagicMock(return_value=None)
    add('database.notifications', notification_db)

    subscription = add('utils.subscription', AutoMockModule('utils.subscription'))
    subscription.is_trial_paywalled = MagicMock(return_value=False)
    subscription.should_defer_desktop_processing = MagicMock(return_value=False)
    subscription.request_has_llm_byok_key = MagicMock(return_value=False)
    subscription.should_skip_omi_paid_postprocessing = MagicMock(return_value=False)

    byok = ModuleType('utils.byok')
    byok.get_byok_key = lambda _provider: None
    byok.has_validated_byok_keys = lambda: False
    byok.has_byok_keys = lambda: False
    add('utils.byok', byok)

    speaker_id = add('utils.speaker_identification', AutoMockModule('utils.speaker_identification'))
    speaker_id.extract_speaker_samples = AsyncMock()

    executors = add('utils.executors', AutoMockModule('utils.executors'))
    executors.db_executor = MagicMock()
    executors.llm_executor = MagicMock()
    executors.postprocess_executor = MagicMock()
    executors.submit_with_context = MagicMock()

    add('utils.llm.memories', AutoMockModule('utils.llm.memories'))
    add('utils.llm.trends', AutoMockModule('utils.llm.trends'))
    add('utils.llm.goals', AutoMockModule('utils.llm.goals'))
    add('utils.llm.chat', AutoMockModule('utils.llm.chat'))
    add('utils.llm.clients', AutoMockModule('utils.llm.clients'))
    add('utils.notifications', AutoMockModule('utils.notifications'))
    add('utils.other.hume', AutoMockModule('utils.other.hume'))
    add('utils.retrieval.rag', AutoMockModule('utils.retrieval.rag'))
    add('utils.webhooks', AutoMockModule('utils.webhooks'))
    add('utils.task_sync', AutoMockModule('utils.task_sync'))
    add('utils.other.storage', AutoMockModule('utils.other.storage'))
    add('utils.metrics', AutoMockModule('utils.metrics'))
    for name, mod in package_submodule_stubs('utils.observability').items():
        add(name, mod)

    add('utils.memory.canonical_activation', AutoMockModule('utils.memory.canonical_activation'))
    add('utils.memory.memory_service', AutoMockModule('utils.memory.memory_service'))
    add('utils.memory.canonical_memory_adapter', AutoMockModule('utils.memory.canonical_memory_adapter'))
    add('utils.memory.decision_path_telemetry', AutoMockModule('utils.memory.decision_path_telemetry'))
    add('utils.memory.rejected_memory_feedback', AutoMockModule('utils.memory.rejected_memory_feedback'))

    task_intelligence = ModuleType('utils.task_intelligence')
    task_intelligence.__path__ = []  # type: ignore[attr-defined]
    add('utils.task_intelligence', task_intelligence)
    capture = AutoMockModule('utils.task_intelligence.conversation_capture')
    capture.capture_enabled = MagicMock(return_value=False)
    add('utils.task_intelligence.conversation_capture', capture)
    task_intelligence.conversation_capture = capture
    add(
        'utils.task_intelligence.workstream_association',
        AutoMockModule('utils.task_intelligence.workstream_association'),
    )
    add('utils.app_integrations', AutoMockModule('utils.app_integrations'))
    add('utils.conversations.location', AutoMockModule('utils.conversations.location'))
    add('utils.conversations.meeting_receipt', AutoMockModule('utils.conversations.meeting_receipt'))
    add('utils.conversations.smart_merge', AutoMockModule('utils.conversations.smart_merge'))
    add('utils.jit_rollout', AutoMockModule('utils.jit_rollout'))
    add('utils.log_sanitizer', AutoMockModule('utils.log_sanitizer'))
    add('utils.retrieval.frame_request_authority', AutoMockModule('utils.retrieval.frame_request_authority'))
    services_pkg = ModuleType('services')
    services_pkg.__path__ = []  # type: ignore[attr-defined]
    add('services', services_pkg)
    add('services.conversation_keyframes', AutoMockModule('services.conversation_keyframes'))

    return fakes


@pytest.fixture(scope='module')
def pc():
    fakes = _build_fakes()
    with stub_modules(fakes):
        module = load_module_fresh(
            'utils.conversations.process_conversation',
            os.path.join(str(_BACKEND), 'utils', 'conversations', 'process_conversation.py'),
        )
        # pc's get_message_structure was bound to whatever
        # utils.llm.external_integrations object existed UNDER the stub set;
        # stub_modules evicts that object at teardown, so the fixture (and the
        # tests) must reach the exact same object through this captured
        # reference, not through a fresh import.
        pc_ext = sys.modules.get('utils.llm.external_integrations')
        # Under the stub set pc_ext's `parser` re-export resolved to the
        # AutoMock utils.llm.clients — give the chain the real pure parser so
        # the model's JSON answer reaches StructuredExtraction.
        from langchain_core.output_parsers import PydanticOutputParser

        from models.structured_extraction import StructuredExtraction

        pc_ext.parser = PydanticOutputParser(pydantic_object=StructuredExtraction)
        module.pc_ext = pc_ext
        yield module


class _DeadlineProvider:
    """get_llm double enforcing the resolved deadline the way the transport does."""

    def __init__(self):
        self.resolved: list = []

    def __call__(self, feature, *args, **kwargs):
        import utils.llm.model_config as model_config

        deadline = kwargs.get('request_timeout')
        if deadline is None:
            deadline = model_config.feature_request_timeout(feature)
        if deadline is None:
            from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

            deadline = DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS
        self.resolved.append((feature, deadline))
        return _Model(deadline, self)


class _Model(RunnableLambda):
    """A real langchain Runnable carrying the resolved deadline.

    ``get_message_structure`` pipes ``prompt | model | parser`` and langchain
    coerces the right-hand operand with ``coerce_to_runnable`` — a plain object
    with ``__or__`` is not enough. Subclassing RunnableLambda keeps the pipe
    shape and the with_structured_output path honest.
    """

    def __init__(self, deadline: float, provider: _DeadlineProvider):
        self._deadline = deadline
        self._provider = provider
        super().__init__(self._run_raw)

    def _run_raw(self, prompt):
        if self._deadline < PROVIDER_FIRST_BYTE_SECONDS:
            raise TimeoutError('Request timed out.')
        return AIMessage(content=json.dumps(_MODEL_ANSWER))

    def with_structured_output(self, schema):
        provider = self._provider
        deadline = self._deadline

        def _run(_prompt):
            if deadline < PROVIDER_FIRST_BYTE_SECONDS:
                raise TimeoutError('Request timed out.')
            return schema.model_validate(_MODEL_ANSWER)

        return RunnableLambda(_run)


@pytest.fixture
def provider(pc):
    """Install the deadline-tracking provider on the module object ``pc``'s
    get_message_structure actually uses — the external_integrations module
    loaded under the same stub set, not a fresh post-teardown import."""
    tracker = _DeadlineProvider()
    original = pc.pc_ext.get_llm
    pc.pc_ext.get_llm = tracker
    yield tracker
    pc.pc_ext.get_llm = original


def _message_conversation():
    from models.conversation import ExternalIntegrationCreateConversation
    from models.conversation_enums import ConversationSource

    return ExternalIntegrationCreateConversation(
        text=_MESSAGE_TEXT,
        text_source=ExternalIntegrationConversationSource.message,
        text_source_spec='slack',
        started_at=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 10, 20, 12, 1, tzinfo=timezone.utc),
        language='en',
        source=ConversationSource.external_integration,
        app_id=None,
    )


def test_message_boundary_structures_under_the_foreground_deadline(pc, provider):
    """The real coordinator message arm structures a whole external message
    under the foreground deadline and returns the note (not the prod 500)."""
    import utils.llm.model_config as model_config

    structured, discarded = pc._get_structured(
        'uid-ext-structure',
        'en',
        _message_conversation(),
    )
    assert discarded is False
    assert structured.title == 'Budget Lock-In'
    assert structured.overview.startswith('Agreed over message to lock the Q2 budget')
    assert provider.resolved == [('external_structure', model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


def test_message_boundary_inherits_the_foreground_deadline_not_a_call_site_override(pc, provider):
    """The coordinator passes no explicit deadline: the 60s budget must arrive
    through the feature route (the deadline is a property of the call)."""
    import utils.llm.model_config as model_config

    pc._get_structured('uid-ext-structure-2', 'en', _message_conversation())
    assert provider.resolved == [('external_structure', model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS)]


def test_background_deadline_on_the_boundary_is_the_prod_500(pc, provider, monkeypatch):
    """Restore the background deadline and the boundary does exactly what prod
    did: TimeoutError -> HTTPException(500, generic detail)."""
    import utils.llm.model_config as model_config
    from utils.llm.gateway_resilience import DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS

    monkeypatch.setattr(model_config, 'FOREGROUND_REQUEST_TIMEOUT_SECONDS', DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)
    with pytest.raises(HTTPException) as excinfo:
        pc._get_structured('uid-ext-structure-3', 'en', _message_conversation())
    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == 'Error processing conversation, please try again later'
    assert provider.resolved == [('external_structure', DEFAULT_GATEWAY_FIRST_BYTE_TIMEOUT_SECONDS)]
