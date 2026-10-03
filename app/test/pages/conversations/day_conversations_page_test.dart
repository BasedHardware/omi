import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';

ServerConversation _conversation(String id, String title, DateTime started) => ServerConversation.fromJson({
      'id': id,
      'created_at': started.toUtc().toIso8601String(),
      'started_at': started.toUtc().toIso8601String(),
      'finished_at': started.add(const Duration(minutes: 10)).toUtc().toIso8601String(),
      'structured': {'title': title, 'overview': '', 'emoji': '', 'category': 'work'},
      'status': 'completed',
      'transcript_segments': [],
    });

class _Fetch {
  _Fetch({this.rows = const [], this.ok = true});

  List<ServerConversation> Function(int offset)? pages;
  List<ServerConversation> rows;
  bool ok;
  bool truncated = false;
  final calls = <({DateTime start, DateTime end, int offset})>[];
  Completer<({List<ServerConversation> items, bool ok, bool truncated})>? gate;

  Future<({List<ServerConversation> items, bool ok, bool truncated})> call(
      {required DateTime startDate, required DateTime endDate, int limit = 50, int offset = 0}) {
    calls.add((start: startDate, end: endDate, offset: offset));
    final pending = gate;
    if (pending != null) return pending.future;
    return Future.value((items: pages?.call(offset) ?? rows, ok: ok, truncated: truncated));
  }
}

Future<void> _pumpPage(WidgetTester tester, DateTime date, DayConversationsFetcher fetch) {
  return tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
      ChangeNotifierProvider(create: (_) => ConversationDetailProvider()),
      ChangeNotifierProvider(create: (_) => FolderProvider()),
      ChangeNotifierProvider(create: (_) => IntegrationProvider()),
      ChangeNotifierProvider(create: (_) => UsageProvider()),
      ChangeNotifierProvider(create: (_) => MessageProvider()),
      ChangeNotifierProvider(
          create: (_) => ConversationProvider(
              conversationListFetcher: () async => (items: <ServerConversation>[], ok: true), isSignedIn: () => true)),
    ],
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: DayConversationsPage(date: date, fetchConversations: fetch),
    ),
  ));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  final day = DateTime(2026, 9, 12);

  testWidgets('fetches the exact local-day bounds and renders rows', (tester) async {
    final fetch = _Fetch(rows: [_conversation('c1', 'Morning Standup', DateTime(2026, 9, 12, 9))]);
    await _pumpPage(tester, day, fetch.call);
    expect(find.byType(OmiSpinner), findsOneWidget);
    await tester.pump();
    await tester.pumpAndSettle();

    expect(fetch.calls, hasLength(1));
    expect(fetch.calls.first.start, DateTime(2026, 9, 12));
    expect(fetch.calls.first.end, DateTime(2026, 9, 13).subtract(const Duration(microseconds: 1)));
    expect(fetch.calls.first.offset, 0);
    expect(find.text('Morning Standup'), findsOneWidget);
  });

  testWidgets('an empty day shows the localized empty state', (tester) async {
    await _pumpPage(tester, day, _Fetch().call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.textContaining('No conversations on'), findsOneWidget);
  });

  testWidgets('a failed fetch shows the error state and retry reloads', (tester) async {
    final fetch = _Fetch(ok: false);
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.byType(OmiErrorState), findsOneWidget);

    fetch.ok = true;
    fetch.rows = [_conversation('c1', 'Recovered', DateTime(2026, 9, 12, 9))];
    await tester.tap(find.text('Try Again'));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.text('Recovered'), findsOneWidget);
    expect(fetch.calls, hasLength(2));
  });

  testWidgets('previous/next day refetch with shifted bounds; next stops at today', (tester) async {
    final fetch = _Fetch();
    await _pumpPage(tester, day, fetch.call);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('day_previous')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(fetch.calls.last.start, DateTime(2026, 9, 11));

    await tester.tap(find.byKey(const ValueKey('day_next')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(fetch.calls.last.start, DateTime(2026, 9, 12));
  });

  testWidgets('a stale page from a superseded day never lands', (tester) async {
    final gate = Completer<({List<ServerConversation> items, bool ok, bool truncated})>();
    final fetch = _Fetch(rows: [_conversation('c-new', 'Current Day', DateTime(2026, 9, 12, 9))])..gate = gate;
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();

    fetch.gate = null;
    await tester.tap(find.byKey(const ValueKey('day_previous')));
    await tester.pump();
    await tester.pumpAndSettle();

    gate.complete((items: [_conversation('c-old', 'Stale Day', DateTime(2026, 9, 12, 9))], ok: true, truncated: false));
    await tester.pumpAndSettle();

    expect(find.text('Stale Day'), findsNothing, reason: 'the late page must not overwrite the new day');
    expect(find.byKey(const ValueKey('day_previous')), findsOneWidget);
  });

  testWidgets('the global date filter is untouched and a row tap opens detail', (tester) async {
    final fetch = _Fetch(rows: [_conversation('c1', 'Morning Standup', DateTime(2026, 9, 12, 9))]);
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();

    final context = tester.element(find.byType(DayConversationsPage));
    expect(Provider.of<ConversationProvider>(context, listen: false).selectedStartDate, isNull);

    await tester.tap(find.byKey(const ValueKey('conversation_card')));
    await tester.pump();
    await tester.pump();
    expect(find.byType(ConversationDetailPage), findsOneWidget);

    Navigator.of(tester.element(find.byType(ConversationDetailPage))).pop();
    await tester.pump();
    await tester.pump(const Duration(seconds: 5));
  });

  testWidgets('next day is disabled when the page already shows today', (tester) async {
    await _pumpPage(tester, DateTime.now(), _Fetch().call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(tester.widget<OmiIconButton>(find.byKey(const ValueKey('day_next'))).onPressed, isNull);
  });

  testWidgets('a local provider update removes the row from the list', (tester) async {
    final fetch = _Fetch(rows: [
      _conversation('c1', 'First Chat', DateTime(2026, 9, 12, 9)),
      _conversation('c2', 'Second Chat', DateTime(2026, 9, 12, 10)),
    ]);
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.text('Second Chat'), findsOneWidget);

    final globalProvider =
        Provider.of<ConversationProvider>(tester.element(find.byType(DayConversationsPage)), listen: false);
    globalProvider.selectedStartDate = DateTime(2026, 6, 1);
    globalProvider.selectedEndDate = DateTime(2026, 6, 3);
    final provider = Provider.of<ConversationProvider>(tester.element(find.text('Second Chat')), listen: false);
    provider.conversations = provider.conversations.where((c) => c.id == 'c1').toList();
    provider.groupConversationsByDate();
    provider.notifyListeners();
    await tester.pump();
    expect(find.text('Second Chat'), findsNothing);
    expect(find.text('First Chat'), findsOneWidget);
    expect(globalProvider.selectedStartDate, DateTime(2026, 6, 1));
    expect(globalProvider.selectedEndDate, DateTime(2026, 6, 3));
  });

  testWidgets('a truncated page stops paging and its retry reloads the first page', (tester) async {
    final fetch = _Fetch(rows: [_conversation('c1', 'Kept Row', DateTime(2026, 9, 12, 9))])..truncated = true;
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('Kept Row'), findsOneWidget);
    expect(find.byKey(const ValueKey('search_partial_retry')), findsOneWidget);
    expect(find.byKey(const ValueKey('day_load_more')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('search_partial_retry')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(fetch.calls.last.offset, 0, reason: 'the partial retry reloads the first page, not a deeper offset');
  });

  testWidgets('an empty truncated answer is an error, not an empty day', (tester) async {
    final fetch = _Fetch()..truncated = true;
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.byType(OmiErrorState), findsOneWidget);
    expect(find.textContaining('No conversations on'), findsNothing);
  });

  testWidgets('a failed second page keeps rows and its retry appends without duplicates', (tester) async {
    final firstPage = List.generate(50, (i) => _conversation('p1-$i', 'Row $i', DateTime(2026, 9, 12, 9)));
    final secondPage = List.generate(50, (i) => _conversation('p2-$i', 'Page Two $i', DateTime(2026, 9, 12, 9)));
    final fetch = _Fetch()..pages = (offset) => offset == 0 ? firstPage : secondPage;
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byKey(const ValueKey('day_load_more')), 200);
    await tester.tap(find.byKey(const ValueKey('day_load_more')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(fetch.calls.last.offset, 50);

    fetch.ok = false;
    await tester.scrollUntilVisible(find.byKey(const ValueKey('day_load_more')), 200);
    await tester.tap(find.byKey(const ValueKey('day_load_more')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(fetch.calls.last.offset, 100);
    expect(find.byKey(const ValueKey('day_load_more_retry')), findsOneWidget);
    final provider = Provider.of<ConversationProvider>(tester.element(find.byType(ListView)), listen: false);
    expect(provider.conversations.length, 100, reason: 'earlier rows stay loaded after the failure');

    fetch.ok = true;
    fetch.truncated = false;
    fetch.pages = (offset) => [
          _conversation('p1-0', 'Row 0 dup', DateTime(2026, 9, 12, 9)),
          _conversation('p3-0', 'New Row', DateTime(2026, 9, 12, 10)),
        ];
    await tester.tap(find.byKey(const ValueKey('day_load_more_retry')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(provider.conversations.map((c) => c.id).last, 'p3-0', reason: 'the retried page appends its new rows');
    expect(provider.conversations.where((c) => c.id == 'p1-0'), hasLength(1),
        reason: 're-fetched ids are deduplicated');
    expect(provider.conversations, hasLength(101));
    expect(find.byKey(const ValueKey('day_load_more')), findsNothing, reason: 'a short page ends paging');
  });

  testWidgets('a full page followed by an empty page ends normally, not partial', (tester) async {
    final firstPage = List.generate(50, (i) => _conversation('p1-$i', 'Row $i', DateTime(2026, 9, 12, 9)));
    final fetch = _Fetch()..pages = (offset) => offset == 0 ? firstPage : [];
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(find.byKey(const ValueKey('day_load_more')), 200);
    await tester.tap(find.byKey(const ValueKey('day_load_more')));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(fetch.calls.last.offset, 50);
    final provider = Provider.of<ConversationProvider>(tester.element(find.byType(ListView)), listen: false);
    expect(provider.conversations, hasLength(50));
    expect(find.byKey(const ValueKey('day_load_more')), findsNothing);
    expect(find.byKey(const ValueKey('day_load_more_retry')), findsNothing);
    expect(find.byKey(const ValueKey('search_partial_retry')), findsNothing);
  });

  testWidgets('a pending page on a changed day leaves no latched footer spinner', (tester) async {
    final firstPage = List.generate(50, (i) => _conversation('p1-$i', 'Row $i', DateTime(2026, 9, 12, 9)));
    final gate = Completer<({List<ServerConversation> items, bool ok, bool truncated})>();
    final fetch = _Fetch()..pages = (offset) => offset == 0 ? firstPage : [];
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();

    fetch.gate = gate;
    await tester.scrollUntilVisible(find.byKey(const ValueKey('day_load_more')), 200);
    await tester.tap(find.byKey(const ValueKey('day_load_more')));
    await tester.pump();
    expect(find.byType(OmiSpinner), findsOneWidget);

    fetch.gate = null;
    fetch.pages = (offset) => [_conversation('c-prev', 'Previous Day Row', DateTime(2026, 9, 11, 9))];
    await tester.tap(find.byKey(const ValueKey('day_previous')));
    await tester.pump();
    gate.complete((items: firstPage, ok: true, truncated: false));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.byType(OmiSpinner), findsNothing);
    expect(find.text('Previous Day Row'), findsOneWidget);
  });

  testWidgets('a failed same-day refresh keeps the rows and shows a retry above them', (tester) async {
    final fetch = _Fetch(rows: [_conversation('c1', 'Visible Row', DateTime(2026, 9, 12, 9))]);
    await _pumpPage(tester, day, fetch.call);
    await tester.pump();
    await tester.pumpAndSettle();

    fetch.ok = false;
    final state = tester.state<RefreshIndicatorState>(find.byType(RefreshIndicator));
    unawaited(state.show());
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('Visible Row'), findsOneWidget);
    expect(find.byType(OmiErrorState), findsOneWidget);
    expect(fetch.calls.length, greaterThan(1));
  });
}
