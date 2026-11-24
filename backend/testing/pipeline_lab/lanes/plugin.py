"""Ingest-lane registration: ``ingest``, ``transcribe``, ``boundaries``, ``speakers`` and ``record-stt``.

- ``ingest`` builds ``corpus/<day>/timeline.json`` when it is missing (islands, unknown gaps,
  lane per conversation) and reports coverage.
- ``transcribe`` plays STT cassettes through the lane drivers (record/batch and sync; streaming
  captures through the sync driver as a labelled stand-in, RULINGS 14). The cassettes to play
  are the overlay's ``model_config.stt``: ``{adapter, provider, model, language, vocabulary,
  sync_mode}``. Without that block, or without audio, the chain keeps the stored production
  transcripts (RULINGS 16) and the run says so. It never records: a missing cassette is a
  ``cassette_miss`` for that conversation, which then also keeps its stored transcript.
- ``boundaries`` and ``speakers`` are production's own in M1 (taken from the stored rows); the
  stages report that rather than pretend to replay them.

All four are uncacheable: their effect is files under the run, and each is cheap.
"""

from __future__ import annotations

from typing import Any

from testing.pipeline_lab.registry import StageResult, ToolContext
from testing.pipeline_lab.store import read_json

REPLAY_MODULE = 'testing.pipeline_lab.lanes.__main__'


def stt_config(overlay: dict[str, Any]) -> dict[str, Any]:
    stt = dict((overlay.get('model_config') or {}).get('stt') or {})
    if stt.get('adapter') == 'parakeet_batch':
        stt.setdefault('provider', 'parakeet')
        stt.setdefault('model', 'parakeet-batch')
    return stt


def stt_label(stt: dict[str, Any]) -> str:
    return f'{stt.get("adapter") or "prerecorded"} {stt.get("provider")}/{stt.get("model")}'


def _timeline(ctx: Any) -> dict[str, Any]:
    from testing.pipeline_lab.timeline.build import build_day_timeline

    path = ctx.store.day_dir(ctx.day.day_id) / 'timeline.json'
    return read_json(path) or build_day_timeline(ctx.day.day_id, root=ctx.store.root)


class _Stage:
    cacheable = False
    schema_version = 1
    stage = ''


class IngestStage(_Stage):
    stage = 'ingest'

    def run(self, ctx: Any) -> StageResult:
        timeline = _timeline(ctx)
        coverage = timeline.get('coverage') or {}
        warnings = []
        if not coverage.get('with_audio'):
            warnings.append('no audio in the corpus day: transcripts come from production')
        return StageResult(
            output={'coverage': coverage, 'evaluable_boundaries': timeline.get('evaluable_boundaries')},
            warnings=warnings,
        )


class TranscribeStage(_Stage):
    stage = 'transcribe'

    def run(self, ctx: Any) -> StageResult:
        stt = stt_config(ctx.overlay)
        coverage = _timeline(ctx).get('coverage') or {}
        if not stt.get('provider') or not stt.get('model'):
            ctx.run_extra['stt'] = 'stored production transcripts'
            return StageResult(
                output={'source': 'stored', 'reason': 'no model_config.stt in the overlay'},
                warnings=['no STT selection in the overlay: the chain uses the stored production transcripts'],
            )
        if not coverage.get('with_audio'):
            ctx.run_extra['stt'] = 'stored production transcripts'
            return StageResult(output={'source': 'stored', 'reason': 'no audio'}, warnings=['no audio to replay'])
        ctx.env['OMI_PIPELINE_LAB_ROOT'] = str(ctx.store.root)
        args = [
            'replay',
            '--day',
            ctx.day.day_id,
            '--run',
            ctx.run_id,
            '--provider',
            str(stt['provider']),
            '--model',
            str(stt['model']),
            '--sync-mode',
            str(stt.get('sync_mode') or 'span'),
            '--streaming-via',
            str(stt.get('streaming_via') or 'sync'),
        ]
        if stt.get('language'):
            args += ['--language', str(stt['language'])]
        if stt.get('vocabulary'):
            args += ['--vocabulary', ','.join(stt['vocabulary'])]
        code = ctx.run_module(REPLAY_MODULE, args)
        if code != 0:
            raise RuntimeError(f'transcribe replay exited {code}')
        index = read_json(ctx.run_dir / 'ingest' / 'index.json') or {}
        outcomes: dict[str, int] = {}
        for row in index.get('conversations') or []:
            outcomes[row.get('outcome')] = outcomes.get(row.get('outcome'), 0) + 1
        ctx.run_extra['stt'] = stt_label(stt)
        warnings = []
        if outcomes.get('failed'):
            warnings.append(
                f'{outcomes["failed"]} conversations kept their stored transcript (no cassette or no audio)'
            )
        return StageResult(output={'source': 'cassette', 'stt': stt, 'outcomes': outcomes}, warnings=warnings)


class ProductionOwnedStage(_Stage):
    """M1: production's boundaries and speakers are kept; say so in the run."""

    def __init__(self, stage: str):
        self.stage = stage

    def run(self, ctx: Any) -> StageResult:
        timeline = _timeline(ctx)
        return StageResult(
            output={
                'source': 'production',
                'conversations': len(timeline.get('conversations') or []),
                'evaluable_boundaries': timeline.get('evaluable_boundaries'),
            }
        )


def record_stt(ctx: ToolContext) -> int:
    import os
    from unittest import mock

    from testing.pipeline_lab.lanes.__main__ import main

    with mock.patch.dict(os.environ, {'OMI_PIPELINE_LAB_ROOT': str(ctx.store.root)}):
        return main(['record-stt', *ctx.argv])


def register(registry: Any) -> None:
    registry.add_stage(IngestStage())
    registry.add_stage(TranscribeStage())
    registry.add_stage(ProductionOwnedStage('boundaries'))
    registry.add_stage(ProductionOwnedStage('speakers'))
    registry.add_tool('record-stt', record_stt)
