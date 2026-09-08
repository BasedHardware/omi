import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/capture_gap_list_item.dart';

CalendarCaptureGap _gap({String eventId = 'evt-1', String title = 'Scaling Forever sync'}) {
  return CalendarCaptureGap(
    eventId: eventId,
    title: title,
    startTime: DateTime.parse('2026-08-18T19:30:00Z'),
    endTime: DateTime.parse('2026-08-18T20:00:00Z'),
  );
}

Widget _localized(Widget child) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets('the header states the not-captured count', (tester) async {
    await tester.pumpWidget(_localized(const CaptureGapHeader(count: 3)));
    await tester.pumpAndSettle();

    expect(find.textContaining('3'), findsOneWidget);
    expect(find.textContaining('Not captured'), findsOneWidget);
  });

  testWidgets('a gap row shows the event title and time range, not a fabricated conversation', (tester) async {
    await tester.pumpWidget(_localized(CaptureGapListItem(gap: _gap())));
    await tester.pumpAndSettle();

    expect(find.text('Scaling Forever sync'), findsOneWidget);
    expect(find.byIcon(Icons.event_busy), findsOneWidget);
    // Calendar rows are their own surface — they never render conversation
    // affordances.
    expect(find.byType(InkWell), findsNothing);
  });

  test('fromJson reads the capture-gaps API payload', () {
    final gap = CalendarCaptureGap.fromJson({
      'event_id': 'evt-9',
      'title': 'Board review',
      'start_time': '2026-08-18T19:30:00Z',
      'end_time': '2026-08-18T20:00:00Z',
      'status': 'confirmed',
      'coverage': 'not_captured',
    });

    expect(gap.eventId, 'evt-9');
    expect(gap.title, 'Board review');
    expect(gap.coverage, 'not_captured');
  });

  test('gaps group by the local day of their start', () {
    final early = _gap(eventId: 'a');
    final lateSameDay = CalendarCaptureGap(
      eventId: 'b',
      title: 'Evening sync',
      startTime: DateTime.parse('2026-08-18T19:45:00Z'),
      endTime: DateTime.parse('2026-08-18T20:15:00Z'),
    );

    final byDay = groupCaptureGapsByLocalDay([early, lateSameDay]);

    expect(byDay.keys, hasLength(1));
    // Both gaps bucket to the same local day, ordered as fetched.
    expect(byDay.values.single.map((gap) => gap.eventId), ['a', 'b']);
  });
}
