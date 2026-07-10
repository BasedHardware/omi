import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;
import 'package:omi/backend/schema/gen/task_intelligence_wire.g.dart' as intelligence;

Map<String, dynamic> _readJson(String relativePath) {
  final file = File('../$relativePath');
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
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

  test('canonical task fields survive the generated Dart DTO round trip', () {
    final fixture = _readJson('backend/tests/unit/fixtures/task_intelligence/canonical_round_trip_v1.json');
    final decoded = wire.GeneratedActionItemResponse.fromJson(
      fixture['create_response'] as Map<String, dynamic>,
    );
    final roundTrip = decoded.toJson();

    expect(roundTrip['goal_id'], 'goal-1');
    expect(roundTrip['workstream_id'], 'workstream-1');
    expect(roundTrip['owner'], 'user');
    expect(roundTrip['source'], 'conversation');
    expect(roundTrip['provenance'], isNotEmpty);
    expect(roundTrip['due_confidence'], 0.9);

    final listed = wire.GeneratedActionItemsResponse.fromJson(
      fixture['list_response'] as Map<String, dynamic>,
    );
    expect(listed.actionItems.single.toJson(), roundTrip);

    final createRequest = wire.GeneratedActionItemCreateRequest.fromJson(
      fixture['create_request'] as Map<String, dynamic>,
    );
    final updateRequest = wire.GeneratedActionItemUpdateRequest.fromJson(
      fixture['update_request'] as Map<String, dynamic>,
    );
    final updated = wire.GeneratedActionItemResponse.fromJson(
      fixture['update_response'] as Map<String, dynamic>,
    );
    expect(createRequest.toJson()['workstream_id'], 'workstream-1');
    expect(updateRequest.toJson()['status'], 'completed');
    expect(updated.toJson()['completed_at'], '2026-07-09T13:00:00.000Z');

    final legacy = wire.GeneratedActionItemResponse.fromJson(
      fixture['legacy_response'] as Map<String, dynamic>,
    );
    expect(legacy.goalId, isNull);
    expect(legacy.workstreamId, isNull);

    final unlinkPatch = wire.GeneratedActionItemUpdateRequest.fromJson({
      'goal_id': null,
      'description': 'Keep this field only',
    });
    final unlinkJson = unlinkPatch.toJson();
    expect(unlinkJson.containsKey('goal_id'), isTrue);
    expect(unlinkJson['goal_id'], isNull);
    expect(unlinkJson.containsKey('workstream_id'), isFalse);

    final workstream = intelligence.GeneratedWorkstream.fromJson(
      fixture['linked_workstream'] as Map<String, dynamic>,
    );
    expect(workstream.workstreamId, decoded.workstreamId);
    expect(workstream.status, 'open');

    final goalPatch = intelligence.GeneratedGoalUpdate.fromJson({
      'desired_outcome': null,
      'title': 'Keep moving',
    }).toJson();
    expect(goalPatch.containsKey('desired_outcome'), isTrue);
    expect(goalPatch['desired_outcome'], isNull);
    expect(goalPatch.containsKey('why_it_matters'), isFalse);

    final workstreamPatch = intelligence.GeneratedWorkstreamUpdate.fromJson({
      'next_review_at': null,
    }).toJson();
    expect(workstreamPatch.containsKey('next_review_at'), isTrue);
    expect(workstreamPatch['next_review_at'], isNull);
    expect(workstreamPatch.containsKey('objective'), isFalse);
  });

  test('Candidate/workstream checkpoint DTOs retain typed device-local evidence', () {
    final candidate = intelligence.GeneratedCandidateRecord.fromJson({
      'candidate_id': 'candidate-1',
      'subject_kind': 'task',
      'proposed_action': 'create',
      'task_change': {'description': 'Send the budget', 'owner': 'user'},
      'capture_confidence': 0.9,
      'ownership_confidence': 1.0,
      'evidence_refs': [
        {
          'kind': 'local_screen',
          'id': 'screen-1',
          'scope': 'device_local',
          'device_id': 'mac-1',
        },
      ],
      'source_surface': 'desktop_screen',
      'status': 'pending',
      'account_generation': 7,
      'idempotency_key': 'idempotency-1',
      'created_at': '2026-07-09T12:00:00Z',
    });
    final roundTrip = candidate.toJson();
    final evidence = (roundTrip['evidence_refs'] as List<dynamic>).single as Map<String, dynamic>;
    expect(evidence['scope'], 'device_local');
    expect(evidence['device_id'], 'mac-1');
    expect(candidate.taskChange?.create?.description, 'Send the budget');
    expect(candidate.taskChange?.change, isNull);

    final checkpoint = intelligence.GeneratedContinuationCheckpoint.fromJson({
      'checkpoint_id': 'checkpoint-1',
      'workstream_id': 'workstream-1',
      'runtime_id': 'mac-1',
      'context_summary': 'Current state',
      'last_event_sequence': 3,
      'updated_at': '2026-07-09T12:00:00Z',
    });
    expect(checkpoint.toJson()['last_event_sequence'], 3);
  });

  test('normalized context signals decode and round trip as string values', () {
    const values = ['person', 'app', 'document', 'meeting', 'free_time', 'dependency', 'agent'];
    final match = intelligence.GeneratedNormalizedContextMatch.fromJson({
      'signals': values,
      'subject_id': 'workstream-1',
      'subject_kind': 'workstream',
    });

    expect(match.signals.map((signal) => signal.value).toList(), values);
    expect(match.toJson()['signals'], values);
    expect(match.subjectKind.value, 'workstream');
  });
}
