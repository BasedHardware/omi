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

const _coffeeWithSam = 'Coffee with Sam after work';
const _coffeeBeans = 'Buys coffee beans from the corner shop';
const _gym = 'Gym at 7am before work';
const _reading = 'Reads before bed';

Memory _memory(String id, String content, MemoryCategory category) => Memory(
      id: id,
      uid: 'global-search-user',
      content: content,
      category: category,
      createdAt: DateTime(2026, 10, 1),
      updatedAt: DateTime(2026, 10, 1),
      visibility: MemoryVisibility.private,
    );

List<Memory> _memories() => [
      _memory('mem-coffee-sam', _coffeeWithSam, MemoryCategory.system),
      _memory('mem-coffee-beans', _coffeeBeans, MemoryCategory.manual),
      _memory('mem-gym', _gym, MemoryCategory.system),
      _memory('mem-reading', _reading, MemoryCategory.manual),
    ];

MemoriesProvider _memoriesProvider() => MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult(_memories(), true),
    );

/// Memory search answers like `GET /memory/search`, which has no category filter: every memory that
/// holds a query word is found, whatever its category. Every other kind finds nothing.
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
  final memories = _memoriesProvider();
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
    // On an earlier visit the user left only Manual checked in the Memories filter, which is saved.
    SharedPreferences.setMockInitialValues({
      'memories_filter_categories': <String>['manual'],
    });
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('a memory from a category the saved filter leaves out is listed when Memories opens', (tester) async {
    final memories = await _pumpSearch(tester, 'coffee');
    // Search has no category filter, so it finds the System memory.
    expect(find.text(_coffeeWithSam), findsOneWidget);

    await tester.tap(find.text(_coffeeWithSam));
    await tester.pumpAndSettle();

    expect(find.byType(MemoriesPage), findsOneWidget);
    expect(_listedInMemories(_coffeeWithSam), findsOneWidget, reason: 'the memory that was tapped is in the list');
    expect(_listedInMemories(_coffeeBeans), findsOneWidget);
    expect(_listedInMemories(_gym), findsNothing);
    expect(_listedInMemories(_reading), findsNothing);
    expect(memories.searchQuery, 'coffee');
    // Opening the result leaves the saved filter as the user set it.
    expect(memories.selectedCategories, {MemoryCategory.manual});
  });

  test('a search looks in every category, and the saved filter narrows the list again once it is cleared', () async {
    final memories = _memoriesProvider();
    addTearDown(memories.dispose);

    // What the Memories page does when it opens: restore the saved filter, then load.
    await memories.init();
    expect(memories.selectedCategories, {MemoryCategory.manual});
    expect(memories.filteredMemories.map((memory) => memory.content), unorderedEquals([_coffeeBeans, _reading]));

    memories.setSearchQuery('coffee');
    expect(
      memories.filteredMemories.map((memory) => memory.content),
      unorderedEquals([_coffeeWithSam, _coffeeBeans]),
      reason: 'a System memory matching the search is listed although only Manual is checked',
    );

    memories.setSearchQuery('');
    expect(memories.filteredMemories.map((memory) => memory.content), unorderedEquals([_coffeeBeans, _reading]));
  });
}
