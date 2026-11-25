"""Process entry for a v3 day (the chain stages ``discard`` .. ``chat_index`` under conversations v3).

    python -m testing.pipeline_lab.v3.entry --root ROOT --run RUN_ID [--engine product|fake]

Started by the chain stage driver when the run's pipeline is ``v3`` (``v3/select.py``), in the
run's pinned arm or the in-place checkout, exactly like ``chain/entry.py``.

Inputs (run store): ``corpus/<day>/day.json``, ``start_state/``, ``v3/recordings.jsonl`` (the
day's recordings, lab uid) and ``baseline/v3_conversations.jsonl`` (production's v3
conversations, contract shape). Overlay ``model_config.v3`` tunes the replay:
``{"arrival": "production"|"finish", "arrival_lag_seconds": 60, "tail_hours": 2, "sweeps": true,
"partial_step_seconds": 60, "partial_lag_seconds": 60, "clock": "sim"|"tick"}``. ``partial_step_seconds: 0``
turns partial updates off (each recording then lands whole at its arrival, as before 2026-11-19).
``clock`` picks the replay clock (``v3/run.py``); ``sim`` is the default.

Outputs: see ``v3/run.py``; then ``baseline.json`` against production's v3 conversations and
``chain_entry.json`` (this summary). Exit 0 when the day ran (even partially), 2 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional, Sequence

from testing.pipeline_lab.chain.entry import EMBEDDER_ENV, PROXY_ENV, _overlay, _production_recap_at

V3_BASELINE = 'v3_conversations.jsonl'


def v3_options(overlay: Any) -> dict[str, Any]:
    raw = dict((overlay.model_config or {}).get('v3') or {})
    return {
        'arrival_mode': str(raw.get('arrival') or 'production'),
        'arrival_lag': timedelta(seconds=float(raw.get('arrival_lag_seconds', 60))),
        'tail': timedelta(hours=float(raw.get('tail_hours', 2))),
        'sweeps': bool(raw.get('sweeps', True)),
        'partial_step': (
            timedelta(seconds=float(raw.get('partial_step_seconds', 60)))
            if float(raw.get('partial_step_seconds', 60)) > 0
            else None
        ),
        'partial_lag': timedelta(seconds=float(raw.get('partial_lag_seconds', 60))),
        'max_events': int(raw.get('max_events', 20000)),
        'clock': str(raw.get('clock') or 'sim'),
    }


def drop_start_conversations(state: Any, prefixes: Any) -> int:
    """Leave start-state rows whose id starts with a listed prefix out of the seed (``exclude_start_ids``).

    For A/B runs blocked by one source both arms share, e.g. a recording already near Firestore's 1 MiB
    document limit (every pass that touches it fails, and the owner stops building).
    """
    wanted = tuple(str(p) for p in prefixes or () if str(p))
    if not wanted:
        return 0
    before = len(state.conversations)
    state.conversations = [row for row in state.conversations if not str(row.get('id') or '').startswith(wanted)]
    return before - len(state.conversations)


def run(root: Path, run_id: str, engine: str) -> dict[str, Any]:
    from testing.pipeline_lab.baseline.build import build_baseline
    from testing.pipeline_lab.seed.corpus import DayWindow, load_start_state
    from testing.pipeline_lab.store import Store, atomic_write_json, ensure_private_dir, read_jsonl
    from testing.pipeline_lab.v3.corpus import read_day_recordings

    store = Store(root=ensure_private_dir(Path(root)), verdicts_root=Path(os.devnull))
    record = store.read_run(run_id)
    day = store.read_day(record.day_id)
    run_dir = store.run_dir(run_id)
    window = DayWindow.of(day.date, day.timezone)
    recordings = read_day_recordings(store, day.day_id)
    production = list(read_jsonl(store.baseline_dir(day.day_id) / V3_BASELINE))
    proxy_url = os.environ.get(PROXY_ENV) or ''
    if not proxy_url:
        raise RuntimeError('no LLM proxy for this run (pass --llm-upstream or --llm-mode replay)')
    overlay = _overlay()
    options = v3_options(overlay)
    if engine == 'fake':
        from testing.pipeline_lab.v3.fake import replay_v3_fake

        options.pop('clock')  # the fake engine's clock is already simulated (v3/fake.py)
        result = replay_v3_fake(
            run_dir=run_dir, recordings=recordings, production=production, proxy_url=proxy_url, **options
        )
    elif engine == 'product':
        from testing.pipeline_lab.v3.run import V3RunSpec, replay_v3
        from testing.pipeline_lab.vector.embed import CachedEmbedder, FakeEmbedder, ProductEmbedder
        from testing.pipeline_lab.vector.index import NumericVectorIndex

        if os.environ.get(EMBEDDER_ENV, 'product') == 'fake':
            embedder: Any = FakeEmbedder(int(os.environ.get('OMI_PIPELINE_LAB_EMBED_DIMENSION') or 3072))
        else:
            embedder = CachedEmbedder(ProductEmbedder(), store.root / 'cache' / 'embeddings')
        index = NumericVectorIndex.open(run_dir / 'vector_index.json', dimension=embedder.dimension)
        start_state = load_start_state(store, day.day_id)
        excluded = ((overlay.model_config or {}).get('v3') or {}).get('exclude_start_ids')
        if dropped := drop_start_conversations(start_state, excluded):
            print(
                f'v3: left {dropped} start-state row(s) out of the seed ({len(excluded)} prefix(es))', file=sys.stderr
            )
        spec = V3RunSpec(
            run_dir=run_dir,
            day_start=window.start,
            day_end=window.end,
            recordings=recordings,
            production=production,
            start_state=start_state,
            overlay=overlay,
            embedder=embedder,
            vector_index=index,
            day=day.date,
            tz_name=day.timezone,
            production_recap_at=_production_recap_at(store, day.day_id),
            **options,
        )
        result = asyncio.run(replay_v3(spec))
        failed = getattr(embedder, 'failed', 0)
        if failed:
            result.setdefault('warnings', []).append(
                f'embeddings: {failed} text(s) refused by the provider even alone; placeholder vectors used'
            )
    else:
        raise ValueError(f'unknown v3 engine {engine!r}')
    view = build_baseline(run_dir, store.baseline_dir(day.day_id), conversations_file=V3_BASELINE)
    summary = {
        'engine': engine,
        'pipeline': 'v3',
        'transcripts': {'stored': len(recordings), 'replayed': 0},
        'plan': result.get('plan'),
        'admission': result.get('admission'),
        'driver': result.get('driver'),
        'conversations': result.get('conversations'),
        'day': result.get('day'),
        'notifications': result.get('notifications'),
        'network_refusals': len(result.get('network_refusals') or []),
        'baseline_counts': view.get('counts'),
        'timings': result.get('timings'),
        'seed': {k: (result.get('seed') or {}).get(k) for k in ('written', 'skipped', 'cleared', 'timings')},
        'warnings': result.get('warnings') or [],
    }
    atomic_write_json(run_dir / 'chain_entry.json', summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.v3.entry')
    parser.add_argument('--root', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--engine', choices=('product', 'fake'), default='product')
    args = parser.parse_args(argv)
    try:
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
