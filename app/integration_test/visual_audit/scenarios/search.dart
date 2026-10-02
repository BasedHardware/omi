// Search: the overlay the Home header's search button drops in — browse tiles before typing,
// grouped results after, and a browsed folder.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/gen/people_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:provider/single_child_widget.dart';

import '../harness.dart';

const _page = 'lib/pages/search/global_search.dart (GlobalSearchPage)';

ServerConversation _conversation(String id, String title, String emoji, DateTime at, {String? snippet}) =>
    ServerConversation.fromJson({
      'id': id,
      'created_at': at.toUtc().toIso8601String(),
      'started_at': at.toUtc().toIso8601String(),
      'finished_at': at.add(const Duration(minutes: 12)).toUtc().toIso8601String(),
      'structured': {'title': title, 'overview': '', 'emoji': emoji, 'category': 'work'},
      'status': 'completed',
      'transcript_segments': [],
      if (snippet != null)
        'match_snippets': [
          {'text': snippet}
        ],
    });

/// Canned search results; counts on every tile.
class AuditSearchSource extends GlobalSearchSource {
  const AuditSearchSource({this.failTasks = false});

  /// Task search answers 503, as when one backend dependency is down.
  final bool failTasks;

  static final _now = DateTime(2026, 9, 29, 10, 12);

  @override
  Future<ApiResult<SearchOverview>> overview() async => const ApiSuccess(SearchOverview(
        starred: 12,
        folders: [
          SearchFolderCount(id: 'work', name: 'Work', icon: 'briefcase', color: '#3B82F6', count: 148),
          SearchFolderCount(id: 'personal', name: 'Personal', icon: 'heart', color: '#EC4899', count: 63),
        ],
        recaps: 41,
        memories: 312,
        people: 18,
        places: 27,
      ));

  @override
  Future<ConversationSearchResult> conversations(String query, {String? speakerId}) async =>
      ConversationSearchResult(currentPage: 1, totalPages: 1, outcome: ConversationSearchResultOutcome.success, items: [
        _conversation('c1', 'Device Connection Troubleshooting', '🔧', _now.subtract(const Duration(hours: 1)),
            snippet: 'It should show the bluetooth connection level'),
        _conversation('c2', 'Firmware update planning', '🛠️', _now.subtract(const Duration(days: 5)),
            snippet: 'Bluetooth reconnect after the OTA'),
        _conversation('c3', 'Weekly sync', '📅', _now.subtract(const Duration(days: 7)),
            snippet: 'BLE battery drain numbers'),
      ]);

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) async => [
        _conversation('w1', 'Rewrite, equity, and product polish', '🧭', _now.subtract(const Duration(hours: 3))),
        _conversation('w2', 'Omi reliability talk on stage', '🎤', _now.subtract(const Duration(days: 1))),
        _conversation('w3', 'Design review with Alex', '🎨', _now.subtract(const Duration(days: 2))),
        _conversation('w4', 'Hiring loop debrief', '🤝', _now.subtract(const Duration(days: 3))),
      ];

  @override
  Future<ApiResult<List<DailySummary>>> recaps(String query) async => ApiSuccess([
        DailySummary(
          id: 'r1',
          date: '2026-09-28',
          createdAt: DateTime.utc(2026, 9, 28, 22),
          headline: 'Omi reliability talk on stage',
          overview: 'Pendant Bluetooth drops during demos',
          dayEmoji: '🎤',
          stats: DayStats(totalConversations: 6, actionItemsCount: 2),
        ),
      ]);

  @override
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query) async => failTasks
      ? const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 503))
      : const ApiSuccess([
          ActionItemWithMetadata(id: 't1', description: 'Send the Bluetooth logs to firmware', completed: false),
        ]);

  @override
  Future<ApiResult<List<MemorySearchHit>>> memories(String query) async => const ApiSuccess(
      [MemorySearchHit(id: 'm1', content: 'Prefers the pendant over the phone mic for long meetings')]);
}

Future<void> _pumpSearch(
  AuditRun a, {
  String? query,
  AuditSearchSource source = const AuditSearchSource(),
  List<SingleChildWidget> extraProviders = const [],
}) async {
  await a.pump(
    GlobalSearchPage(initialQuery: query, source: source),
    scaffold: false,
    providers: [
      ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
      ...extraProviders,
    ],
  );
}

Person _auditPerson(
  String id,
  String name, {
  String confidence = 'unverified',
  bool pinned = false,
  Map<String, int> reasons = const {'never_confirmed': 1},
}) =>
    Person(
      id: id,
      name: name,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
      voiceReadiness: confidence == 'unverified' ? 'not_learned' : 'ready',
      confidence: confidence,
      pinned: pinned,
      confidenceReasons: [
        for (final entry in reasons.entries) GeneratedPersonConfidenceReason(code: entry.key, count: entry.value),
      ],
    );

final searchScenarios = <AuditScenario>[
  AuditScenario(
    id: 'search-browse',
    title: 'Search, before typing: browse tiles and recent searches',
    page: _page,
    state: 'Canned overview counts; two folders; two recent searches',
    prefs: {
      'globalSearchRecentQueries': ['bluetooth', 'Tristan'],
    },
    run: (a) async {
      await _pumpSearch(a);
      expect(find.byKey(const ValueKey('search_tile_starred')), findsOneWidget);
      await a.shot('Open search from the Home header');
    },
  ),
  AuditScenario(
    id: 'search-drop',
    title: 'Search dropping in from the top',
    page: 'lib/pages/search/global_search.dart (SearchDropTransition)',
    state: 'The drop at 55% of its run, over a plain page',
    run: (a) async {
      await a.pump(
        const Stack(children: [
          Positioned.fill(child: ColoredBox(color: Color(0xFFF2F2F7))),
          SearchDropTransition(
            animation: AlwaysStoppedAnimation(0.55),
            child: GlobalSearchPage(source: AuditSearchSource()),
          ),
        ]),
        scaffold: false,
        providers: [ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[]))],
      );
      await a.shot('Mid-drop: the panel slides down while the page dims');
    },
  ),
  AuditScenario(
    id: 'search-results',
    title: 'Search results grouped by kind',
    page: _page,
    state: '"bluetooth" typed; one recap, three conversations, one task and one memory',
    run: (a) async {
      await _pumpSearch(a, query: 'bluetooth');
      expect(find.text('Device Connection Troubleshooting'), findsOneWidget);
      await a.shot('Type "bluetooth"');
    },
  ),
  AuditScenario(
    id: 'search-partial',
    title: 'Search results when one kind fails to load',
    page: _page,
    state: '"bluetooth" typed; task search answers 503, the rest succeed',
    run: (a) async {
      await _pumpSearch(a, query: 'bluetooth', source: const AuditSearchSource(failTasks: true));
      expect(find.byKey(const ValueKey('search_partial_retry')), findsOneWidget);
      await a.shot('Type "bluetooth" while task search is down');
    },
  ),
  AuditScenario(
    id: 'search-people',
    title: 'People opened from its tile: the shared People list, filtered by the search field',
    page: _page,
    state: 'The People tile tapped; five people (one pinned, three unsure), then "a" typed',
    run: (a) async {
      final people = PeopleProvider(
        setPinned: (_, __) async => true,
        loadPeople: () async => [
          _auditPerson('p-maya', 'Maya Chen', confidence: 'confirmed', pinned: true, reasons: {'manual_labels': 6}),
          _auditPerson('p-sam', 'Sam Okafor', confidence: 'likely', reasons: {'card_picks': 2}),
          _auditPerson('p-because', 'Because', reasons: {'auto_unconfirmed': 3}),
          _auditPerson('p-american', 'American', reasons: {'auto_corrected': 1}),
          _auditPerson('p-cs', 'Cs'),
        ],
      );
      await _pumpSearch(a, extraProviders: [ChangeNotifierProvider<PeopleProvider>.value(value: people)]);
      await a.tap(find.byKey(const ValueKey('search_tile_people')));
      expect(find.byKey(const ValueKey('search_people_list')), findsOneWidget);
      await a.shot('Tap the People tile');
      await a.tester.enterText(
          find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)),
          'a');
      await a.settle();
      await a.shot('Type "a" into the search field', step: 'query');
    },
  ),
  AuditScenario(
    id: 'search-folder',
    title: 'A folder opened from its tile',
    page: _page,
    state: 'The Work tile tapped; four conversations in it',
    run: (a) async {
      await _pumpSearch(a);
      await a.tap(find.byKey(const ValueKey('search_tile_folder_work')));
      expect(find.text('Design review with Alex'), findsOneWidget);
      await a.shot('Tap the Work tile');
    },
  ),
];
