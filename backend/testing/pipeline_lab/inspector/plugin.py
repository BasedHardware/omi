"""Inspector registration: the ``serve`` and ``sample-run`` tools."""

from __future__ import annotations

from typing import Any

from testing.pipeline_lab.registry import ToolContext


def serve(ctx: ToolContext) -> int:
    from testing.pipeline_lab.inspector.server import main

    argv = ['--root', str(ctx.store.root), '--verdicts', str(ctx.store.verdicts_root)]
    if getattr(ctx.args, 'port', None) is not None:
        argv += ['--port', str(ctx.args.port)]
    return main(argv + list(ctx.argv))


def sample_run(ctx: ToolContext) -> dict[str, Any]:
    """The synthetic Lumen Bay day and two runs. Sample verdicts only with ``--with-verdicts``
    (they would otherwise land in the real verdict record)."""
    from testing.pipeline_lab.inspector.sample_run import write_sample

    with_verdicts = '--with-verdicts' in ctx.argv
    return write_sample(ctx.store.root, ctx.store.verdicts_root if with_verdicts else None)


def register(registry: Any) -> None:
    registry.add_tool('serve', serve)
    registry.add_tool('sample-run', sample_run)
