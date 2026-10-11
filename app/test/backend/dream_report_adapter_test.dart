import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/dream_report.dart';

import 'dream_wire_test.dart' show completedRun;

void main() {
  test(
    'screen adapter uses generated fields and isolates malformed history rows',
    () {
      final page = {
        'mode': 'shadow',
        'passes_today': 3,
        'passes_limit': 4,
        'manual_runs_today': 1,
        'manual_runs_limit': 3,
        'queued_changes': 108,
        'runs': [
          completedRun(),
          {'status': 'complete'},
          completedRun()..['created_at'] = 'invalid',
        ],
      };
      final report = DreamReport.fromJson(page);
      expect(report.runs, hasLength(1));
      final run = report.runs.single;
      expect(run.createdAt.toUtc(), DateTime.utc(2026, 10, 9, 11, 0, 47));
      expect(run.edits.single.targetLabel, 'Conversation · Synthetic sync');
      expect(run.questions, ['Are these the same invented robot?']);
      expect(run.slowTasks, ['Send the synthetic notes']);
      expect(run.vocabulary.single.aliases, ['Qorby']);
      expect(run.feedback.single.count, 3);
      expect(report.manualRunsLeft, 2);
      expect(report.live, isFalse);
      page['passes_limit'] = 'invalid';
      expect(() => DreamReport.fromJson(page), throwsFormatException);
    },
  );
}
