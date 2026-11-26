"""Process entry for the chain stages (``discard`` .. ``chat_index``), run once per run.

    python -m testing.pipeline_lab.chain.entry --root ROOT --run RUN_ID [--engine product|fake]

The ``discard`` stage driver starts this in the run's pinned arm (a fresh ``python -I``
against the arm's ``backend/``), so product modules are imported only here, under the lab
environment. With an in-place checkout or in tests the driver calls ``main`` in process.

Inputs, all from the run store: ``corpus/<day>/day.json``, ``start_state/``,
``baseline/raw_conversations.jsonl`` (the day's production rows, lab uid), and, when the
ingest stages ran, ``runs/<id>/ingest/<conversation>.json`` (replayed transcripts replace
the stored ones for conversations whose ingest outcome is ``transcript``).

Env: ``OMI_PIPELINE_LAB_LLM_PROXY_URL`` (the run's proxy), ``OMI_PIPELINE_LAB_OVERLAY_JSON``
(the unredacted overlay; never written to disk), ``OMI_PIPELINE_LAB_EMBEDDER`` (``product``
default, ``fake`` for hermetic runs) and the stack's own variables (``stack/config.py``).

Outputs: ``conversations/*.json``, ``chain.json``, ``day.json`` (contract shape),
``notifications.jsonl``, ``baseline.json`` + ``baseline/conversations/*``, and
``chain_entry.json`` (this summary). Exit 0 when the chain ran (even partially), 2 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from testing.pipeline_lab.contracts import wire_speaker_label

OVERLAY_ENV = 'OMI_PIPELINE_LAB_OVERLAY_JSON'
EMBEDDER_ENV = 'OMI_PIPELINE_LAB_EMBEDDER'
PROXY_ENV = 'OMI_PIPELINE_LAB_LLM_PROXY_URL'


def product_segments(segments: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Contract segments (from ingest) in the product's ``transcript_segments`` shape."""
    out = []
    speakers: dict[str, int] = {}
    for index, segment in enumerate(segments):
        label = str(segment.get('speaker') or 'SPEAKER_00')
        speaker_id = speakers.setdefault(label, len(speakers))
        out.append(
            {
                'id': f'lab-seg-{index}',
                'text': segment.get('text') or '',
                'speaker': wire_speaker_label(speaker_id),
                'speaker_id': speaker_id,
                'is_user': bool(segment.get('is_user')),
                'person_id': None,
                'start': float(segment.get('start') or 0.0),
                'end': float(segment.get('end') or 0.0),
            }
        )
    return out


def apply_ingest(rows: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    """Swap in replayed transcripts where the ingest stage produced one; report what was used."""
    from testing.pipeline_lab.store import read_json

    ingest_dir = run_dir / 'ingest'
    used = {'replayed': 0, 'stored': 0, 'failed': 0}
    if not ingest_dir.is_dir():
        used['stored'] = len(rows)
        return used
    for row in rows:
        result = read_json(ingest_dir / f'{row["id"]}.json')
        if result and result.get('outcome') == 'transcript' and result.get('segments'):
            row['transcript_segments'] = product_segments(result['segments'])
            if result.get('language'):
                row['language'] = result['language']
            used['replayed'] += 1
        else:
            used['stored'] += 1
            if result and result.get('outcome') == 'failed':
                used['failed'] += 1
    return used


def _overlay() -> Any:
    from testing.pipeline_lab.stack.overlay import Overlay

    raw = os.environ.get(OVERLAY_ENV) or '{}'
    return Overlay.from_mapping(json.loads(raw))


def _production_recap_at(store: Any, day_id: str) -> Any:
    summary = store.read_baseline_daily_summary(day_id) or {}
    return summary.get('created_at')


def run(root: Path, run_id: str, engine: str) -> dict[str, Any]:
    import time

    started = time.monotonic()
    from testing.pipeline_lab.baseline.build import build_baseline
    from testing.pipeline_lab.seed.corpus import DayWindow, load_start_state
    from testing.pipeline_lab.stack import LAB_UID
    from testing.pipeline_lab.store import Store, atomic_write_json, ensure_private_dir

    store = Store(
        root=ensure_private_dir(Path(root)), verdicts_root=Path(os.devnull)
    )  # the chain never writes verdicts
    record = store.read_run(run_id)
    day = store.read_day(record.day_id)
    run_dir = store.run_dir(run_id)
    window = DayWindow.of(day.date, day.timezone)
    state = load_start_state(store, day.day_id)
    rows = store.read_baseline(day.day_id, 'raw_conversations.jsonl')
    transcripts = apply_ingest(rows, run_dir)
    proxy_url = os.environ.get(PROXY_ENV) or ''
    if not proxy_url:
        raise RuntimeError('no LLM proxy for this run (pass --llm-upstream or --llm-mode replay)')
    recap_at = _production_recap_at(store, day.day_id)
    if engine == 'fake':
        from testing.pipeline_lab.chain.fake import replay_chain_fake

        result = asyncio.run(
            replay_chain_fake(
                run_dir=run_dir,
                uid=LAB_UID,
                day=day.date,
                tz_name=day.timezone,
                day_start=window.start,
                conversations=rows,
                start_state=state,
                proxy_url=proxy_url,
                production_recap_at=recap_at,
            )
        )
    elif engine == 'product':
        from testing.pipeline_lab.chain.run import ChainRunSpec, replay_chain
        from testing.pipeline_lab.vector.embed import CachedEmbedder, FakeEmbedder, ProductEmbedder
        from testing.pipeline_lab.vector.index import NumericVectorIndex

        if os.environ.get(EMBEDDER_ENV, 'product') == 'fake':
            embedder: Any = FakeEmbedder(int(os.environ.get('OMI_PIPELINE_LAB_EMBED_DIMENSION') or 3072))
        else:
            embedder = CachedEmbedder(ProductEmbedder(), store.root / 'cache' / 'embeddings')
        # One index per run, seeded from the start state: no vectors leak between runs.
        index = NumericVectorIndex.open(run_dir / 'vector_index.json', dimension=embedder.dimension)
        spec = ChainRunSpec(
            run_dir=run_dir,
            day_start=window.start,
            conversations=rows,
            start_state=state,
            overlay=_overlay(),
            embedder=embedder,
            vector_index=index,
            day=day.date,
            tz_name=day.timezone,
            production_recap_at=recap_at,
        )
        result = asyncio.run(replay_chain(spec))
        result['engine'] = 'product'
    else:
        raise ValueError(f'unknown chain engine {engine!r}')
    chain_done = time.monotonic()
    view = build_baseline(run_dir, store.baseline_dir(day.day_id))
    timings = dict(result.get('timings') or {})
    timings['baseline_view'] = round(time.monotonic() - chain_done, 3)
    timings['entry_total'] = round(time.monotonic() - started, 3)
    summary = {
        'engine': engine,
        'clock': result.get('clock'),
        'late_monotonic_reads': result.get('late_monotonic_reads'),
        'transcripts': transcripts,
        'chain': (result.get('chain') or {}).get('summary'),
        'day': result.get('day'),
        'notifications': result.get('notifications'),
        'network_refusals': len(result.get('network_refusals') or []),
        'baseline_counts': view.get('counts'),
        'seed': {k: (result.get('seed') or {}).get(k) for k in ('written', 'skipped', 'cleared', 'timings')},
        'warnings': list((result.get('seed') or {}).get('warnings') or []),
        'timings': timings,
    }
    atomic_write_json(run_dir / 'chain_entry.json', summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.chain.entry')
    parser.add_argument('--root', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--engine', choices=('product', 'fake'), default='product')
    args = parser.parse_args(argv)
    from testing.pipeline_lab.store import private_tempdir

    try:
        with private_tempdir(Path(args.root)):  # the product's own temp files stay inside the lab root
            summary = run(Path(args.root), args.run, args.engine)
    except Exception:  # noqa: BLE001 - the traceback goes to chain_errors.log
        trace = traceback.format_exc()
        try:
            from testing.pipeline_lab.store import atomic_write_bytes, safe_segment

            atomic_write_bytes(Path(args.root) / 'runs' / safe_segment(args.run) / 'chain_errors.log', trace.encode())
        except Exception:  # noqa: BLE001
            pass
        print(trace, file=sys.stderr)
        return 2
    print(json.dumps(summary, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
