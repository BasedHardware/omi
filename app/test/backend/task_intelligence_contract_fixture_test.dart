import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;

Map<String, dynamic> _readJson(String relativePath) {
  final file = File('../$relativePath');
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

void _expectKnownGap(String ticket, void Function() assertion) {
  TestFailure? expectedFailure;
  try {
    assertion();
  } on TestFailure catch (error) {
    expectedFailure = error;
  }
  if (expectedFailure == null) {
    fail('$ticket known gap is closed; remove this strict characterization marker');
  }
}

void main() {
  test('task intelligence v1 contract exposes every cross-lane schema and example', () {
    final contract = _readJson('backend/config/task_intelligence_contract_v1.json');
    final definitions = contract[r'$defs'] as Map<String, dynamic>;
    final examples = contract['examples'] as Map<String, dynamic>;
    const domains = {
      'task',
      'candidate',
      'goal',
      'workstream',
      'workstream_event',
      'evidence_ref',
      'feedback',
      'recommendation',
      'decision_record',
      'kernel_workstream_bridge',
      'attribution_event',
    };

    expect(contract['schema_version'], 1);
    expect(definitions.keys.toSet().containsAll(domains), isTrue);
    expect(examples.keys.toSet(), containsAll(domains));
    final task = (examples['task'] as List<dynamic>).first as Map<String, dynamic>;
    expect(task['priority'], 'high');
  });

  test('capture fixture modalities carry identical recorded adapter outputs', () {
    final fixture = _readJson('backend/tests/unit/fixtures/task_intelligence/capture_v1.json');
    final cases = fixture['cases'] as List<dynamic>;

    expect(cases, isNotEmpty);
    for (final rawCase in cases) {
      final testCase = rawCase as Map<String, dynamic>;
      final inputs = testCase['inputs'] as Map<String, dynamic>;
      final transcript = inputs['transcript'] as Map<String, dynamic>;
      final screen = inputs['screen'] as Map<String, dynamic>;
      expect(transcript['stub_output'], screen['stub_output'], reason: 'modality drift in ${testCase['id']}');
    }
  });

  test('Ticket 03 characterizes canonical fields lost by the generated Dart DTO', () {
    final decoded = wire.GeneratedActionItemResponse.fromJson({
      'id': 'task-1',
      'description': 'Send the budget',
      'completed': false,
      'goal_id': 'goal-1',
      'workstream_id': 'workstream-1',
      'owner': 'user',
      'source': 'conversation',
      'provenance': [
        {'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'},
      ],
      'due_confidence': 0.9,
    });
    final roundTrip = decoded.toJson();

    _expectKnownGap('#9352 Ticket 03', () {
      expect(roundTrip['goal_id'], 'goal-1');
      expect(roundTrip['workstream_id'], 'workstream-1');
      expect(roundTrip['owner'], 'user');
      expect(roundTrip['source'], 'conversation');
      expect(roundTrip['provenance'], isNotEmpty);
      expect(roundTrip['due_confidence'], 0.9);
    });
  });
}
