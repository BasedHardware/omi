"""One immutable manifest supplies both advertisement and execution authority."""

from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from utils.messaging.contracts import Principal


@dataclass(frozen=True)
class ToolProjection:
    registry: Mapping[str, Any]
    principal: Principal

    @classmethod
    def build(cls, core, surface, entitled, *, device_names=(), live_devices=False, principal, excluded_names=()):
        registry = {}
        for tool in (*core, *surface, *entitled):
            if tool.name in excluded_names:
                continue
            if tool.name in device_names and not live_devices:
                continue
            if principal.allowed_tools is not None and tool.name not in principal.allowed_tools:
                continue
            if tool.name in registry and registry[tool.name] is not tool:
                raise ValueError('Duplicate tool name: ' + tool.name)
            registry[tool.name] = tool
        return cls(MappingProxyType(registry), principal)

    def authorize(self, uid, name):
        self.principal.authorize(uid, name)
        if name not in self.registry:
            raise PermissionError('Tool not advertised on this surface')
        return self.registry[name]


@dataclass(frozen=True)
class SurfaceRuntime:
    surface: str
    skill: str
    principal: Principal
    tools: tuple[Any, ...] = ()
    evidence: tuple[dict, ...] = ()
    link_id: str | None = None
    session_id: str | None = None
    guard: Any = None
    persist: Any = None
    write_reports: list[str] | None = None
    withhold_private_memories: bool = False


surface_runtime: ContextVar[SurfaceRuntime | None] = ContextVar('messaging_surface', default=None)


def project_runtime_tools(runtime, core, device, entitled, device_names):
    return ToolProjection.build(
        core,
        (*runtime.tools, *device),
        entitled,
        device_names=device_names,
        live_devices=runtime.surface == 'app',
        principal=runtime.principal,
        excluded_names=() if runtime.surface == 'app' else ('create_chart_tool',),
    )
