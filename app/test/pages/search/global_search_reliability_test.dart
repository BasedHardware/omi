import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/ui/ui.dart';

class _ScriptedSource extends GlobalSearchSource {
  Future<ConversationSearchResult> Function(String query)? onConversations;
  Future<ApiResult<List<DailySummary>>> Function(String query)? onRecaps;
  Future<ApiResult<List<ActionItemWithMetadata>>> Function(String query)? onTasks;
  Future<ApiResult<List<MemorySearchHit>>> Function(String query)? onMemories;

  static const _empty = ConversationSearchResult(
      items: [], currentPage: 1, totalPages: 1, outcome: ConversationSearchResultOutcome.success);

  @override
  Future<ApiResult<SearchOverview>> overview() async =>
      const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404));

  @override
  Future<ConversationSearchResult> conversations(String query,
          {String? speakerId, DateTime? startDate, DateTime? endDate}) =>
      onConversations?.call(query) ?? Future.value(_empty);

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) async => const [];

  @override
  Future<ApiResult<List<DailySummary>>> recaps(String query) =>
      onRecaps?.call(query) ?? Future.value(const ApiSuccess(<DailySummary>[]));

  @override
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query) =>
      onTasks?.call(query) ?? Future.value(const ApiSuccess(<ActionItemWithMetadata>[]));

  @override
  Future<ApiResult<List<MemorySearchHit>>> memories(String query) =>
      onMemories?.call(query) ?? Future.value(const ApiSuccess(<MemorySearchHit>[]));
}

ServerConversation _conversation(String id, String title) => ServerConversation.fromJson({
      'id': id,
      'created_at': DateTime(2026, 9, 28, 10).toUtc().toIso8601String(),
      'started_at': DateTime(2026, 9, 28, 10).toUtc().toIso8601String(),
      'finished_at': DateTime(2026, 9, 28, 10, 12).toUtc().toIso8601String(),
      'structured': {'title': title, 'overview': '', 'emoji': '', 'category': 'work'},
      'status': 'completed',
      'transcript_segments': [],
    });

ConversationSearchResult _conversations(List<ServerConversation> items) => ConversationSearchResult(
    items: items, currentPage: 1, totalPages: 1, outcome: ConversationSearchResultOutcome.success);

Future<void> _pumpSearch(WidgetTester tester, GlobalSearchSource source, {String? initialQuery}) {
  return tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
    ],
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: GlobalSearchPage(initialQuery: initialQuery, source: source)),
    ),
  ));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a hung kind settles at the deadline: error state, no spinner', (tester) async {
    final source = _ScriptedSource()..onTasks = (_) => Completer<ApiResult<List<ActionItemWithMetadata>>>().future;
    await _pumpSearch(tester, source, initialQuery: 'bluetooth');
    await tester.pump();

    expect(find.byType(OmiSpinner), findsOneWidget, reason: 'searching indicator while the kind hangs');

    await tester.pump(const Duration(seconds: 16));
    await tester.pump();

    expect(find.byType(OmiErrorState), findsOneWidget, reason: 'no rows at deadline shows the error state');
    expect(find.byType(OmiSpinner), findsNothing, reason: 'the search must not wait forever');
  });

  testWidgets('completed rows survive a hung kind: results stay, partial retry offered', (tester) async {
    final source = _ScriptedSource();
    source.onConversations = (_) async => _conversations([_conversation('c1', 'Device Connection Troubleshooting')]);
    source.onTasks = (_) => Completer<ApiResult<List<ActionItemWithMetadata>>>().future;
    await _pumpSearch(tester, source, initialQuery: 'bluetooth');
    await tester.pump();
    await tester.pump(const Duration(seconds: 16));
    await tester.pump();

    expect(find.text('Device Connection Troubleshooting'), findsOneWidget, reason: 'finished rows stay visible');
    expect(find.byType(OmiErrorState), findsNothing, reason: 'rows present means partial notice, not error state');
    expect(find.byKey(const ValueKey('search_partial_retry')), findsOneWidget, reason: 'partial retry is offered');
    expect(find.byType(OmiSpinner), findsNothing);
  });

  testWidgets('an unexpected source throw shows the error state; retry clears it', (tester) async {
    var throwSource = true;
    final source = _ScriptedSource()
      ..onConversations = (_) async {
        if (throwSource) throw StateError('source blew up');
        return _conversations([_conversation('c1', 'Device Connection Troubleshooting')]);
      };
    await _pumpSearch(tester, source, initialQuery: 'bluetooth');
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.byType(OmiErrorState), findsOneWidget, reason: 'a thrown source lands on the error path');

    throwSource = false;
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();

    expect(find.byType(OmiErrorState), findsNothing);
    expect(find.text('Device Connection Troubleshooting'), findsOneWidget);
  });

  testWidgets('editing a query keeps the page searching through the debounce window', (tester) async {
    final source = _ScriptedSource()
      ..onConversations = (_) async => _conversations([_conversation('c1', 'Device Connection Troubleshooting')]);
    await _pumpSearch(tester, source, initialQuery: 'bluetooth');
    await tester.pumpAndSettle();

    expect(find.text('Device Connection Troubleshooting'), findsOneWidget);

    await tester.enterText(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)),
        'bluetooh');
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(OmiSpinner), findsOneWidget, reason: 'the debounce window is a pending search, not a result');
    expect(find.text('No results found'), findsNothing,
        reason: 'cleared results must not render an empty state before the request starts');

    await tester.pumpAndSettle();
    expect(find.text('Device Connection Troubleshooting'), findsOneWidget);
  });

  testWidgets('a newer query is not clobbered by the previous run finishing late', (tester) async {
    final staleCompleter = Completer<ConversationSearchResult>();
    final source = _ScriptedSource()
      ..onConversations = (query) =>
          query == 'old' ? staleCompleter.future : Future.value(_conversations([_conversation('c-new', 'New Answer')]));
    await _pumpSearch(tester, source, initialQuery: 'old');
    await tester.pump();

    await tester.enterText(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)),
        'new');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.text('New Answer'), findsOneWidget);

    staleCompleter.complete(_conversations([_conversation('c-old', 'Stale Answer')]));
    await tester.pumpAndSettle();

    expect(find.text('Stale Answer'), findsNothing, reason: 'late completions never overwrite newer results');
    expect(find.text('New Answer'), findsOneWidget);
  });

  testWidgets('clearing the field discards a pending run entirely', (tester) async {
    final staleCompleter = Completer<ConversationSearchResult>();
    final source = _ScriptedSource()..onConversations = (_) => staleCompleter.future;
    await _pumpSearch(tester, source, initialQuery: 'old');
    await tester.pump();

    await tester.enterText(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)), '');
    await tester.pump();
    staleCompleter.complete(_conversations([_conversation('c-old', 'Stale Answer')]));
    await tester.pumpAndSettle();

    expect(find.text('Stale Answer'), findsNothing);
    expect(find.byType(OmiSpinner), findsNothing, reason: 'a cleared field is not still searching');
  });

  testWidgets('a source completing after the deadline cannot rewrite the committed state', (tester) async {
    final lateTasks = Completer<ApiResult<List<ActionItemWithMetadata>>>();
    final source = _ScriptedSource();
    source.onConversations = (_) async => _conversations([_conversation('c1', 'Device Connection Troubleshooting')]);
    source.onTasks = (_) => lateTasks.future;
    await _pumpSearch(tester, source, initialQuery: 'bluetooth');
    await tester.pump();
    await tester.pump(const Duration(seconds: 16));
    await tester.pump();

    expect(find.text('Device Connection Troubleshooting'), findsOneWidget);
    expect(find.byKey(const ValueKey('search_partial_retry')), findsOneWidget);

    lateTasks.complete(const ApiSuccess(<ActionItemWithMetadata>[]));
    await tester.pumpAndSettle();

    expect(find.text('Device Connection Troubleshooting'), findsOneWidget,
        reason: 'a post-deadline completion must not rewrite settled rows');
    expect(find.byKey(const ValueKey('search_partial_retry')), findsOneWidget,
        reason: 'the committed partial flag survives a late success');
  });

  testWidgets('a fresh query shows the searching state during the debounce window', (tester) async {
    final source = _ScriptedSource();
    await _pumpSearch(tester, source);
    await tester.pumpAndSettle();

    await tester.enterText(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)),
        'bluetooth');
    await tester.pump();

    expect(find.byType(OmiSpinner), findsOneWidget,
        reason: 'a pending debounced search already reads as searching, not empty');
    expect(find.text('No results found'), findsNothing);

    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
  });

  test('conversation search carries a 15s deadline with zero retries', () {
    final source = File('lib/backend/http/api/conversations.dart').readAsStringSync();
    final fn = RegExp(r'searchConversationsServerResult[\s\S]*?makeApiCall\(([\s\S]*?)\);').firstMatch(source);
    expect(fn, isNotNull, reason: 'searchConversationsServerResult must go through makeApiCall');
    expect(fn!.group(1), contains('timeout: const Duration(seconds: 15)'));
    expect(fn.group(1), contains('retries: 0'));
  });
}
