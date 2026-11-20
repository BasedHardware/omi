"""Local-stack smoke for the chain lane: synthetic snapshot -> real Firestore emulator.

Exercises the parts unit tests cannot: the product database helpers the seeder writes
through, the reads the exporter uses, the guarded reset, and vector seeding through
``database.vector_db`` with the lab index (owner routing state lives in Firestore too).
No LLM, no network beyond the emulator; Redis is fakeredis. Synthetic data only.

    firebase emulators:exec --only firestore --project demo-omi-local \\
      'python -m testing.pipeline_lab.stack.smoke'

Prints one JSON report. Exits non-zero when any check fails.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def main() -> int:
    from contextlib import ExitStack

    import fakeredis

    from testing.pipeline_lab.chain.driver import ProductChainStore
    from testing.pipeline_lab.seed.snapshot import SnapshotReader
    from testing.pipeline_lab.seed.start_state import build_start_state
    from testing.pipeline_lab.seed.synthetic import write_synthetic_snapshot
    from testing.pipeline_lab.seed.writer import ProductSeedWriter, reset_lab_user, seed_start_state
    from testing.pipeline_lab.stack.config import LabStackConfig
    from testing.pipeline_lab.stack.env import lab_environment
    from testing.pipeline_lab.stack.overlay import Overlay
    from testing.pipeline_lab.vector import install_vector_index
    from testing.pipeline_lab.vector.embed import FakeEmbedder, install_embeddings
    from testing.pipeline_lab.vector.index import NumericVectorIndex
    from testing.pipeline_lab.vector.seed import apply_with_product, plan_vectors

    report: dict = {'checks': {}, 'errors': {}}
    root = Path(tempfile.mkdtemp(prefix='plab-smoke-'))
    config = LabStackConfig.from_env({**os.environ, 'OMI_PIPELINE_LAB_ROOT': str(root)})
    state = build_start_state(
        SnapshotReader(write_synthetic_snapshot(root / 'snap')),
        datetime(2026, 3, 14, tzinfo=timezone.utc),
        day_date='2026-03-14',
    )
    errors: dict[str, list[str]] = {}

    def on_error(kind: str, error: Exception) -> None:
        errors.setdefault(kind, []).append(f'{type(error).__name__}: {str(error)[:200]}')

    with lab_environment(
        config,
        Overlay(name='smoke'),
        run_dir=root / 'run',
        redis_client=fakeredis.FakeRedis(),
        preimport=('database.vector_db', 'database.conversations', 'database.action_items', 'database.memories'),
    ) as env, ExitStack() as stack:
        index = NumericVectorIndex(64)
        install_vector_index(stack, index)
        install_embeddings(stack, FakeEmbedder(64))
        writer = ProductSeedWriter(env.firestore, on_error=on_error)
        seeded = seed_start_state(state, writer, reset=lambda: reset_lab_user(env.firestore, config.uid))
        report['seed'] = seeded['written']
        report['errors']['seed'] = errors
        store = ProductChainStore()
        checks = report['checks']
        for row in state.conversations:
            back = store.read_conversation(config.uid, row['id'])
            checks.setdefault('conversation_read_back', []).append(
                bool(back) and len(back.get('transcript_segments') or []) == len(row['transcript_segments'])
            )
        checks['action_items_by_conversation'] = len(store.action_items_for(config.uid, state.conversations[0]['id']))
        checks['memories_by_conversation'] = len(store.memories_for(config.uid, state.conversations[0]['id']))
        checks['people'] = len(store.people_names(config.uid))
        records, vector_report = plan_vectors(
            config.uid, conversations=state.conversations, memories=state.memories, action_items=state.action_items
        )
        try:
            apply_with_product(records, config.uid, vector_report)
        except Exception as error:  # noqa: BLE001
            report['errors']['vectors'] = f'{type(error).__name__}: {str(error)[:200]}'
        report['vectors'] = vector_report.as_dict()
        report['index_namespaces'] = index.namespaces()
        from database import vector_db

        report['dedup_hits'] = vector_db.find_similar_action_items(config.uid, 'order heirloom tomato seeds')
        report['decisions'] = len(env.decisions.rows)
        report['network_refusals'] = env.network.refusals
    ok = (
        all(report['checks'].get('conversation_read_back') or [False])
        and not report['errors'].get('seed')
        and not report['errors'].get('vectors')
        and bool(report['dedup_hits'])
    )
    report['ok'] = ok
    print(json.dumps(report, indent=1, default=str))
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
