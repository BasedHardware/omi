import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/search/search_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';

/// Search everything (Rev 3): one field over conversations (the server's search), memories and
/// to-dos, scope chips, the last searches, and Ask Omi when nothing matches.

class _Memories extends ChangeNotifier implements MemoriesProvider {
  _Memories(this.memories);
  @override
  final List<Memory> memories;
  @override
  Future<void> init() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Tasks extends ChangeNotifier implements ActionItemsProvider {
  _Tasks(this.actionItems);
  @override
  final List<ActionItemWithMetadata> actionItems;
  @override
  Future<void> refreshActionItems() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Memory _memory(String content) => Memory(
      id: content,
      uid: 'user-1',
      content: content,
      category: MemoryCategory.manual,
      createdAt: DateTime.utc(2026, 9, 20),
      updatedAt: DateTime.utc(2026, 9, 20),
      visibility: MemoryVisibility.private,
    );

ActionItemWithMetadata _task(String description) => wire.GeneratedActionItemResponse(
      id: description,
      description: description,
      completed: false,
      createdAt: DateTime.utc(2026, 9, 20),
      updatedAt: DateTime.utc(2026, 9, 20),
    );

void main() {
  final en = lookupAppLocalizations(const Locale('en'));
  final queries = <String>[];

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    queries.clear();
  });

  Future<void> pumpSearch(WidgetTester tester) async {
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<MemoriesProvider>.value(
            value: _Memories([_memory('Battery lasts two days on the pendant'), _memory('Prefers morning meetings')])),
        ChangeNotifierProvider<ActionItemsProvider>.value(
            value: _Tasks([_task('Pull battery reports'), _task('Call Chitapa')])),
      ],
      child: MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        locale: const Locale('en'),
        home: SearchPage(
          searchConversations: (query) async {
            queries.add(query);
            return query.contains('battery')
                ? [
                    ServerConversation(
                      id: 'c1',
                      createdAt: DateTime.utc(2026, 9, 24, 14, 42),
                      structured: Structured('App UX and battery', 'Battery drain reports from two users'),
                    ),
                  ]
                : const [];
          },
        ),
      ),
    ));
    await tester.pumpAndSettle();
  }

  Future<void> type(WidgetTester tester, String text) async {
    await tester.enterText(find.byKey(const ValueKey('search_field')), text);
    await tester.pump(const Duration(milliseconds: 350)); // the debounce
    await tester.pumpAndSettle();
  }

  testWidgets('before typing: Ask Omi with a suggestion; no recent searches yet', (tester) async {
    await pumpSearch(tester);
    expect(find.text(en.searchEverything), findsOneWidget);
    expect(find.text(en.askOmi), findsOneWidget);
    expect(find.text(en.searchAskSuggestion), findsOneWidget);
    expect(find.text(en.recentSearches), findsNothing);
    for (final scope in SearchScope.values) {
      expect(find.byKey(ValueKey('search_scope_${scope.name}')), findsOneWidget);
    }
  });

  testWidgets('a word finds conversations, memories and to-dos, and the scope chips narrow it', (tester) async {
    await pumpSearch(tester);
    await type(tester, 'battery');
    expect(queries, ['battery'], reason: 'one server search after the debounce');
    expect(find.text(en.searchResultsCount(3)), findsOneWidget);
    expect(find.textContaining('Battery drain reports'), findsOneWidget, reason: 'the conversation overview');
    expect(find.textContaining('lasts two days', findRichText: true), findsOneWidget);
    expect(find.textContaining('reports', findRichText: true), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('search_scope_tasks')));
    await tester.pumpAndSettle();
    expect(find.text(en.searchResultsCount(1)), findsOneWidget);
    expect(find.textContaining('lasts two days', findRichText: true), findsNothing);

    await tester.tap(find.byKey(const ValueKey('search_scope_memories')));
    await tester.pumpAndSettle();
    expect(find.text(en.searchResultsCount(1)), findsOneWidget);
    expect(find.textContaining('lasts two days', findRichText: true), findsOneWidget);
  });

  testWidgets('nothing found offers Ask Omi instead', (tester) async {
    await pumpSearch(tester);
    await type(tester, 'zebra');
    expect(find.byKey(const ValueKey('search_nothing_found')), findsOneWidget);
    expect(find.text(en.nothingFound), findsOneWidget);
    expect(find.byKey(const ValueKey('search_ask_instead')), findsOneWidget);
  });

  testWidgets('a submitted search is remembered and can be run again from Recent', (tester) async {
    await pumpSearch(tester);
    await type(tester, 'battery');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    await type(tester, '');
    expect(find.text(en.recentSearches), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('search_recent_battery')));
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pumpAndSettle();
    expect(find.text(en.searchResultsCount(3)), findsOneWidget);
  });
}
