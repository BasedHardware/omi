#!/usr/bin/env python3
"""Run a small Dart VM check against generated app-client wire DTOs.

This intentionally avoids Flutter and package resolution: the generated wire
files only use core Dart APIs, so a temporary script can import them directly.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MESSAGES_WIRE = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'messages_wire.g.dart'


def main() -> int:
    dart = shutil.which('dart')
    if dart is None:
        print('dart executable not found on PATH')
        return 1

    source = f"""
import {MESSAGES_WIRE.as_uri()!r};

void expectValue(bool condition, String message) {{
  if (!condition) {{
    throw StateError(message);
  }}
}}

void expectFormatException(void Function() callback, String messagePart) {{
  try {{
    callback();
  }} on FormatException catch (error) {{
    expectValue(error.message.contains(messagePart), 'expected FormatException containing "$messagePart", got "$error"');
    return;
  }}
  throw StateError('expected FormatException containing "$messagePart"');
}}

Map<String, dynamic> responseMessageJson() => {{
  'id': 'message-1',
  'created_at': '2026-07-02T12:00:00Z',
  'sender': 'ai',
  'text': 'hello',
  'type': 'text',
}};

void main() {{
  final defaulted = GeneratedResponseMessage.fromJson(responseMessageJson());
  expectValue(defaulted.askForNps == false, 'absent nullable default should use schema default');
  expectValue(
    GeneratedResponseMessage(
      askForNps: null,
      createdAt: DateTime.parse('2026-07-02T12:00:00Z'),
      id: 'message-constructor',
      sender: 'ai',
      text: 'hello',
      type: 'text',
    ).askForNps == null,
    'explicit constructor null should remain null',
  );

  final explicitNull = responseMessageJson()..['ask_for_nps'] = null;
  expectValue(GeneratedResponseMessage.fromJson(explicitNull).askForNps == null, 'explicit JSON null should remain null');

  expectFormatException(() => GeneratedResponseMessage.fromJson({{
    ...responseMessageJson(),
    'id': null,
  }}), 'Null field: id');
  expectFormatException(() => GeneratedResponseMessage.fromJson({{
    ...responseMessageJson()..remove('id'),
  }}), 'Missing required field: id');

  final opaqueChart = {{
    'chart_type': 'pie',
    'title': 'Opaque',
    'datasets': <Map<String, dynamic>>[],
    'vendor': 'external',
  }};
  final message = GeneratedMessage.fromJson({{
    'id': 'message-2',
    'created_at': '2026-07-02T12:00:00Z',
    'sender': 'ai',
    'text': 'chart',
    'type': 'text',
    'chart_data': opaqueChart,
  }});
  expectValue(message.chartData?['vendor'] == 'external', 'opaque chart_data should remain a raw map');
  expectValue(message.files.isEmpty, 'missing list default should use schema default');
}}
"""

    with tempfile.TemporaryDirectory(prefix='omi-dart-wire-check-') as temp_dir:
        script = Path(temp_dir) / 'wire_hardening_check.dart'
        script.write_text(source)
        result = subprocess.run(
            [dart, str(script)],
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if result.stdout:
        print(result.stdout, end='')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
