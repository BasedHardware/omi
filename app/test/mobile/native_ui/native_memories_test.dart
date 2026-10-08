import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/pages/memories/widgets/memory_item.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

final _en = lookupAppLocalizations(const Locale('en'));

/// The page's provider with its state set directly; network calls are never made.
class _Memories extends MemoriesProvider {
  _Memories(this.items);

  List<Memory> items;
  String query = '';
  bool device = false, partial = false, belief = false, history = false, truncated = false, more = false;
  final using = <String>{}, reverting = <String>{}, revertable = <String>{};
  final deleted = <String>[];
  final calls = <String>[];
  var loads = 0, confirmed = 0;

  @override
  List<Memory> get memories => items;
  @override
  List<Memory> get filteredMemories => [
        for (final memory in items)
          if (!device && memory.content.toLowerCase().contains(query)) memory
      ];
  @override
  bool get loading => false;
  @override
  String get searchQuery => query;
  @override
  void setSearchQuery(String value) {
    query = value;
    notifyListeners();
  }

  @override
  bool get filterThisDeviceOnly => device;
  @override
  bool get showPartialLoadError => partial;
  @override
  bool get showLoadError => false;
  @override
  bool get memoryBeliefEnabled => belief;
  @override
  bool get showHistory => history;
  @override
  bool get ledgerHistoryTruncated => truncated;
  @override
  bool get ledgerHistoryHasMore => more;
  @override
  bool isApplyingMemoryUse(String memoryId) => using.contains(memoryId);
  @override
  bool isRevertingMemory(String memoryId) => reverting.contains(memoryId);
  @override
  bool canRevertSupersededFact(Memory memory) => revertable.contains(memory.id);
  @override
  Future<void> init() async {}
  @override
  Future<void> loadMemories({int limit = 100}) async => loads++;
  @override
  Future<void> deleteMemory(Memory memory) async => deleted.add(memory.id);
  @override
  Future<void> confirmPendingDeletion({String? id}) async => confirmed++;
  @override
  Future<bool> reviewMemory(Memory memory, bool value) async {
    calls.add('review:${memory.id}:$value');
    return true;
  }

  @override
  Future<bool> setMemoryUse(Memory memory, MemoryUseAction action) async {
    calls.add('use:${memory.id}:${action.apiValue}');
    return true;
  }

  @override
  Future<bool> revertSupersededFact(Memory memory) async {
    calls.add('revert:${memory.id}');
    return true;
  }

  @override
  Future<bool> restoreLastDeletedMemory({String? id}) async => true;
}

class _Usage extends UsageProvider {
  _Usage(this.subscriptionUI);
  final bool subscriptionUI;

  @override
  bool get showSubscriptionUI => subscriptionUI;
}

class _Pushes extends NavigatorObserver {
  final routes = <Route<dynamic>>[];

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) => routes.add(route);
}

Memory _memory(
  String id,
  String content, {
  bool locked = false,
  bool baseline = false,
  String? conversationId,
  KnowledgeLedgerKind? ledgerKind,
  String? slot,
  String? supersededBy,
  DateTime? invalidAt,
  bool? userReview,
  bool? suppressed,
}) =>
    Memory(
      id: id,
      uid: 'native-test-owner',
      content: content,
      category: MemoryCategory.system,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
      visibility: MemoryVisibility.private,
      isLocked: locked,
      isBaseline: baseline,
      conversationId: conversationId,
      ledgerSchemaVersion: ledgerKind == null ? null : 'knowledge_ledger.v1',
      ledgerKind: ledgerKind,
      ledgerSlot: slot,
      supersededBy: supersededBy,
      invalidAt: invalidAt,
      userReview: userReview,
      intentBacked: ledgerKind != null,
      arguments: suppressed == null
          ? null
          : {
              'memory_use': {'suppressed': suppressed}
            },
    );

Map<String, dynamic> _graphFixture() => {
      'nodes': [
        {'id': 'ada', 'label': 'Ada', 'node_type': 'person'},
        {'id': 'paris', 'label': 'Paris', 'node_type': 'place'},
      ],
      'edges': [
        {'source_id': 'ada', 'target_id': 'paris', 'label': 'visited'},
      ],
    };

Widget _app(_Memories memories, Widget home,
        {bool subscriptionUI = true, List<NavigatorObserver> observers = const []}) =>
    MultiProvider(
      providers: [
        ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
        ChangeNotifierProvider<UsageProvider>(create: (_) => _Usage(subscriptionUI)),
      ],
      child: observers.isEmpty
          ? NativeTestHost.app(home)
          : NativeTestHost.app(Navigator(
              observers: observers,
              onGenerateRoute: (_) => MaterialPageRoute<void>(builder: (_) => home),
            )),
    );

/// The last snapshot's sections as id → row ids, and its rows by id.
(Map<String, List<String>>, Map<String, Map>) _published(NativeTestHost host) {
  final view = host.created.first;
  final snapshot = host.calls.lastWhere((call) => call.$1 == view && call.$2.method == 'update').$2.arguments as Map;
  final sections = <String, List<String>>{};
  final rows = <String, Map>{};
  for (final section in (snapshot['sections'] as List).cast<Map>()) {
    sections[section['id'] as String] = [
      for (final row in (section['rows'] as List).cast<Map>()) row['id'] as String,
    ];
    for (final row in (section['rows'] as List).cast<Map>()) {
      rows[row['id'] as String] = row;
    }
  }
  for (final row in (snapshot['toolbar'] as List).cast<Map>()) {
    rows[row['id'] as String] = row;
  }
  return (sections, rows);
}

Future<void> _send(NativeTestHost host, String id, [Object? value]) =>
    host.sendFromNative(host.created.first, MethodCall('action', {'id': id, 'value': value}));

/// Builds [memory]'s native row with the page's providers in scope.
Future<NativeRow> _row(WidgetTester tester, _Memories memories, Memory memory,
    {bool subscriptionUI = true, void Function(Memory)? onEdit}) async {
  late NativeRow row;
  await tester.pumpWidget(_app(memories, subscriptionUI: subscriptionUI, Builder(builder: (context) {
    row = memoryNativeRow(context, memory, memories, onEdit: (_, edited, __) => onEdit?.call(edited));
    return const SizedBox();
  })));
  return row;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('memory rows', () {
    testWidgets('an editable memory opens, edits, deletes and swipes to delete', (tester) async {
      final memory = _memory('m1', 'Likes tea', baseline: true);
      final row = await _row(tester, _Memories([memory]), memory);
      expect([row.id, row.title, row.kind], ['memory_m1', 'Likes tea', 'navigation']);
      expect(row.options.keys, ['open', 'edit', 'delete']);
      expect(row.swipeTrailing, ['delete']);
      expect(row.subtitle, _en.baselineMemory);
      expect(row.valid, isTrue);
    });

    testWidgets('a locked memory carries only the upgrade title', (tester) async {
      final memory = _memory('m2', 'Secret plan', locked: true, conversationId: 'c1', slot: 'plan');
      final row = await _row(tester, _Memories([memory]), memory);
      expect(row.title, _en.upgradeToUnlimited);
      expect([row.options, row.subtitle, row.swipeTrailing], [isEmpty, '', isEmpty]);
      expect(row.projection.toString(), isNot(contains('Secret plan')));
    });

    testWidgets('a reviewable ledger fact omits the verdict already cast and links its conversation', (tester) async {
      final memory = _memory('f1', 'Lives in Brooklyn',
          ledgerKind: KnowledgeLedgerKind.fact, slot: 'home_city', userReview: true, conversationId: 'c1');
      final row = await _row(tester, _Memories([memory]), memory);
      expect(row.symbol, 'person');
      expect(row.options.keys, ['open', 'edit', 'delete', 'open_conversation', 'review_wrong']);
      expect(row.subtitle, 'home_city');
    });

    testWidgets('belief use offers allow or suppress, and an in-flight change disables the row', (tester) async {
      final suppressed = _memory('u1', 'Prefers trains', suppressed: true);
      final allowed = _memory('u2', 'Runs daily', suppressed: false);
      final memories = _Memories([suppressed, allowed])..belief = true;
      expect((await _row(tester, memories, suppressed)).options.keys, contains('use_allow'));
      expect((await _row(tester, memories, allowed)).options.keys, contains('use_suppress'));

      memories.using.add('u2');
      final inFlight = await _row(tester, memories, allowed);
      expect(inFlight.options.keys, isNot(anyOf(contains('use_allow'), contains('use_suppress'))));
      expect(inFlight.projection['enabled'], isFalse);
    });

    testWidgets('a superseded fact is read-only and offers revert unless one is running', (tester) async {
      final memory = _memory('s1', 'Lived in Boston',
          ledgerKind: KnowledgeLedgerKind.fact, supersededBy: 'f1', invalidAt: DateTime.utc(2026, 9, 2));
      final memories = _Memories([memory])..revertable.add('s1');
      var row = await _row(tester, memories, memory);
      expect(row.options.keys, ['open', 'revert']);
      expect(row.swipeTrailing, isEmpty);

      memories.reverting.add('s1');
      row = await _row(tester, memories, memory);
      expect(row.options.keys, ['open']);
      expect(row.projection['enabled'], isFalse);
    });
  });

  group('memory row actions', () {
    testWidgets('without a plan to offer, a locked row is a neutral title', (tester) async {
      final memory = _memory('m2', 'Secret plan', locked: true);
      final row = await _row(tester, _Memories([memory]), memory, subscriptionUI: false);
      expect(row.title, _en.memoryDetailsTitle);
      expect(row.projection.toString(), isNot(contains('Secret plan')));
    });

    testWidgets('an unreviewed fact offers both verdicts; a wrong verdict leaves only right', (tester) async {
      final open = _memory('f1', 'Lives in Brooklyn', ledgerKind: KnowledgeLedgerKind.fact);
      final wrong = _memory('f2', 'Lives in Queens', ledgerKind: KnowledgeLedgerKind.fact, userReview: false);
      final memories = _Memories([open, wrong]);
      expect((await _row(tester, memories, open)).options.keys, containsAll(['review_right', 'review_wrong']));
      final row = await _row(tester, memories, wrong);
      expect(row.options.keys, contains('review_right'));
      expect(row.options.keys, isNot(contains('review_wrong')));
    });

    testWidgets('tap and options reach the existing owners', (tester) async {
      final fact = _memory('f1', 'Lives in Brooklyn', ledgerKind: KnowledgeLedgerKind.fact, suppressed: false);
      final superseded = _memory('s1', 'Lived in Boston',
          ledgerKind: KnowledgeLedgerKind.fact, supersededBy: 'f1', invalidAt: DateTime.utc(2026, 9, 2));
      final memories = _Memories([fact, superseded])
        ..belief = true
        ..revertable.add('s1');
      final edited = <String>[];
      final row = await _row(tester, memories, fact, onEdit: (memory) => edited.add(memory.id));
      await row.action!(null);
      await row.action!('edit');
      expect(edited, ['f1', 'f1'], reason: 'an editable tap and Edit open the edit sheet');
      await row.action!('review_right');
      await row.action!('use_suppress');
      final revert = await _row(tester, memories, superseded);
      await revert.action!('revert');
      expect(memories.calls, ['review:f1:true', 'use:f1:${MemoryUseAction.suppress.apiValue}', 'revert:s1']);
    });
  });

  group('native Memories page', () {
    testWidgets('a locked tap routes to the plan page when subscriptions show', (tester) async {
      final host = NativeTestHost.install();
      final pushes = _Pushes();
      final memories = _Memories([_memory('m2', 'Secret plan', locked: true)]);
      await tester.pumpWidget(_app(memories, const MemoriesPage(showMindMap: false), observers: [pushes]));
      await NativeTestHost.settle(tester);
      final before = pushes.routes.length;

      await _send(host, 'memory_m2');
      final route = pushes.routes.skip(before).single as ModalRoute;
      final page = (route as dynamic).builder(tester.element(find.byType(MemoriesPage))) as Widget;
      expect(page, isA<UsagePage>().having((page) => page.showUpgradeDialog, 'showUpgradeDialog', isTrue));
      route.navigator!.removeRoute(route);
      await tester.pump();
    });

    testWidgets('delete goes through the undo delete', (tester) async {
      final host = NativeTestHost.install();
      final memories = _Memories([_memory('m1', 'Likes tea')]);
      await tester.pumpWidget(_app(memories, const Scaffold(body: MemoriesPage(showMindMap: false))));
      await NativeTestHost.settle(tester);
      expect(_published(host).$2['memory_m1']!['swipeTrailing'], ['delete']);

      unawaited(_send(host, 'memory_m1', 'delete'));
      await tester.pump();
      expect(memories.deleted, ['m1']);
      expect(memories.confirmed, 0, reason: 'the delete waits for its Undo toast');
      // The toast closes without Undo; the undo delete then commits.
      ScaffoldMessenger.of(tester.element(find.byType(MemoriesPage))).hideCurrentSnackBar();
      await tester.pump();
      await tester.pump();
      expect(memories.confirmed, 1);
    });

    testWidgets('shows the partial and history banners', (tester) async {
      final host = NativeTestHost.install();
      final memories = _Memories([_memory('m1', 'Likes tea')])
        ..partial = true
        ..belief = true
        ..history = true
        ..truncated = true
        ..more = true;
      await tester.pumpWidget(_app(memories, const MemoriesPage(showMindMap: false)));
      await NativeTestHost.settle(tester);

      final (sections, rows) = _published(host);
      expect(sections['memory_partial'], ['memory_partial_label', 'memory_partial_retry']);
      expect(rows['memory_partial_label']!['title'], _en.couldNotLoadMemories);
      expect(sections['memory_history'], ['memory_history_label', 'memory_history_more']);
      final retry = _send(host, 'memory_partial_retry');
      await NativeTestHost.settle(tester);
      await retry;
      expect(memories.loads, 1);

      memories
        ..more = false
        ..notifyListeners();
      await NativeTestHost.settle(tester);
      expect(_published(host).$1['memory_history'], ['memory_history_label']);
    });

    testWidgets('mirrors the three empty states and their one action', (tester) async {
      final host = NativeTestHost.install();
      final memories = _Memories([]);
      await tester.pumpWidget(_app(memories, const MemoriesPage(showMindMap: false)));
      await NativeTestHost.settle(tester);

      var (sections, rows) = _published(host);
      expect(sections['memory_empty'], ['memory_empty_label', 'memory_add_first']);
      expect(rows['memory_empty_label']!['title'], _en.noMemoriesYet);
      expect(rows.containsKey('memories_add'), isFalse, reason: 'the empty state owns the first add');

      memories
        ..items = [_memory('m1', 'Likes tea')]
        ..query = 'coffee'
        ..notifyListeners();
      await NativeTestHost.settle(tester);
      (sections, rows) = _published(host);
      expect(sections['memory_empty'], ['memory_empty_label', 'memory_clear_search']);
      expect(rows['memory_empty_label']!['title'], _en.noMemoriesFound);
      final clear = _send(host, 'memory_clear_search');
      await NativeTestHost.settle(tester);
      await clear;
      expect(memories.query, isEmpty);

      memories
        ..device = true
        ..notifyListeners();
      await NativeTestHost.settle(tester);
      (sections, rows) = _published(host);
      expect(sections['memory_empty'], ['memory_empty_label', 'memory_reset_filters']);
      expect(rows['memory_empty_label']!['title'], _en.noMemoriesInCategories);
    });
  });

  group('mind map card', () {
    testWidgets('is hidden during search', (tester) async {
      final host = NativeTestHost.install();
      final memories = _Memories([_memory('m1', 'Likes tea')])..query = 'tea';
      await tester.pumpWidget(_app(memories, MemoriesPage(loadGraph: () async => _graphFixture())));
      await NativeTestHost.settle(tester);
      expect(_published(host).$1.containsKey('memory_graph'), isFalse);

      memories.setSearchQuery('');
      await NativeTestHost.settle(tester);
      expect(_published(host).$1['memory_graph'], ['memory_graph_preview']);
    });

    testWidgets('loads as a card and opens the full graph with the same source', (tester) async {
      final host = NativeTestHost.install();
      final response = Completer<Map<String, dynamic>>();
      Future<Map<String, dynamic>> load() => response.future;
      await tester.pumpWidget(_app(_Memories([_memory('m1', 'Likes tea')]), MemoriesPage(loadGraph: load)));
      await NativeTestHost.settle(tester);

      var preview = _published(host).$2['memory_graph_preview']!;
      expect((preview['graph'] as Map)['placeholder'], isTrue);
      response.complete(_graphFixture());
      await NativeTestHost.settle(tester);
      preview = _published(host).$2['memory_graph_preview']!;
      final graph = preview['graph'] as Map;
      expect([graph['placeholder'], graph['layout'], graph['height'], graph['interactive'], graph['zoom']],
          [false, 'card', 140.0, false, 0.6]);

      // The row stays pending natively while the pushed graph is open.
      unawaited(_send(host, 'memory_graph_preview'));
      await NativeTestHost.settle(tester);
      final page = tester.widget<MemoryGraphPage>(find.byType(MemoryGraphPage));
      expect(page.trackOpenEvent, isFalse);
      expect(page.loadGraph, same(load));
    });

    testWidgets('a failure offers Try Again and a graph over the limits becomes a plain row', (tester) async {
      final host = NativeTestHost.install();
      var calls = 0;
      Future<Map<String, dynamic>> load() async {
        if (++calls == 1) throw Exception('offline');
        return {
          'nodes': [
            for (var i = 0; i < 1100; i++) {'id': 'n$i', 'label': 'n$i'}
          ],
          'edges': const [],
        };
      }

      await tester.pumpWidget(_app(_Memories([_memory('m1', 'Likes tea')]), MemoriesPage(loadGraph: load)));
      await NativeTestHost.settle(tester);
      expect(_published(host).$1['memory_graph'], ['memory_graph_error', 'memory_graph_retry']);

      final retry = _send(host, 'memory_graph_retry');
      await NativeTestHost.settle(tester);
      await retry;
      await NativeTestHost.settle(tester);
      final (sections, _) = _published(host);
      expect(sections['memory_graph'], ['memory_graph_open']);
      expect(sections['memories'], ['memory_m1']);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'the list stays native');
    });
  });
}
