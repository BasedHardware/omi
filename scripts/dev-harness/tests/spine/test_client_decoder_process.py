"""C10 real subprocess oracle; no backend, Flutter app, or external network."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dev_harness import client_compat as compat
from .pending import pending


@pending('C10')
def test_real_frozen_decoder_executes_its_logic_and_rejects_bad_input(tmp_path):
    path = 'contracts/client-compat/releases/synthetic/decoder.dart'
    file = tmp_path / path
    file.parent.mkdir(parents=True)
    file.write_text('''import 'dart:convert';
import 'dart:io';
Future<void> main() async {
  final request = jsonDecode(await stdin.transform(utf8.decoder).join());
  if (request['status'] != 200) throw StateError('HTTP status');
  final value = jsonDecode(utf8.decode(base64Decode(request['body_base64'])));
  final String id = value['id'];
  final int count = value['count'] ?? 17;
  print(jsonEncode({'id': id.split('').reversed.join(), 'count': count * 3}));
}
''')
    (tmp_path / 'contracts/client-compat/catalog.json').write_text(json.dumps({'releases': [
        {'id': 'synthetic', 'decoder': path, 'files': {path: hashlib.sha256(file.read_bytes()).hexdigest()}}]}))
    # No execute injection: a hardcoded id, JSON echo, or transport-only fake fails.
    for body, expected in [(b'{"id":"alpha"}', {'id': 'ahpla', 'count': 51}),
                           (b'{"id":"beta","count":4}', {'id': 'ateb', 'count': 12})]:
        assert compat.decode_released(tmp_path, path, compat.Response(200, {}, body)) == expected
    for status, body in [(503, b'{"id":"alpha"}'), (200, b''), (200, b'{"id":7}'),
                         (200, b'{"id":"alpha","count":"4"}')]:
        with pytest.raises(ValueError):
            compat.decode_released(tmp_path, path, compat.Response(status, {}, body))


@pending('C10')
def test_admitted_extractions_have_original_flutter_equivalence_evidence():
    root = Path(__file__).resolve().parents[4]
    rows = json.loads((root / 'contracts/client-compat/catalog.json').read_text())['releases']
    assert rows, 'capture admission is separate from synthetic engine acceptance'
    for row in rows:
        path = row['decoder_equivalence']
        raw = (root / path).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row['files'][path]
        proof = json.loads(raw)
        assert proof['source_files'] == row['source_files']
        assert proof['decoder_sha256'] == row['files'][row['decoder']]
        assert proof['flutter_sdk'] and proof['command'].startswith('flutter test ')
        vectors = proof['vectors']
        assert {v['case'] for v in vectors} >= {'happy', 'missing', 'null', 'wrong_type', 'enum', 'date', 'default'}
        assert any(v['original']['ok'] for v in vectors)
        assert any(not v['original']['ok'] for v in vectors)
        for vector in vectors:
            assert vector['input']
            assert vector['original'] == vector['extracted']
            assert set(vector['original']) == {'ok', 'value'}
