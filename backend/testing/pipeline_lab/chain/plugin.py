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

Cacheable as one unit (``unit = 'chain'``): the orchestrator keys the eight stages together on
the corpus day (everything but audio), the upstream stages' outputs and stored artifacts (the
replayed transcripts), the engine and embedder, the whole backend tree, overlay and model config;
it stores every run file the composite wrote (conversations, chain.json, day.json, notifications,
baseline view, vector index) and restores them on a hit. The emulator state is not restored: no
lab stage reads it after the chain. ``--from-stage`` anywhere inside the unit re-runs the unit.

Why one unit: ``discard`` .. ``goals`` run inside one ``process_conversation`` per conversation,
serially, each conversation reading what earlier ones wrote (memories, action items, goals, the
vector index); ``daily_summary`` and ``chat_index`` run after the day in the same process, on the
emulator, clock, capture sinks and vector index the conversations left. Splitting them needs a
stored emulator snapshot (Firestore export + vector index + sinks), which the lab does not take.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Optional

from testing.pipeline_lab import keys
from testing.pipeline_lab.registry import StageResult
from testing.pipeline_lab.store import read_json, read_jsonl

CHAIN_STAGES = ('discard', 'notes', 'memories', 'tasks', 'notifications', 'goals', 'daily_summary', 'chat_index')
ENTRY_MODULE = 'testing.pipeline_lab.chain.entry'
UNIT = 'chain'
# Process env the chain entry reads that can change its output (``chain/entry.py``).
OUTPUT_ENV = ('OMI_PIPELINE_LAB_EMBEDDER', 'OMI_PIPELINE_LAB_EMBED_DIMENSION')
# LLM call attribution inside the composite: the proxy's stage tag, then the product feature header.
CALL_STAGE = {'open_loops': 'daily_summary', 'finalize': 'discard'}
FEATURE_STAGE = {
    'conv_discard': 'discard',
    'conv_structure': 'notes',
    'conversation_processing': 'notes',
    'conv_folder': 'notes',
    'memories': 'memories',
    'goals': 'goals',
    'daily_summary': 'daily_summary',
    'open_loop_daily': 'daily_summary',
}


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


def attribute_call(row: Mapping[str, Any]) -> Optional[str]:
    """The chain stage an LLM call row belongs to (None: the stage that was executing)."""
    feature = str(row.get('feature') or '')
    if feature in FEATURE_STAGE:
        return FEATURE_STAGE[feature]
    tag = str(row.get('stage') or '')
    if tag in CHAIN_STAGES:
        return tag
    return CALL_STAGE.get(tag)


class ChainStage:
    cacheable = True
    unit = UNIT
    schema_version = 1

    def __init__(self, stage: str, composite: ChainComposite):
        self.stage = stage
        self.composite = composite

    def inputs(self, ctx: Any) -> dict[str, str]:
        return {
            'corpus': keys.hash_dir(ctx.store.day_dir(ctx.day.day_id), skip=('audio',)),
            'engine': str(ctx.engine),
            'env': keys.hash_json({name: os.environ.get(name) for name in OUTPUT_ENV}),
            'typesense': str(bool(os.environ.get('OMI_PIPELINE_LAB_TYPESENSE'))),
        }

    def attribute_call(self, row: Mapping[str, Any]) -> Optional[str]:
        return attribute_call(row)

    def restore(self, ctx: Any, output: dict[str, Any]) -> None:
        ctx.run_extra.update(output.get('run_extra') or {})

    def run(self, ctx: Any) -> StageResult:
        self.composite.ensure(ctx)
        output, warnings = stage_summary(self.stage, ctx.run_dir)
        if self.stage == CHAIN_STAGES[0]:
            output['run_extra'] = {
                k: ctx.run_extra[k] for k in ('pipeline', 'pipeline_reason', 'stt') if k in ctx.run_extra
            }
        return StageResult(output=output, warnings=warnings)


def register(registry: Any) -> None:
    composite = ChainComposite()
    for stage in CHAIN_STAGES:
        registry.add_stage(ChainStage(stage, composite))
