// Imports: Settings > Import Data (ImportHistoryPage) with the transcript-file importer next to
// Limitless, and a history of transcript-file and Limitless jobs.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/settings/import_history_page.dart';

import '../harness.dart';

// No skipped counts: a row with both the created and the skipped chip squeezes its status text
// into a narrow column. That layout predates this importer (Limitless rows on main do the same).
String _jobs() {
  final now = DateTime.now().toUtc();
  String ago(Duration d) => now.subtract(d).toIso8601String();
  return jsonEncode([
    {
      'job_id': 'job-transcripts-running',
      'status': 'processing',
      'source_type': 'transcript_files',
      'total_files': 12,
      'processed_files': 5,
      'conversations_created': 4,
      'created_at': ago(const Duration(minutes: 2)),
    },
    {
      'job_id': 'job-transcripts-done',
      'status': 'completed',
      'source_type': 'transcript_files',
      'total_files': 8,
      'processed_files': 8,
      'conversations_created': 7,
      'created_at': ago(const Duration(hours: 3)),
    },
    {
      'job_id': 'job-transcripts-failed',
      'status': 'failed',
      'source_type': 'transcript_files',
      'total_files': 0,
      'processed_files': 0,
      'conversations_created': 0,
      'error': 'The upload is not a valid ZIP archive.',
      'created_at': ago(const Duration(days: 1)),
    },
    {
      'job_id': 'job-limitless-done',
      'status': 'completed',
      'source_type': 'limitless',
      'total_files': 30,
      'processed_files': 30,
      'conversations_created': 28,
      'created_at': ago(const Duration(days: 3)),
    },
  ]);
}

final importsScenarios = <AuditScenario>[
  AuditScenario(
    id: 'imports-history',
    title: 'Import Data: transcript files next to Limitless, with a running, a finished and a failed import',
    page: 'lib/pages/settings/import_history_page.dart (ImportHistoryPage)',
    state: 'The fixture backend answers GET /v1/import/jobs with three transcript-file jobs and one Limitless job',
    run: (a) async {
      // The page polls every 3 s while a job is processing; every poll gets the same history.
      for (var i = 0; i < 20; i++) {
        a.server.failNext('GET', '/v1/import/jobs', status: 200, body: _jobs());
      }
      await a.pump(const ImportHistoryPage(), scaffold: false);
      expect(find.text('Transcript files'), findsOneWidget);
      await a.scrollSeries('Open Settings > Import Data and scroll through the import history');
    },
  ),
];
