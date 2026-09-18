import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/imports.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/import_history_page.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Regression coverage for #10984: the import-history row compared an import
/// job's raw UTC `year/month/day` against a *local* `today`, and rendered the
/// raw UTC `hour`/`minute`. For any viewer off UTC that flips the row between
/// the today / yesterday / absolute-date branches at the wrong boundary and
/// prints the wrong clock time (a 21:00 New York import rendered as 01:00, on
/// the following day).
///
/// Every case builds `createdAt` as a UTC instant projected from a known *local*
/// wall-clock time, which is how the server timestamp actually reaches the page.
/// The hour sweep keeps this honest in whatever timezone the suite runs in — a
/// single pinned hour only trips the bug at some UTC offsets.
String _two(int value) => value.toString().padLeft(2, '0');

void main() {
  late AppLocalizations l10n;

  setUpAll(() async {
    l10n = await AppLocalizations.delegate.load(const Locale('en'));
  });

  test('a job created earlier the same local day reads as today at its local time', () {
    final now = DateTime(2026, 8, 1, 12);
    for (var hour = 0; hour < 24; hour++) {
      final localCreatedAt = DateTime(2026, 8, 1, hour, 30);
      final label = formatImportJobTimestamp(l10n, localCreatedAt.toUtc(), now: now);

      expect(label, 'Today at ${_two(hour)}:30', reason: 'local hour $hour');
    }
  });

  test('a job created the previous local day reads as yesterday at its local time', () {
    final now = DateTime(2026, 8, 1, 12);
    for (var hour = 0; hour < 24; hour++) {
      final localCreatedAt = DateTime(2026, 7, 31, hour, 30);
      final label = formatImportJobTimestamp(l10n, localCreatedAt.toUtc(), now: now);

      expect(label, 'Yesterday at ${_two(hour)}:30', reason: 'local hour $hour');
    }
  });

  test('the yesterday branch survives every calendar day, including DST shifts', () {
    // `today - Duration(days: 1)` lands at 23:00 or 01:00 on a DST transition
    // day and never equals a midnight day key, so the row silently degrades to
    // the absolute-date branch. Sweeping a full year covers both transitions in
    // whichever timezone the suite runs in (2/366 days in America/New_York).
    for (var day = 0; day < 366; day++) {
      final now = DateTime(2026, 1, 1 + day, 12);
      final localCreatedAt = DateTime(2026, 1, day, 12);
      final label = formatImportJobTimestamp(l10n, localCreatedAt.toUtc(), now: now);

      expect(label, 'Yesterday at 12:00', reason: 'local day ${localCreatedAt.toIso8601String()}');
    }
  });

  test('an older job reads as its local date and local time', () {
    final now = DateTime(2026, 8, 1, 12);
    final localCreatedAt = DateTime(2026, 7, 20, 9, 5);

    expect(formatImportJobTimestamp(l10n, localCreatedAt.toUtc(), now: now), '20/7/2026 at 09:05');
  });

  testWidgets('the job card renders the label the page builds from context.l10n', (tester) async {
    // The page's own expression, driven through a real localized context: a job
    // whose server timestamp is decoded exactly as ImportJobResponse decodes it.
    final job = ImportJobResponse.fromJson({
      'job_id': 'job-1',
      'status': 'completed',
      'created_at': DateTime(2026, 8, 1, 21, 0).toUtc().toIso8601String(),
    });

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) =>
              Text(formatImportJobTimestamp(context.l10n, job.createdAt!, now: DateTime(2026, 8, 1, 22))),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Today at 21:00'), findsOneWidget);
  });

  test('fromGenerated keeps conversations_skipped from the wire model', () {
    final job = ImportJobResponse.fromJson({
      'job_id': 'job-1',
      'status': 'completed',
      'conversations_created': 0,
      'conversations_skipped': 4,
    });

    expect(job.conversationsCreated, 0);
    expect(job.conversationsSkipped, 4);
    expect(job.toGenerated().conversationsSkipped, 4);
  });

  test('import history shows a skipped-only job instead of hiding the count', () {
    expect(importJobCountChips(created: 0, skipped: 4).single.skipped, isTrue);
    expect(importJobCountChips(created: 0, skipped: 4).single.count, 4);
    expect(importJobCountChips(created: 2, skipped: 3).map((chip) => (chip.count, chip.skipped)).toList(), [
      (2, false),
      (3, true),
    ]);
    expect(importJobCountChips(created: 0, skipped: 0), isEmpty);
  });
}
