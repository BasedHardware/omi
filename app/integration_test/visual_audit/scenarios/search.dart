// Search: the overlay the Home header's search button drops in — browse tiles before typing,
// grouped results after, and a browsed folder.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/providers/folder_provider.dart';

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
  const AuditSearchSource();

  static final _now = DateTime(2026, 9, 29, 10, 12);

  @override
  Future<SearchOverview?> overview() async => const SearchOverview(
        starred: 12,
        folders: [
          SearchFolderCount(id: 'work', name: 'Work', icon: 'briefcase', color: '#3B82F6', count: 148),
          SearchFolderCount(id: 'personal', name: 'Personal', icon: 'heart', color: '#EC4899', count: 63),
        ],
        recaps: 41,
        memories: 312,
        people: 18,
        places: 27,
      );

  @override
  Future<List<ServerConversation>> conversations(String query, {String? speakerId}) async => [
        _conversation('c1', 'Device Connection Troubleshooting', '🔧', _now.subtract(const Duration(hours: 1)),
            snippet: 'It should show the bluetooth connection level'),
        _conversation('c2', 'Firmware update planning', '🛠️', _now.subtract(const Duration(days: 5)),
            snippet: 'Bluetooth reconnect after the OTA'),
        _conversation('c3', 'Weekly sync', '📅', _now.subtract(const Duration(days: 7)),
            snippet: 'BLE battery drain numbers'),
      ];

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) async => [
        _conversation('w1', 'Rewrite, equity, and product polish', '🧭', _now.subtract(const Duration(hours: 3))),
        _conversation('w2', 'Omi reliability talk on stage', '🎤', _now.subtract(const Duration(days: 1))),
        _conversation('w3', 'Design review with Alex', '🎨', _now.subtract(const Duration(days: 2))),
        _conversation('w4', 'Hiring loop debrief', '🤝', _now.subtract(const Duration(days: 3))),
      ];

  @override
  Future<List<DailySummary>> recaps(String query) async => [
        DailySummary(
          id: 'r1',
          date: '2026-09-28',
          createdAt: DateTime.utc(2026, 9, 28, 22),
          headline: 'Omi reliability talk on stage',
          overview: 'Pendant Bluetooth drops during demos',
          dayEmoji: '🎤',
          stats: DayStats(totalConversations: 6, actionItemsCount: 2),
        ),
      ];

  @override
  Future<List<ActionItemWithMetadata>> tasks(String query) async => [
        const ActionItemWithMetadata(id: 't1', description: 'Send the Bluetooth logs to firmware', completed: false),
      ];

  @override
  Future<List<MemorySearchHit>> memories(String query) async =>
      const [MemorySearchHit(id: 'm1', content: 'Prefers the pendant over the phone mic for long meetings')];

  @override
  Future<List<Person>> people() async => [
        for (final name in ['Alex', 'Tristan', 'John'])
          Person(id: name, name: name, createdAt: DateTime(2026, 1, 1), updatedAt: DateTime(2026, 1, 1)),
      ];
}

Future<void> _pumpSearch(AuditRun a, {String? query}) async {
  await a.pump(
    GlobalSearchPage(initialQuery: query, source: const AuditSearchSource()),
    scaffold: false,
    providers: [ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[]))],
  );
}

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
