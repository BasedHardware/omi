import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/dream.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/dream_report.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/dream_report_page.dart';
import 'package:omi/pages/review/review_page.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';

Map<String, dynamic> _runJson(String id, {String status = 'complete', String trigger = 'schedule'}) => {
      'run_id': id,
      'created_at': '2026-10-09T11:00:47Z',
      'trigger': trigger,
      'status': status,
      'error_type': status == 'failed' ? 'HTTPStatusError' : null,
      'records_read': 20,
      'records_queued_after': 108,
      'dirty_dropped': 0,
      'tokens': 5400,
      'cost_usd': 0.0108,
      'edits': [
        {
          'kind': 'spelling',
          'target_label': 'Paraform sync',
          'before': 'Bella',
          'after': 'Béla',
          'reason': 'Same person in three conversations',
          'evidence_count': 3,
          'outcome': 'shadow',
        },
      ],
      'questions': [
        {'kind': 'same_person', 'text': 'Is Bela K the same person as Béla?'},
      ],
      'slow_tasks': [
        {'description': 'Send the SOW to Paraform'},
      ],
      'vocabulary': [
        {
          'kind': 'person',
          'spelling': 'Béla',
          'aliases': ['Bella']
        },
      ],
      'feedback': [
        {'component': 'transcription', 'failure_class': 'spelling', 'severity': 'warning', 'count': 3},
      ],
      'privacy_rejected': 1,
    };

DreamReport _report({List<Map<String, dynamic>>? runs, int manualRunsToday = 0}) => DreamReport.fromJson({
      'mode': 'shadow',
      'passes_today': 3,
      'passes_limit': 4,
      'manual_runs_today': manualRunsToday,
      'manual_runs_limit': 3,
      'queued_changes': 108,
      'runs': runs ?? [_runJson('r2'), _runJson('r1', status: 'failed')],
    });

Widget _app(Widget home) => MaterialApp(
      theme: buildOmiTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    );

void main() {
  group('wire parsing', () {
    test('keeps well-formed runs and drops a run without an id or timestamp', () {
      final report = _report(runs: [
        _runJson('r1'),
        {'status': 'complete'},
        {'run_id': 'x', 'created_at': 'not a date'},
      ]);
      expect(report.runs.map((r) => r.runId), ['r1']);
      final run = report.runs.single;
      expect(run.edits.single.after, 'Béla');
      expect(run.questions, ['Is Bela K the same person as Béla?']);
      expect(run.vocabulary.single.aliases, ['Bella']);
      expect(report.live, isFalse);
      expect(report.manualRunsLeft, 3);
    });

    test('maps run-now refusals to the two explained cases', () {
      expect(
          dreamRunNowRefusal(const ApiProblem(ApiProblemKind.rateLimited, statusCode: 429)), DreamRunNowRefusal.limit);
      expect(dreamRunNowRefusal(const ApiProblem(ApiProblemKind.rejected, statusCode: 409)),
          DreamRunNowRefusal.inProgress);
      expect(dreamRunNowRefusal(const ApiProblem(ApiProblemKind.server, statusCode: 500)), isNull);
    });
  });

  testWidgets('shows the newest pass expanded with what it would fix, and older passes collapsed', (tester) async {
    await tester.pumpWidget(_app(DreamReportPage(loadReport: () async => ApiSuccess(_report()))));
    await tester.pumpAndSettle();
    expect(find.text('Bella → Béla'), findsOneWidget);
    expect(find.text('Is Bela K the same person as Béla?'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Failed (HTTPStatusError)'), 200);
    expect(find.text('Failed (HTTPStatusError)'), findsOneWidget);
    // The failed older pass is collapsed: its edits are not rendered twice.
    expect(find.text('Send the SOW to Paraform'), findsOneWidget);
  });

  testWidgets('Run Now refreshes on success and explains the manual limit', (tester) async {
    var loads = 0;
    var runs = 0;
    await tester.pumpWidget(_app(DreamReportPage(
      loadReport: () async {
        loads++;
        return ApiSuccess(_report());
      },
      runNow: () async {
        runs++;
        return runs == 1
            ? ApiSuccess(DreamRun.fromJson(_runJson('r3', trigger: 'manual'))!)
            : const ApiFailure(ApiProblem(ApiProblemKind.rateLimited, statusCode: 429));
      },
    )));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('dream_run_now')));
    await tester.pumpAndSettle();
    expect(runs, 1);
    expect(loads, 2);
    await tester.tap(find.byKey(const Key('dream_run_now')));
    await tester.pumpAndSettle();
    expect(find.text('No manual runs left today'), findsWidgets);
  });

  testWidgets('Run Now is disabled once the manual runs are used up', (tester) async {
    var runs = 0;
    await tester.pumpWidget(_app(DreamReportPage(
      loadReport: () async => ApiSuccess(_report(manualRunsToday: 3)),
      runNow: () async {
        runs++;
        return const ApiFailure(ApiProblem(ApiProblemKind.server));
      },
    )));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('dream_run_now')), warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(runs, 0);
  });

  testWidgets('Review shows the Dream Report link only when the report is available', (tester) async {
    Future<void> pumpReview(bool available) async {
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [], remainingToday: 0)),
      );
      await tester.pumpWidget(ChangeNotifierProvider<ReviewProvider>.value(
        value: provider,
        child: _app(ReviewPage(key: ValueKey(available), probeDreamReport: () async => available)),
      ));
      await tester.pumpAndSettle();
    }

    await pumpReview(false);
    expect(find.byKey(const Key('review_dream_report')), findsNothing);
    await pumpReview(true);
    expect(find.byKey(const Key('review_dream_report')), findsOneWidget);
  });
}
