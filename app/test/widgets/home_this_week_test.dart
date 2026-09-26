import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/home_sections.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/format/omi_duration.dart';

/// Home's "This week" counts the whole week, not whatever the Conversations tab's filter left
/// loaded (a Starred filter once showed 39 s instead of 3 h 18 m until it was cleared).
void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    HomeThisWeek.resetForTest();
  });

  ServerConversation at(DateTime start, Duration length, {bool starred = false}) => ServerConversation(
        id: '${start.millisecondsSinceEpoch}',
        createdAt: start,
        startedAt: start,
        finishedAt: start.add(length),
        structured: Structured('Title', 'Overview'),
        starred: starred,
      );

  Future<void> pump(WidgetTester tester, ConversationProvider provider) => tester.pumpWidget(
        ChangeNotifierProvider<ConversationProvider>.value(
          value: provider,
          child: const MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: SingleChildScrollView(child: HomeThisWeek())),
          ),
        ),
      );

  testWidgets('a filter on the Conversations tab does not shrink the week', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final monday = today.subtract(Duration(days: today.weekday - DateTime.monday));
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    final starredClip = at(monday.add(const Duration(hours: 9)), const Duration(seconds: 39), starred: true);
    provider.conversations = [
      starredClip,
      at(monday.add(const Duration(hours: 11)), const Duration(hours: 1)),
      at(monday.add(const Duration(hours: 14)), const Duration(minutes: 30)),
      at(monday.subtract(const Duration(days: 2)), const Duration(hours: 3)), // last week: the list reaches Monday
    ];
    await pump(tester, provider);
    final week = en.capturedDuration(OmiDuration.compact(3600 + 1800 + 39, en));
    expect(find.text(week), findsOneWidget);

    // The Starred chip reloads the list with only starred conversations.
    provider.showStarredOnly = true;
    provider.conversations = [starredClip];
    provider.notifyListeners();
    await tester.pump();
    expect(find.text(week), findsOneWidget, reason: 'still the whole week');
    expect(find.text(en.capturedDuration(OmiDuration.compact(39, en))), findsNothing);
  });

  test('a filtered or partial list cannot be counted', () {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    final monday = DateTime(2026, 9, 21);
    provider.conversations = [at(DateTime(2026, 9, 18), const Duration(minutes: 5))];
    expect(HomeThisWeek.countWeek(provider, monday), isNotNull);
    provider.showStarredOnly = true;
    expect(HomeThisWeek.countWeek(provider, monday), isNull);
    provider.showStarredOnly = false;
    provider.selectedFolderId = 'work';
    expect(HomeThisWeek.countWeek(provider, monday), isNull);
  });
  // IMG_1168: tapping a day shows that day's time, not only the week's; tapping it again goes back.
  testWidgets('tapping a day shows its time; tapping it again shows the week', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final monday = today.subtract(Duration(days: today.weekday - DateTime.monday));
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.conversations = [
      at(monday.add(const Duration(hours: 9)), const Duration(minutes: 20)),
      at(today.add(const Duration(hours: 1)), const Duration(minutes: 5)),
      at(monday.subtract(const Duration(days: 2)), const Duration(hours: 1)), // the list reaches Monday
    ];
    await pump(tester, provider);
    final week = en.capturedDuration(OmiDuration.compact(today == monday ? 1500 : 1500, en));
    expect(find.text(week), findsOneWidget);

    await tester.tap(find.byKey(const Key('home_this_week_day_0')));
    await tester.pump();
    final mondayTime = today == monday ? 1500 : 1200;
    expect(find.textContaining(en.capturedDuration(OmiDuration.compact(mondayTime, en))), findsOneWidget);
    expect(find.textContaining('Monday'), findsOneWidget);

    await tester.tap(find.byKey(const Key('home_this_week_day_0')));
    await tester.pump();
    expect(find.text(week), findsOneWidget, reason: 'back to the week');
  });
}
