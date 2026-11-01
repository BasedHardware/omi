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
PENDING_WIRE = MESSAGES_WIRE.with_name('pending_work_wire.g.dart')
ADAPTER_DEPENDENCIES = (
    'backend/schema/chat_content_block.dart',
    'backend/schema/memory_review.dart',
    'models/chat_evidence_reference.dart',
    'backend/schema/gen/users_wire.g.dart',
)


def package_free_message_adapter_source() -> str:
    source = MESSAGE_ADAPTER.read_text(encoding='utf-8')
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
    for dependency in ADAPTER_DEPENDENCIES:
        source = source.replace('package:omi/' + dependency, Path(dependency).name)
    # Keep Dart directives before the harness-only declarations.
    lines = source.splitlines(keepends=True)
    imports = ''.join(line for line in lines if line.startswith('import '))
    body = ''.join(line for line in lines if not line.startswith('import '))
    return "import 'messages_wire.g.dart' as wire;\n" + imports + prelude + body


def main() -> int:
    dart = shutil.which('dart')
    if dart is None:
        print('dart executable not found on PATH')
        return 1

    source = """
import 'messages_wire.g.dart';
import 'message_adapter.dart';
import 'pending_work_wire.g.dart';

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
  final pending = GeneratedPendingWorkSnapshot.fromJson({
    'enabled': true,
    'attention_unseen_count': 1,
    'items': [{
      'id': 'conv:c1',
      'kind': 'conversation',
      'state': 'summarizing',
      'conversation_ids': ['c1'],
      'duration_seconds': 12.5,
      'started_at': '2026-10-16T00:00:00Z',
      'updated_at': null,
    }],
  });
  expectValue(pending.enabled && pending.attentionUnseenCount == 1, 'pending snapshot should decode');
  expectValue(pending.items.single.durationSeconds == 12.5, 'fractional duration should decode');
  final roundTrip = GeneratedPendingWorkSnapshot.fromJson(pending.toJson());
  expectValue(roundTrip.items.single.startedAt?.toUtc() == DateTime.utc(2026, 10, 16), 'dates should round-trip');
  expectValue(roundTrip.items.single.updatedAt == null, 'nullable dates should round-trip');
  expectValue(const GeneratedSeenRequest(all: true).toJson()['ids'].isEmpty, 'seen defaults must encode valid requests');
  final retry = GeneratedAttentionRetryAllResponse.fromJson({
    'operations': [{'id': 'attention:c1', 'operation_id': 'op1', 'state': 'in_progress'}],
  });
  expectValue(retry.operations.single.operationId == 'op1', 'retry operations should decode');
  expectValue(retry.toJson()['operations'][0]['id'] == 'attention:c1', 'retry operations should encode');
  expectFormatException(() => GeneratedPendingWorkSnapshot.fromJson({'enabled': true}), 'attention_unseen_count');

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
        shutil.copyfile(PENDING_WIRE, temp_path / PENDING_WIRE.name)
        for dependency in ADAPTER_DEPENDENCIES:
            path = ROOT_DIR / 'app' / 'lib' / dependency
            contents = path.read_text(encoding='utf-8')
            for nested in ADAPTER_DEPENDENCIES:
                contents = contents.replace('package:omi/' + nested, Path(nested).name)
            (temp_path / path.name).write_text(contents, encoding='utf-8', newline='\n')
        (temp_path / 'message_adapter.dart').write_text(
            package_free_message_adapter_source(), encoding='utf-8', newline='\n'
        )
        script = temp_path / 'wire_hardening_check.dart'
        script.write_text(source, encoding='utf-8', newline='\n')
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
