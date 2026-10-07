import pytest

from utils.retrieval import agentic


class _AttemptSpy:
    instances = []

    def __init__(self, journey, client_kind):
        self.journey = journey
        self.client_kind = client_kind
        self.outcome = None
        self.issue_class = None
        self.__class__.instances.append(self)

    def succeed(self):
        self.outcome = 'success'

    def degrade(self, issue_class):
        self.outcome = 'degraded'
        self.issue_class = issue_class

    def fail(self, issue_class):
        self.outcome = 'failure'
        self.issue_class = issue_class

    def cancel(self):
        self.outcome = 'cancelled'


class _MemoryTool:
    def __init__(self, result):
        self.result = result

    async def ainvoke(self, _tool_input, *, config):
        assert config['configurable']['client_kind'] == 'mobile_android'
        return self.result


class _FailingMemoryTool:
    async def ainvoke(self, _tool_input, *, config):
        assert config['configurable']['client_kind'] == 'mobile_android'
        raise RuntimeError('memory store unavailable')


def _install_attempt_spy(monkeypatch):
    _AttemptSpy.instances = []
    monkeypatch.setattr(agentic, 'ClientJourneyAttempt', _AttemptSpy)


@pytest.mark.asyncio
async def test_memory_retrieval_records_success_when_context_is_returned(monkeypatch):
    _install_attempt_spy(monkeypatch)
    result = await agentic._execute_tool(
        'search_memories_tool',
        {'query': 'coffee'},
        {'search_memories_tool': _MemoryTool('Found 1 memories matching coffee:\n- Likes coffee')},
        {'client_kind': 'mobile_android'},
    )

    assert 'Likes coffee' in result
    attempt = _AttemptSpy.instances[0]
    assert (attempt.journey, attempt.client_kind, attempt.outcome) == (
        'memory_retrieval',
        'mobile_android',
        'success',
    )
    assert attempt.issue_class is None


@pytest.mark.asyncio
async def test_memory_retrieval_records_empty_expected_context_as_degraded(monkeypatch):
    _install_attempt_spy(monkeypatch)
    result = await agentic._execute_tool(
        'get_memories_tool',
        {},
        {'get_memories_tool': _MemoryTool('No memories found. The user has no recorded facts yet.')},
        {'client_kind': 'mobile_android'},
    )

    assert result.startswith('No memories found')
    attempt = _AttemptSpy.instances[0]
    assert (attempt.journey, attempt.client_kind, attempt.outcome) == (
        'memory_retrieval',
        'mobile_android',
        'degraded',
    )
    assert attempt.issue_class == 'empty_answer'


@pytest.mark.asyncio
async def test_memory_retrieval_records_dependency_failure_when_the_tool_raises(monkeypatch):
    _install_attempt_spy(monkeypatch)

    with pytest.raises(RuntimeError, match='memory store unavailable'):
        await agentic._execute_tool(
            'search_memories_tool',
            {'query': 'coffee'},
            {'search_memories_tool': _FailingMemoryTool()},
            {'client_kind': 'mobile_android'},
        )

    attempt = _AttemptSpy.instances[0]
    assert (attempt.journey, attempt.client_kind, attempt.outcome) == (
        'memory_retrieval',
        'mobile_android',
        'failure',
    )
    assert attempt.issue_class == 'dependency_unavailable'


def _journey_sample(name, labels):
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value(name, labels) or 0


def _accepted_labels(client_kind):
    return {'journey': 'conversation_finalization', 'client_kind': client_kind, 'app_build': 'unknown'}


def _terminal_labels(client_kind, outcome):
    return {**_accepted_labels(client_kind), 'outcome': outcome}


def _journeys_stubbed() -> bool:
    import sys

    import utils.observability as obs

    if not getattr(obs, '__path__', None):
        return True
    journeys = sys.modules.get('utils.observability.journeys')
    if journeys is None:
        return True
    # A stub harness ModuleType exposes only the attributes its file set;
    # the real module exposes the full contract. Probe two names from
    # different consumers.
    if not hasattr(journeys, 'record_journey_accepted') or not hasattr(journeys, 'ClientJourneyAttempt'):
        return True
    return False


def _run_sync_reprocess(monkeypatch, row, conversation, processed):
    from unittest.mock import MagicMock

    if _journeys_stubbed():
        pytest.skip(
            'utils.observability.journeys is stubbed in this worker (the '
            'sync_v2 behavioral harness shares the process), so the sync '
            'journey counters cannot be observed'
        )
    from utils.sync import pipeline

    monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', lambda *_args, **_kwargs: row)
    monkeypatch.setattr(pipeline, 'deserialize_conversation', lambda _data: conversation)
    monkeypatch.setattr(pipeline, 'process_conversation', MagicMock(return_value=processed))
    monkeypatch.setattr(pipeline, 'submit_with_context', MagicMock())
    pipeline._reprocess_conversation_after_update('uid-1', row['id'], 'en')


def test_sync_visible_conversation_accepts_conversation_finalization_once(monkeypatch):
    from types import SimpleNamespace

    row = {'id': 'conv-visible', 'status': 'completed', 'sync_relevance': 'keep'}
    conversation = SimpleNamespace(discarded=False, client_platform='ios', source='omi', language='en')
    processed = SimpleNamespace(discarded=False)
    before_accepted = _journey_sample('omi_client_journey_accepted_total', _accepted_labels('mobile_ios'))
    before_success = _journey_sample('omi_client_journey_terminal_total', _terminal_labels('mobile_ios', 'success'))

    _run_sync_reprocess(monkeypatch, row, conversation, processed)

    assert _journey_sample('omi_client_journey_accepted_total', _accepted_labels('mobile_ios')) == before_accepted + 1
    assert (
        _journey_sample('omi_client_journey_terminal_total', _terminal_labels('mobile_ios', 'success'))
        == before_success + 1
    )

    row['relevance_decision'] = {'trigger': 'sync_update', 'verdict': 'keep'}
    _run_sync_reprocess(monkeypatch, row, conversation, processed)

    assert _journey_sample('omi_client_journey_accepted_total', _accepted_labels('mobile_ios')) == before_accepted + 1
    assert (
        _journey_sample('omi_client_journey_terminal_total', _terminal_labels('mobile_ios', 'success'))
        == before_success + 1
    )


def test_sync_discarded_conversation_terminals_cancelled_without_accept(monkeypatch):
    from types import SimpleNamespace

    row = {'id': 'conv-discarded', 'status': 'completed', 'sync_relevance': 'keep'}
    conversation = SimpleNamespace(discarded=False, client_platform='android', source='omi', language='en')
    processed = SimpleNamespace(discarded=True)
    before_accepted = _journey_sample('omi_client_journey_accepted_total', _accepted_labels('mobile_android'))
    before_cancelled = _journey_sample(
        'omi_client_journey_terminal_total', _terminal_labels('mobile_android', 'cancelled')
    )

    _run_sync_reprocess(monkeypatch, row, conversation, processed)

    assert _journey_sample('omi_client_journey_accepted_total', _accepted_labels('mobile_android')) == before_accepted
    assert (
        _journey_sample('omi_client_journey_terminal_total', _terminal_labels('mobile_android', 'cancelled'))
        == before_cancelled + 1
    )

    row['relevance_decision'] = {'trigger': 'sync_update', 'verdict': 'discard'}
    conversation.discarded = True
    _run_sync_reprocess(monkeypatch, row, conversation, processed)

    assert _journey_sample('omi_client_journey_accepted_total', _accepted_labels('mobile_android')) == before_accepted
    assert (
        _journey_sample('omi_client_journey_terminal_total', _terminal_labels('mobile_android', 'cancelled'))
        == before_cancelled + 1
    )


def test_sync_discarded_to_visible_promotion_accepts_once(monkeypatch):
    from types import SimpleNamespace

    row = {
        'id': 'conv-promoted',
        'status': 'completed',
        'sync_relevance': 'keep',
        'relevance_decision': {'trigger': 'sync_update', 'verdict': 'discard'},
    }
    conversation = SimpleNamespace(discarded=True, client_platform='ios', source='omi', language='en')
    processed = SimpleNamespace(discarded=False)
    before_accepted = _journey_sample('omi_client_journey_accepted_total', _accepted_labels('mobile_ios'))
    before_success = _journey_sample('omi_client_journey_terminal_total', _terminal_labels('mobile_ios', 'success'))

    _run_sync_reprocess(monkeypatch, row, conversation, processed)

    assert _journey_sample('omi_client_journey_accepted_total', _accepted_labels('mobile_ios')) == before_accepted + 1
    assert (
        _journey_sample('omi_client_journey_terminal_total', _terminal_labels('mobile_ios', 'success'))
        == before_success + 1
    )
