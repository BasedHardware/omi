"""Projection receipts stay import-pure and never retain transcript payloads."""

import ast
from collections import OrderedDict
from pathlib import Path
import subprocess
import sys

import pytest

from utils.episodes import transcript_receipts as receipts

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def queue(monkeypatch):
    monkeypatch.setattr(receipts, '_pending', OrderedDict())
    monkeypatch.setattr(receipts, '_dropped', 0)


def test_projection_receipt_import_graph_excludes_composer_and_provider_stacks():
    # Cover imports inside functions too: a lazy composer import was the original regression.
    tree = ast.parse((BACKEND / 'utils/batch_pipeline/projection.py').read_text())
    episode_edges = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('utils.episodes')
    ]
    assert len(episode_edges) == 1
    assert episode_edges[0].module == 'utils.episodes'
    assert [alias.name for alias in episode_edges[0].names] == ['transcript_receipts']
    tree = ast.parse(Path(receipts.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module.split('.')[0] in sys.stdlib_module_names
        elif isinstance(node, ast.Import):
            assert all(alias.name.split('.')[0] in sys.stdlib_module_names for alias in node.names)

    result = subprocess.run(
        [
            sys.executable,
            '-c',
            '''
import importlib.abc, sys
class DenyHeavy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        assert not fullname.startswith(('utils.episodes.composer', 'utils.memory', 'database.vector_db', 'utils.llm.clients')), fullname
sys.meta_path.insert(0, DenyHeavy())
from utils.batch_pipeline import projection
assert projection.transcript_receipts.enqueue('synthetic-owner', {'id': 'capture', 'transcript_segments': [{'text': 'Speech.'}]})
assert projection.transcript_receipts.take() == [('synthetic-owner', 'capture', None)]
''',
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_receipts_coalesce_ids_and_rollovers_without_retaining_content():
    client = object()
    assert receipts.enqueue('u', {'id': 'a', 'transcript_segments': object()}, firestore_client=client)
    assert receipts.enqueue(
        'u', {'id': 'a', '_sync_size_rollover_rows': [({'id': 'b'}, None)]}, firestore_client=client
    )
    assert len(receipts._pending) == 2
    assert receipts.take(1) == [('u', 'a', client)]
    assert receipts.take() == [('u', 'b', client)]
    assert receipts.take() == []


def test_receipt_overflow_is_bounded_and_observable(monkeypatch, caplog):
    monkeypatch.setattr(receipts, 'MAX_PENDING', 1)
    assert receipts.enqueue('u', {'id': 'a'})
    assert not receipts.enqueue('u', {'id': 'b'})
    assert receipts.enqueue('u', {'id': 'a'})
    assert receipts.take() == [('u', 'a', None)]
    assert receipts.take_dropped() == 1
    assert receipts.take_dropped() == 0
    assert 'capacity_full' in caplog.text
