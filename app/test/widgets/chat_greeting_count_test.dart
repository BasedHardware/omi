import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/chat_entrance.dart';
import 'package:omi/pages/chat/widgets/chat_starters.dart';
import 'package:omi/ui/ui.dart';

Widget host(int count, {bool reduced = false}) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: MediaQuery(
        data: MediaQueryData(disableAnimations: reduced),
        child: Scaffold(
          body: ChatEntrance(
            child: ChatGreeting(isConnected: true, name: 'Alex', hour: 10, todayCount: count),
          ),
        ),
      ),
    );

double opacity(WidgetTester tester, String key) =>
    tester.widget<Opacity>(find.descendant(of: find.byKey(Key(key)), matching: find.byType(Opacity)).first).opacity;

ServerConversation conversation(String id, DateTime createdAt, {bool discarded = false}) =>
    ServerConversation(id: id, createdAt: createdAt, structured: Structured('', ''), discarded: discarded);

void main() {
  testWidgets('V3 text, count-up and line movement share one bounded entrance', (tester) async {
    await tester.pumpWidget(host(12));
    expect(find.text('Morning, Alex.'), findsOneWidget);
    final heading = tester.widget<Text>(find.text('Morning, Alex.'));
    expect(heading.style!.fontSize, OmiType.title1.fontSize);
    expect(heading.style!.fontWeight, FontWeight.w600);
    await tester.pump(const Duration(milliseconds: 100));
    expect(opacity(tester, 'chat_greeting_rise'), greaterThan(0));
    expect(opacity(tester, 'chat_count_rise'), 0);
    expect(opacity(tester, 'chat_question_rise'), 0);
    await tester.pump(const Duration(milliseconds: 100));
    expect(opacity(tester, 'chat_count_rise'), greaterThan(0));
    expect(opacity(tester, 'chat_question_rise'), 0);
    await tester.pump(const Duration(milliseconds: 350));
    expect(opacity(tester, 'chat_greeting_rise'), 1);
    expect(opacity(tester, 'chat_question_rise'), greaterThan(0));
    expect(tester.widget<Text>(find.byKey(const Key('chat_today_count'))).data, isNot('12 conversations today.'));
    await tester.pumpAndSettle();
    expect(find.text('12 conversations today.'), findsOneWidget);
    expect(find.text('What do you want to know?'), findsOneWidget);
    final settledQuestionY = tester.getTopLeft(find.text('What do you want to know?')).dy;
    await tester.pump(const Duration(seconds: 5));
    expect(tester.getTopLeft(find.text('What do you want to know?')).dy, settledQuestionY);
  });

  test('local count uses the viewer day and excludes discarded conversations', () {
    final day = DateTime(2026, 9, 29, 12);
    final rows = [
      conversation('one', DateTime(2026, 9, 29, 8)),
      conversation('two', DateTime(2026, 9, 29, 23, 59)),
      conversation('discarded', DateTime(2026, 9, 29, 10), discarded: true),
      conversation('yesterday', DateTime(2026, 9, 28, 23, 59)),
    ];
    expect(countConversationsForLocalDay(rows, day), 2);
  });

  testWidgets('a provider count update does not replay the greeting', (tester) async {
    await tester.pumpWidget(host(0));
    await tester.pumpAndSettle();
    // Zero is not a greeting: only the greeting and the question show.
    expect(find.text('No conversations today.'), findsNothing);
    expect(find.byKey(const Key('chat_today_count')), findsNothing);
    expect(find.text('What do you want to know?'), findsOneWidget);
    await tester.pumpWidget(host(6));
    expect(opacity(tester, 'chat_greeting_rise'), 1);
    expect(find.text('6 conversations today.'), findsOneWidget);
    // The line joining the column takes one layout frame; nothing keeps ticking after it.
    await tester.pump();
    expect(tester.binding.hasScheduledFrame, isFalse);
    expect(opacity(tester, 'chat_count_rise'), 1);
  });

  testWidgets('Reduce Motion renders the final count without a ticker', (tester) async {
    await tester.pumpWidget(host(7, reduced: true));
    await tester.pumpAndSettle();
    expect(find.text('7 conversations today.'), findsOneWidget);
    expect(tester.binding.hasScheduledFrame, isFalse);
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });
}
