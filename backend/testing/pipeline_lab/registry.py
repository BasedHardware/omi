"""Stage-driver and tool registry that other lanes plug into.

A lane exposes ``testing/pipeline_lab/<its dir>/plugin.py`` with::

    def register(registry):
        registry.add_stage(MyNotesDriver())          # a StageDriver, one per stage
        registry.add_tool('corpus-add-day', add_day)  # a CLI command engine

``load_plugins`` imports every known lane plugin that exists (a missing module
is skipped; a plugin that fails to import is an error, never hidden), plus any
extra module named in ``$OMI_PIPELINE_LAB_PLUGINS`` (comma separated).

Tool names the CLI routes to a registered engine: ``corpus-add-day``,
``record-stt``, ``serve``, ``sample-run``. A tool is called as
``tool(ToolContext) -> dict | int``.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, Protocol, Sequence, runtime_checkable

from testing.pipeline_lab.contracts import STAGES

if TYPE_CHECKING:  # pragma: no cover
    from testing.pipeline_lab.orchestrator import StageContext
    from testing.pipeline_lab.store import Store

PLUGINS_ENV = 'OMI_PIPELINE_LAB_PLUGINS'
LANE_DIRS = (
    'stack',
    'seed',
    'vector',
    'sinks',
    'chain',
    'day',
    'baseline',
    'timeline',
    'cassette',
    'lanes',
    'streaming',
    'inspector',
)
KNOWN_TOOLS = ('corpus-add-day', 'record-stt', 'serve', 'sample-run')


class DriverNotRegistered(LookupError):
    def __init__(self, kind: str, names: Sequence[str]):
        self.names = list(names)
        super().__init__(
            f'{kind} not registered: {", ".join(names)} '
            f'(lanes register them in testing/pipeline_lab/<dir>/plugin.py: register(registry))'
        )


@dataclass
class StageResult:
    """What a driver returns. ``output`` is a small JSON manifest (cached, hashed as the next stage's input)."""

    output: dict[str, Any] = field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class StageDriver(Protocol):
    """A stage engine. Optional attributes: ``schema_version`` (int, default 1),
    ``cacheable`` (bool, default True: False for drivers whose effect cannot be
    restored from stored run files), ``inputs(ctx) -> {name: hash}`` (extra
    cache-key inputs), ``restore(ctx, output)`` (after the orchestrator writes the
    stored artifacts back), ``unit`` (str: stages sharing one execute and cache
    together), ``scoped_code`` (bool: key on the files the stage runs, per
    ``affected``, not the whole backend tree), ``key_overlay(overlay) -> (overlay,
    model_config)`` (the part of the overlay the stage reads) and
    ``attribute_call(llm_call_row) -> stage | None`` (LLM call attribution inside a unit)."""

    stage: str

    def run(self, ctx: 'StageContext') -> StageResult: ...


@dataclass
class ToolContext:
    store: 'Store'
    args: Any  # argparse.Namespace
    argv: list[str]  # arguments after the command, passed through untouched
    as_json: bool = False


class Registry:
    def __init__(self) -> None:
        self.stages: dict[str, StageDriver] = {}
        self.tools: dict[str, Callable[[ToolContext], Any]] = {}
        self.plugins: list[str] = []

    def add_stage(self, driver: StageDriver) -> None:
        stage = getattr(driver, 'stage', None)
        if stage not in STAGES:
            raise ValueError(f'driver declares unknown stage {stage!r}')
        if stage in self.stages:
            raise ValueError(f'stage {stage} already has a driver')
        self.stages[stage] = driver

    def add_tool(self, name: str, tool: Callable[[ToolContext], Any]) -> None:
        if name in self.tools:
            raise ValueError(f'tool {name} already registered')
        self.tools[name] = tool

    def stage(self, name: str) -> StageDriver:
        if name not in self.stages:
            raise DriverNotRegistered('stage driver', [name])
        return self.stages[name]

    def tool(self, name: str) -> Callable[[ToolContext], Any]:
        if name not in self.tools:
            raise DriverNotRegistered('tool', [name])
        return self.tools[name]

    def missing(self, stages: Sequence[str]) -> list[str]:
        return [stage for stage in stages if stage not in self.stages]

    def describe(self) -> dict[str, Any]:
        return {
            'plugins': list(self.plugins),
            'stages': {stage: type(self.stages[stage]).__name__ if stage in self.stages else None for stage in STAGES},
            'tools': {name: name in self.tools for name in sorted(set(KNOWN_TOOLS) | set(self.tools))},
        }


def plugin_modules(env: Optional[Mapping[str, str]] = None) -> list[str]:
    env = os.environ if env is None else env
    modules = [f'testing.pipeline_lab.{name}.plugin' for name in LANE_DIRS]
    modules += [name.strip() for name in (env.get(PLUGINS_ENV) or '').split(',') if name.strip()]
    return modules


def load_plugins(registry: Registry, modules: Optional[Sequence[str]] = None) -> Registry:
    for name in modules if modules is not None else plugin_modules():
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as error:
            # Skip only when the plugin module itself (or its lane package) is absent.
            if error.name and (name == error.name or name.startswith(error.name + '.')):
                continue
            raise
        register = getattr(module, 'register', None)
        if register is None:
            raise ValueError(f'plugin {name} has no register(registry)')
        register(registry)
        registry.plugins.append(name)
    return registry
