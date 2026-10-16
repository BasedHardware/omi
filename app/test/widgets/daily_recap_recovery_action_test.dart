import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/daily_recap_recovery_action.dart';
import 'package:omi/ui/ui.dart';

final _summary = DailySummary(
  id: 'recap',
  date: '2026-10-04',
  createdAt: DateTime.utc(2026, 10, 13),
  headline: 'Recovered day',
  overview: 'A saved conversation',
  stats: DayStats(totalConversations: 1),
);

Widget _app(DailyRecapCreator create, Future<void> Function(DailySummary) created, {bool settings = false}) =>
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
          body: DailyRecapRecoveryAction(
        create: create,
        onCreated: created,
        settingsRow: settings,
        now: () => DateTime(2026, 10, 13),
      )),
    );

Future<void> _pick(WidgetTester tester) async {
  await tester.tap(find.text('Generate Summary').hitTestable());
  await tester.pumpAndSettle();
  await tester.tap(find.text('4'));
  await tester.tap(find.text('OK'));
  await tester.pump();
}

void main() {
  testWidgets('reachable settings recovery selects an older date, runs once and publishes the result', (tester) async {
    final pending = Completer<ApiResult<DailySummary>>();
    final dates = <String>[];
    final created = <DailySummary>[];
    await tester.pumpWidget(_app((date) {
      dates.add(date);
      return pending.future;
    }, (summary) async {
      created.add(summary);
    }, settings: true));
    await _pick(tester);
    expect(dates, ['2026-10-04']);
    expect(find.byType(OmiSpinner), findsOneWidget);
    expect(tester.widget<OmiSettingsRow>(find.byType(OmiSettingsRow)).onTap, isNull);
    pending.complete(ApiSuccess(_summary));
    await tester.pumpAndSettle();
    expect(created.single.id, 'recap');
    expect(find.byType(OmiSpinner), findsNothing);
  });

  testWidgets('cancelling the date picker does not send a request', (tester) async {
    var calls = 0;
    await tester.pumpWidget(_app((date) async {
      calls++;
      return ApiSuccess(_summary);
    }, (_) async {}));
    await tester.tap(find.byKey(const Key('daily_recap_generate')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(calls, 0);
  });

  for (final entry in {
    400: 'No conversations to summarize for this day.',
    409: 'Processing. Please wait a few seconds before regenerating again.',
    429: 'Please wait a few seconds before regenerating again.',
    500: 'Something went wrong! Please try again later.',
  }.entries) {
    testWidgets('status ${entry.key} is shown honestly without publishing a recap', (tester) async {
      var published = false;
      await tester.pumpWidget(
          _app((_) async => ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: entry.key)), (_) async {
        published = true;
      }, settings: true));
      await _pick(tester);
      await tester.pumpAndSettle();
      expect(find.text(entry.value), findsOneWidget);
      expect(published, isFalse);
      expect(find.byType(OmiSpinner), findsNothing);
    });
  }
}
