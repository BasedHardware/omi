"""Chain-lane registration: one composite execution reported as eight stages (RULINGS 16).

Production runs discard, notes, memories, tasks, notifications and goals inside one
``process_conversation`` per conversation, and the daily summary and chat index after the
day, so the lab cannot run them as separate passes without changing what it measures. The
first chain stage a run reaches executes ``chain.entry`` once (in the pinned arm, or in
process for in-place and test runs); every chain stage then reports its own status and
counts from the files that execution wrote.

Under conversations v3 (``v3/select.py``: the overlay turns v3 on and the corpus day has v3
recordings, or ``model_config.pipeline`` says so) the same composite runs ``v3.entry``
instead: recordings feed the real v3 builder, and these stages report on its conversations.

Not cacheable: the effect is emulator state plus run files. Re-running is cheap because
unchanged LLM calls are served from the proxy cache (DESIGN L6).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from testing.pipeline_lab.registry import StageResult
from testing.pipeline_lab.store import read_json, read_jsonl

CHAIN_STAGES = ('discard', 'notes', 'memories', 'tasks', 'notifications', 'goals', 'daily_summary', 'chat_index')
ENTRY_MODULE = 'testing.pipeline_lab.chain.entry'


class ChainFailed(RuntimeError):
    pass


def _conversations(run_dir: Path) -> list[dict[str, Any]]:
    return [read_json(path) for path in sorted((run_dir / 'conversations').glob('*.json'))]


def stage_summary(stage: str, run_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """What one chain stage produced, read back from the run files."""
    conversations = _conversations(run_dir)
    kept = [c for c in conversations if not c.get('discarded')]
    day = read_json(run_dir / 'day.json') or {}
    chain = read_json(run_dir / 'chain.json') or {}
    warnings: list[str] = []
    if stage == 'discard':
        failed = [c for c in chain.get('conversations') or [] if c.get('status') == 'failed']
        if failed:
            warnings.append(
                f'{len(failed)} of {len(chain.get("conversations") or [])} conversations failed to finalize'
            )
        entry = read_json(run_dir / 'chain_entry.json') or {}
        out = {
            'conversations': len(conversations),
            'discarded': len(conversations) - len(kept),
            'failed': len(failed),
            'engine': entry.get('engine'),
            'pipeline': entry.get('pipeline', 'classic'),
            'transcripts': entry.get('transcripts'),
        }
        if entry.get('timings'):
            out['timings'] = entry['timings']
        warnings.extend(str(w) for w in entry.get('warnings') or [])
        if entry.get('pipeline') == 'v3':
            out['v3'] = {
                'visible': sum(1 for c in conversations if (c.get('v3') or {}).get('visible')),
                'recordings': (entry.get('plan') or {}).get('arrivals'),
                'driver': (entry.get('driver') or {}).get('counts'),
            }
    elif stage == 'notes':
        titled = sum(1 for c in kept if (c.get('structured') or {}).get('title'))
        out = {'kept': len(kept), 'titled': titled}
        if kept and not titled:
            warnings.append('no kept conversation got a title')
    elif stage == 'memories':
        delta = day.get('memory_delta') or {}
        out = {
            'memories': sum(len(c.get('memories') or []) for c in conversations),
            'delta': {k: len(delta.get(k) or []) for k in ('added', 'updated', 'removed')},
        }
    elif stage == 'tasks':
        out = {'action_items': sum(len(c.get('action_items') or []) for c in conversations)}
    elif stage == 'notifications':
        out = {'would_have_fired': len(read_jsonl(run_dir / 'notifications.jsonl'))}
    elif stage == 'goals':
        goals = day.get('goals') or []
        out = {
            'goals': len(goals),
            'moved': sum(1 for g in goals if g.get('progress_before') != g.get('progress_after')),
        }
    elif stage == 'daily_summary':
        recap = day.get('recap') or {}
        out = {'status': recap.get('status'), 'at': recap.get('at'), 'present': bool(day.get('daily_summary'))}
        if recap.get('status') not in (None, 'ok'):
            warnings.append(f'daily summary {recap.get("status")}: {recap.get("error")}')
    elif stage == 'chat_index':
        index = day.get('chat_index') or {}
        out = {'checked': index.get('checked', True), 'ready': index.get('ready')}
        if index.get('ready') is False:
            warnings.append('chat index is missing conversations of the day')
    else:  # pragma: no cover - registry rejects unknown stages
        raise ValueError(stage)
    return out, warnings


class ChainComposite:
    """Runs ``chain.entry`` at most once per run id."""

    def __init__(self) -> None:
        self.done: dict[str, dict[str, Any]] = {}

    def ensure(self, ctx: Any) -> dict[str, Any]:
        if ctx.run_id in self.done:
            return self.done[ctx.run_id]
        if not ctx.llm_proxy_url:
            raise ChainFailed('the chain needs the lab LLM proxy: pass --llm-upstream (or --llm-mode replay)')
        ctx.env['OMI_PIPELINE_LAB_OVERLAY_JSON'] = json.dumps(ctx.overlay or {})
        ctx.env['OMI_PIPELINE_LAB_ROOT'] = str(ctx.store.root)
        ctx.env['OMI_PIPELINE_LAB_LLM_PROXY_URL'] = ctx.llm_proxy_url
        from testing.pipeline_lab.v3.corpus import day_has_v3
        from testing.pipeline_lab.v3.select import entry_module, select_pipeline

        pipeline, reason = select_pipeline(ctx.overlay or {}, day_has_v3=day_has_v3(ctx.store, ctx.day.day_id))
        ctx.run_extra['pipeline'] = pipeline
        ctx.run_extra['pipeline_reason'] = reason
        code = ctx.run_module(
            entry_module(pipeline), ['--root', str(ctx.store.root), '--run', ctx.run_id, '--engine', ctx.engine]
        )
        summary = read_json(ctx.run_dir / 'chain_entry.json')
        if code != 0 or summary is None:
            raise ChainFailed(f'chain entry exited {code}; traceback in runs/{ctx.run_id}/chain_errors.log')
        transcripts = summary.get('transcripts') or {}
        if not transcripts.get('replayed'):
            ctx.run_extra.setdefault('stt', 'stored production transcripts')
        self.done[ctx.run_id] = summary
        return summary


class ChainStage:
    cacheable = False
    schema_version = 1

    def __init__(self, stage: str, composite: ChainComposite):
        self.stage = stage
        self.composite = composite

    def run(self, ctx: Any) -> StageResult:
        self.composite.ensure(ctx)
        output, warnings = stage_summary(self.stage, ctx.run_dir)
        return StageResult(output=output, warnings=warnings)


def register(registry: Any) -> None:
    composite = ChainComposite()
    for stage in CHAIN_STAGES:
        registry.add_stage(ChainStage(stage, composite))
