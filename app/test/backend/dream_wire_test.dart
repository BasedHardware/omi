import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/gen/dream_wire.g.dart';
import 'package:omi/backend/schema/dream_report.dart';

Map<String, dynamic> completedRun() => {
      'run_id': 'synthetic-run',
      'created_at': '2026-10-09T11:00:47Z',
      'trigger': 'schedule',
      'status': 'complete',
      'error_type': null,
      'records_read': 20,
      'records_queued_after': 108,
      'dirty_dropped': 1,
      'tokens': 5400,
      'cost_usd': 0.0108,
      'edits': [
        {
          'kind': 'spelling',
          'target_label': 'Conversation · Synthetic sync',
          'before': 'Qorby',
          'after': 'Qorbi',
          'reason': 'Repeated spelling evidence',
          'evidence_count': 3,
          'outcome': 'shadow',
        },
      ],
      'questions': [
        {'kind': 'same_person', 'text': 'Are these the same invented robot?'},
      ],
      'slow_tasks': [
        {'description': 'Send the synthetic notes'},
      ],
      'vocabulary': [
        {
          'kind': 'person',
          'spelling': 'Qorbi',
          'aliases': ['Qorby']
        },
      ],
      'feedback': [
        {'component': 'transcription', 'failure_class': 'spelling', 'severity': 'warning', 'count': 3},
      ],
      'privacy_rejected': 1,
    };

void main() {
  test('generated GET response decodes allowance and every nested report model', () {
    final page = GeneratedDreamRunsResponse.fromJson({
      'mode': 'shadow',
      'passes_today': 3,
      'passes_limit': 4,
      'manual_runs_today': 1,
      'manual_runs_limit': 3,
      'queued_changes': 108,
      'runs': [completedRun()],
    });
    expect(page.manualRunsToday, 1);
    expect(page.manualRunsLimit, 3);
    expect(page.passesToday, 3);
    expect(page.passesLimit, 4);
    expect(page.queuedChanges, 108);
    final run = page.runs.single;
    expect(run.createdAt.toUtc(), DateTime.utc(2026, 10, 9, 11, 0, 47));
    expect(run.errorType, isNull);
    expect(run.recordsRead, 20);
    expect(run.recordsQueuedAfter, 108);
    expect(run.edits!.single.targetLabel, 'Conversation · Synthetic sync');
    expect(run.edits!.single.evidenceCount, 3);
    expect(run.questions!.single.text, 'Are these the same invented robot?');
    expect(run.slowTasks!.single.description, 'Send the synthetic notes');
    expect(run.vocabulary!.single.aliases, ['Qorby']);
    expect(run.feedback!.single.count, 3);
    expect(run.privacyRejected, 1);
    expect(GeneratedDreamRunsResponse.fromJson(page.toJson()).runs.single.costUsd, 0.0108);
    final report = DreamReport.fromGenerated(page);
    expect(report.runs.single.runId, 'synthetic-run');
    expect(report.runs.single.edits.single.targetLabel, run.edits!.single.targetLabel);
    expect(report.manualRunsLeft, 2);
  });

  test('generated POST response decodes idle, failed and deadline without an envelope', () {
    expect(const GeneratedDreamRunRequest().toJson(), isEmpty);
    for (final status in ['idle', 'failed', 'deadline']) {
      final json = completedRun()
        ..['run_id'] = ''
        ..['trigger'] = 'manual'
        ..['status'] = status
        ..['cost_usd'] = 0
        ..['edits'] = []
        ..['error_type'] = status == 'idle' ? null : 'TimeoutError';
      final run = GeneratedDreamRun.fromJson(json);
      expect(run.status, status);
      expect(run.trigger, 'manual');
      expect(run.costUsd, 0.0);
      expect(run.edits, isEmpty);
      expect(run.errorType, json['error_type']);
      expect(DreamRun.fromGenerated(run), isNull);
      expect(DreamRun.fromJson({...run.toJson(), 'run_id': status})!.runId, status);
    }
  });

  test('generated decoder rejects malformed run lists and missing mandatory fields', () {
    final run = completedRun()..remove('run_id');
    expect(() => GeneratedDreamRun.fromJson(run), throwsFormatException);
    final page = {
      'mode': 'shadow',
      'passes_today': 0,
      'passes_limit': 4,
      'manual_runs_today': 0,
      'manual_runs_limit': 3,
      'queued_changes': 0,
      'runs': 'malformed',
    };
    expect(() => GeneratedDreamRunsResponse.fromJson(page), throwsFormatException);
  });
}
