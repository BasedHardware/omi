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
