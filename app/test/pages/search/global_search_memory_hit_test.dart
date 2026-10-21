import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const _coffee = 'Coffee with Sam after work';
const _gym = 'Gym at 7am before work';
const _coffeeGym = 'Coffee gym on the corner opens at 6';
const _reading = 'Reads before bed';

Memory _memory(String id, String content) => Memory(
      id: id,
      uid: 'global-search-user',
      content: content,
      category: MemoryCategory.manual,
      createdAt: DateTime(2026, 10, 1),
      updatedAt: DateTime(2026, 10, 1),
      visibility: MemoryVisibility.private,
    );

List<Memory> _memories() => [
      _memory('mem-coffee', _coffee),
      _memory('mem-gym', _gym),
      _memory('mem-coffee-gym', _coffeeGym),
      _memory('mem-reading', _reading),
    ];

/// Memory search answers like `GET /memory/search`: a memory is found when it holds any one word of
/// the query, not the whole query. Every other kind finds nothing.
class _MemorySearchSource extends GlobalSearchSource {
  @override
  Future<ApiResult<SearchOverview>> overview() async =>
      const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404));

  @override
  Future<ConversationSearchResult> conversations(String query,
          {String? speakerId, DateTime? startDate, DateTime? endDate}) async =>
      const ConversationSearchResult(
          items: [], currentPage: 1, totalPages: 1, outcome: ConversationSearchResultOutcome.success);

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) async => const [];

  @override
  Future<ApiResult<List<DailySummary>>> recaps(String query) async => const ApiSuccess(<DailySummary>[]);

  @override
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query) async =>
      const ApiSuccess(<ActionItemWithMetadata>[]);

  @override
  Future<ApiResult<List<MemorySearchHit>>> memories(String query) async {
    final words = query.toLowerCase().split(' ');
    return ApiSuccess([
      for (final memory in _memories())
        if (words.any((word) => memory.content.toLowerCase().contains(word)))
          MemorySearchHit(id: memory.id, content: memory.content),
    ]);
  }
}

/// Global Search over the app-wide providers, as in main.dart, so the Memories page it opens shares
/// the same [MemoriesProvider]. Returns that provider once the search has shown its results.
Future<MemoriesProvider> _pumpSearch(WidgetTester tester, String query) async {
  final memories = MemoriesProvider(
    fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
        GetMemoriesResult(_memories(), true),
  );
  addTearDown(memories.dispose);
  final home = HomeProvider();
  addTearDown(home.dispose);
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
      ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
      ChangeNotifierProvider<HomeProvider>.value(value: home),
    ],
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: GlobalSearchPage(initialQuery: query, source: _MemorySearchSource())),
    ),
  ));
  await tester.pump();
  await tester.pumpAndSettle();
  return memories;
}

/// A memory row on the Memories page (Global Search stays mounted underneath it).
Finder _listedInMemories(String content) =>
    find.descendant(of: find.byType(MemoriesPage), matching: find.text(content));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('a memory found by one word of the query is listed when Memories opens', (tester) async {
    final memories = await _pumpSearch(tester, 'coffee gym');
    // Found for "coffee" alone: the memory does not hold the whole query.
    expect(find.text(_coffee), findsOneWidget);

    await tester.tap(find.text(_coffee));
    await tester.pumpAndSettle();

    expect(find.byType(MemoriesPage), findsOneWidget);
    expect(_listedInMemories(_coffee), findsOneWidget, reason: 'the memory that was tapped is in the list');
    expect(memories.searchQuery, 'coffee');
    expect(_listedInMemories(_coffeeGym), findsOneWidget);
    expect(_listedInMemories(_gym), findsNothing);
    expect(_listedInMemories(_reading), findsNothing);
  });

  testWidgets('a memory holding the whole query keeps the whole query as the filter', (tester) async {
    final memories = await _pumpSearch(tester, 'coffee gym');

    await tester.tap(find.text(_coffeeGym));
    await tester.pumpAndSettle();

    expect(_listedInMemories(_coffeeGym), findsOneWidget);
    expect(memories.searchQuery, 'coffee gym');
    expect(_listedInMemories(_coffee), findsNothing);
    expect(_listedInMemories(_gym), findsNothing);
  });

  testWidgets('a memory holding several query words apart is filtered by the longest one', (tester) async {
    final memories = await _pumpSearch(tester, 'sam coffee');

    await tester.tap(find.text(_coffee));
    await tester.pumpAndSettle();

    expect(_listedInMemories(_coffee), findsOneWidget);
    expect(memories.searchQuery, 'coffee');
    expect(_listedInMemories(_coffeeGym), findsOneWidget);
    expect(_listedInMemories(_gym), findsNothing);
  });
}
