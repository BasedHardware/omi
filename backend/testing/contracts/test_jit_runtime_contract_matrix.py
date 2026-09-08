"""Backend runtime leg of the shared additive JIT client contract matrix."""

from __future__ import annotations

import json
import logging
import sys
import types
from importlib import util as importlib_util
from pathlib import Path
from unittest.mock import Mock, patch

from models.chat import ChatEvidenceEnvelope
from models.memories import MemoryDB

FIXTURE = Path(__file__).resolve().parents[3] / 'contracts' / 'parity' / 'jit_runtime_contract_matrix.json'


def _matrix() -> dict:
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def _standalone_mcp_server(monkeypatch):
    """Load the real standalone transport without installing its protocol host."""
    mcp_package = types.ModuleType('mcp')
    mcp_package.__path__ = []
    mcp_server = types.ModuleType('mcp.server')
    mcp_server.Server = object
    mcp_stdio = types.ModuleType('mcp.server.stdio')
    mcp_stdio.stdio_server = None
    mcp_types = types.ModuleType('mcp.types')
    mcp_types.TextContent = object
    mcp_types.Tool = object
    monkeypatch.setitem(sys.modules, 'mcp', mcp_package)
    monkeypatch.setitem(sys.modules, 'mcp.server', mcp_server)
    monkeypatch.setitem(sys.modules, 'mcp.server.stdio', mcp_stdio)
    monkeypatch.setitem(sys.modules, 'mcp.types', mcp_types)
    source = FIXTURE.parents[2] / 'mcp' / 'src' / 'mcp_server_omi' / 'server.py'
    spec = importlib_util.spec_from_file_location('_jit_contract_mcp_server', source)
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backend_models_accept_mixed_client_versions_without_losing_text():
    matrix = _matrix()
    rows = [MemoryDB.model_validate(row) for row in matrix['memory_rows']]

    assert [row.id for row in rows] == matrix['expected']['memory_ids']
    assert {row.id: row.content for row in rows} == matrix['expected']['readable_text_by_id']
    assert [row.id for row in rows if row.ledger_schema_version == 'knowledge_ledger.v1'] == matrix['expected'][
        'authoritative_ledger_ids'
    ]


def test_backend_evidence_model_keeps_legacy_optional_and_quarantines_future_semantics():
    matrix = _matrix()
    records = matrix['chat_records']

    assert 'evidence' not in records['legacy']
    current = ChatEvidenceEnvelope.model_validate(records['v1']['evidence'])
    future = ChatEvidenceEnvelope.model_validate(records['future']['evidence'])

    assert current.references[0].kind == matrix['expected']['v1_evidence_kind']
    assert future.references[0].kind == matrix['expected']['future_evidence_kind']
    assert future.references[0].state == matrix['expected']['future_evidence_state']
    assert records['legacy']['text'] and records['v1']['text'] and records['future']['text']


def test_standalone_mcp_transport_preserves_the_mixed_version_response(monkeypatch):
    matrix = _matrix()
    server = _standalone_mcp_server(monkeypatch)
    response = Mock()
    response.json.return_value = matrix['memory_rows']

    with patch.object(server.requests, 'get', return_value=response) as request:
        rows = server.get_memories(logging.getLogger(__name__), 'omi_mcp_contract', limit=3)

    assert [row['id'] for row in rows] == matrix['expected']['memory_ids']
    assert {row['id']: row['content'] for row in rows} == matrix['expected']['readable_text_by_id']
    assert [row['id'] for row in rows if row.get('ledger_schema_version') == 'knowledge_ledger.v1'] == matrix[
        'expected'
    ]['authoritative_ledger_ids']
    request.assert_called_once()
    assert request.call_args.kwargs['params'] == {'offset': 0, 'limit': 3}
    assert request.call_args.kwargs['headers'] == {'Authorization': 'Bearer omi_mcp_contract'}
