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
MESSAGE_ADAPTER = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'message.dart'


def package_free_message_adapter_source() -> str:
    source = MESSAGE_ADAPTER.read_text()
    source = source.replace("import 'package:collection/collection.dart';\n", '')
    source = source.replace(
        "import 'package:omi/backend/schema/gen/messages_wire.g.dart' as wire;\n",
        "import 'messages_wire.g.dart' as wire;\n",
    )
    source = source.replace("import 'package:uuid/uuid.dart';\n", '')
    source = source.replace("import 'messages_wire.g.dart' as wire;\n", '')
    prelude = """
extension FirstWhereOrNullForHarness<E> on Iterable<E> {
  E? firstWhereOrNull(bool Function(E) test) {
    for (final value in this) {
      if (test(value)) return value;
    }
    return null;
  }
}

class Uuid {
  const Uuid();
  String v4() => '00000000-0000-4000-8000-000000000000';
}

"""
    return "import 'messages_wire.g.dart' as wire;\n\n" + prelude + source


def main() -> int:
    dart = shutil.which('dart')
    if dart is None:
        print('dart executable not found on PATH')
        return 1

    source = """
import 'messages_wire.g.dart';
import 'message_adapter.dart';

void expectValue(bool condition, String message) {
  if (!condition) {
    throw StateError(message);
  }
}

void expectFormatException(void Function() callback, String messagePart) {
  try {
    callback();
  } on FormatException catch (error) {
    expectValue(error.message.contains(messagePart), 'expected FormatException containing "$messagePart", got "$error"');
    return;
  }
  throw StateError('expected FormatException containing "$messagePart"');
}

Map<String, dynamic> responseMessageJson() => {
  'id': 'message-1',
  'created_at': '2026-07-02T12:00:00Z',
  'sender': 'ai',
  'text': 'hello',
  'type': 'text',
};

void main() {
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

  expectFormatException(() => GeneratedResponseMessage.fromJson({
    ...responseMessageJson(),
    'id': null,
  }), 'Null field: id');
  expectFormatException(() => GeneratedResponseMessage.fromJson({
    ...responseMessageJson()..remove('id'),
  }), 'Missing required field: id');

  final opaqueChart = {
    'chart_type': 'pie',
    'title': 'Opaque',
    'datasets': <Map<String, dynamic>>[],
    'vendor': 'external',
  };
  final message = GeneratedMessage.fromJson({
    'id': 'message-2',
    'created_at': '2026-07-02T12:00:00Z',
    'sender': 'ai',
    'text': 'chart',
    'type': 'text',
    'chart_data': opaqueChart,
  });
  expectValue(message.chartData?['vendor'] == 'external', 'opaque chart_data should remain a raw map');
  expectValue(message.files.isEmpty, 'missing list default should use schema default');

  final responseModel = ServerMessage.fromResponseJson(responseMessageJson());
  expectValue(responseModel.askForNps == false, 'response adapter should use generated ask_for_nps default');

  final legacyIntegration = ServerMessage.fromResponseJson({
    ...responseMessageJson(),
    'from_integration': true,
  });
  expectValue(legacyIntegration.fromIntegration == true, 'response adapter should preserve legacy from_integration');

  final canonicalIntegration = ServerMessage.fromResponseJson({
    ...responseMessageJson(),
    'from_external_integration': true,
  });
  expectValue(
    canonicalIntegration.fromIntegration == true,
    'response adapter should preserve canonical from_external_integration',
  );

  final responseNull = ServerMessage.fromResponseJson(explicitNull);
  expectValue(responseNull.askForNps == false, 'response adapter should coalesce explicit ask_for_nps null to false');

  final opaqueChartModel = ServerMessage.fromResponseJson({
    ...responseMessageJson(),
    'chart_data': opaqueChart,
  });
  expectValue(opaqueChartModel.chartData == null, 'invalid chart_type should stay opaque');
  expectValue(opaqueChartModel.toJson()['chart_data']['vendor'] == 'external', 'opaque chart_data should round-trip through adapter');

  final typedChart = {
    'chart_type': 'line',
    'title': 'Typed',
    'datasets': [
      {
        'label': 'Series',
        'data_points': [
          {'label': 'A', 'value': 1},
        ],
      },
    ],
  };
  final typedChartModel = ServerMessage.fromResponseJson({
    ...responseMessageJson(),
    'chart_data': typedChart,
  });
  expectValue(typedChartModel.chartData?.chartType == 'line', 'typed chart_data should parse');
  expectValue(typedChartModel.toJson()['chart_data']['chart_type'] == 'line', 'typed chart_data should round-trip');
}
"""

    with tempfile.TemporaryDirectory(prefix='omi-dart-wire-check-') as temp_dir:
        temp_path = Path(temp_dir)
        shutil.copyfile(MESSAGES_WIRE, temp_path / 'messages_wire.g.dart')
        (temp_path / 'message_adapter.dart').write_text(package_free_message_adapter_source())
        script = temp_path / 'wire_hardening_check.dart'
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
