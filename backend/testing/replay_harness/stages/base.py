"""Stage protocol, also used by later replay work packages."""

from typing import Protocol
from testing.replay_harness.manifest import Case
from testing.replay_harness.report import StageResult


class StageDriver(Protocol):
    async def run(self, case: Case, environment) -> StageResult: ...


class NotImplementedStage:
    def __init__(self, name: str):
        self.name = name

    async def run(self, case: Case, environment) -> StageResult:
        return StageResult(self.name, 'not_implemented', reason='not_implemented', guard='not_implemented')
