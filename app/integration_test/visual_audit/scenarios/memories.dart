// The Memories page: create, quick edit, search and filter empty states, swipe-to-delete, and the
// knowledge graph preview loading, failed and loaded above the list.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';

import '../harness.dart';

const _preference = 'I prefer morning meetings and keep Fridays free for focused work.';

const _listed = [
  'Prefers morning meetings and keeps Fridays free.',
  'Prefers the pendant over the phone mic for long meetings.',
  'Is training for a half marathon in March.',
  'Sister Priya lives in Austin.',
];

Future<MemoriesProvider> _seededMemories(AuditRun a) async {
  final memories = MemoriesProvider();
  for (final text in _listed.reversed) {
    await a.tester.runAsync(() => memories.createMemory(text, MemoryVisibility.private));
  }
  return memories;
}

/// The graph preview never answers, so it stays on its loading skeleton.
Future<Map<String, dynamic>> _graphNeverLoads() => Completer<Map<String, dynamic>>().future;

Future<Map<String, dynamic>> _graphFails() async => throw Exception('graph fixture failure');

Future<Map<String, dynamic>> _graphLoaded() async => {
      'nodes': [
        {'id': 'me', 'label': 'Me', 'node_type': 'user'},
        {'id': 'meetings', 'label': 'Meetings', 'node_type': 'concept'},
        {'id': 'fridays', 'label': 'Fridays', 'node_type': 'concept'},
        {'id': 'running', 'label': 'Half marathon', 'node_type': 'concept'},
        {'id': 'priya', 'label': 'Priya', 'node_type': 'person'},
        {'id': 'austin', 'label': 'Austin', 'node_type': 'place'},
        {'id': 'pendant', 'label': 'Pendant', 'node_type': 'thing'},
      ],
      'edges': [
        {'id': 'e1', 'source_id': 'me', 'target_id': 'meetings', 'label': 'prefers'},
        {'id': 'e2', 'source_id': 'meetings', 'target_id': 'fridays', 'label': 'avoids'},
        {'id': 'e3', 'source_id': 'me', 'target_id': 'running', 'label': 'trains for'},
        {'id': 'e4', 'source_id': 'me', 'target_id': 'priya', 'label': 'sister'},
        {'id': 'e5', 'source_id': 'priya', 'target_id': 'austin', 'label': 'lives in'},
        {'id': 'e6', 'source_id': 'me', 'target_id': 'pendant', 'label': 'uses'},
      ],
    };

final memoriesScenarios = <AuditScenario>[
  AuditScenario(
    id: 'memories-mind-map-distinct-identities',
    title: 'Mind Map: owner, same-name people and a concept called I stay distinct',
    page: 'lib/pages/memories/widgets/memory_graph_page.dart (MemoryGraphPage)',
    state: 'Synthetic Sam Altman account; canonical owner follows distinct people and a concept in response order',
    prefs: const {'givenName': 'Sam', 'familyName': 'Altman'},
    run: (a) async {
      await a.pump(
          MemoryGraphPage(
            trackOpenEvent: false,
            loadGraph: () async => {
              'nodes': [
                {'id': 'ent_1611f3f21a8027b7c4f5', 'label': 'Sam Altman', 'node_type': 'person'},
                {'id': 'contact-sam', 'label': 'Sam', 'node_type': 'person'},
                {'id': 'ent_f33e07a0450b65412254', 'label': 'I', 'node_type': 'concept'},
                {'id': 'user', 'label': 'user', 'node_type': 'person'},
              ],
              'edges': [
                {'source_id': 'user', 'target_id': 'ent_1611f3f21a8027b7c4f5', 'label': 'knows'},
                {'source_id': 'user', 'target_id': 'contact-sam', 'label': 'knows'},
                {'source_id': 'user', 'target_id': 'ent_f33e07a0450b65412254', 'label': 'studies'},
              ],
            },
          ),
          scaffold: false);
      void assertIdentities() {
        final graph = a.tester.state<MemoryGraphPageState>(find.byType(MemoryGraphPage)).simulation;
        expect(graph.nodes.map((node) => node.id).toSet(),
            {'user', 'ent_1611f3f21a8027b7c4f5', 'contact-sam', 'ent_f33e07a0450b65412254'});
        expect(graph.nodes.singleWhere((node) => node.isFixed).id, 'user');
        expect(graph.edges.length, 3);
      }

      assertIdentities();
      await a.shot('Distinct people and concept retain their owner relationships', step: 'loaded');
      await a.tap(find.byKey(const ValueKey('mind_map_refresh')));
      assertIdentities();
      await a.shot('Refresh preserves all identities and relationships', step: 'refreshed');
    },
  ),
  AuditScenario(
    id: 'memories-mind-map-recovery',
    title: 'Mind Map: saved memories without assertions, then a later graph page',
    page: 'lib/pages/memories/widgets/memory_graph_page.dart (MemoryGraphPage)',
    state: 'A canonical page with saved memories and a signed cursor; a later page contains relationships',
    run: (a) async {
      await a.pump(
          MemoryGraphPage(
            trackOpenEvent: false,
            loadGraph: () async => {
              'nodes': [],
              'edges': [],
              'catalog_nodes': [
                for (var i = 0; i < _listed.length; i++) {'id': 'memory:$i', 'label': _listed[i]}
              ],
              'has_more': true,
              'next_cursor': 'fixture-page-2',
            },
            loadMoreGraph: (_) => _graphLoaded(),
          ),
          scaffold: false);
      await a.shot('Saved memories remain readable without invented relationships', step: 'catalog');
      await a.tap(find.byKey(const ValueKey('mind_map_load_more')));
      await a.shot('Load a later page containing supported relationships', step: 'graph');
    },
  ),
  AuditScenario(
    id: 'memories-mind-map-empty',
    title: 'Mind Map: genuinely empty account with refresh',
    page: 'lib/pages/memories/widgets/memory_graph_page.dart (MemoryGraphPage)',
    state: 'A successful canonical read has no eligible memories or relationships',
    run: (a) async {
      await a.pump(MemoryGraphPage(trackOpenEvent: false, loadGraph: () async => {'nodes': [], 'edges': []}),
          scaffold: false);
      await a.shot('Refresh remains reachable on an empty Mind Map');
    },
  ),
  AuditScenario(
    id: 'memories-manual-memory',
    title: 'Memories: empty, create, save, quick edit, no results, filtered out',
    page: 'lib/pages/memories/page.dart (MemoriesPage)',
    state: 'Fixture-backed MemoriesProvider on an account with no memories; one manual memory is saved during the run',
    run: (a) async {
      final tester = a.tester;
      await a.pump(const MemoriesPage(), providers: [ChangeNotifierProvider(create: (_) => MemoriesProvider())]);
      await a.shot('Open Memories with an empty account', step: 'empty');
      // The empty state's one action adds the first memory; the floating add button waits for a row.
      expect(find.byType(FloatingActionButton), findsNothing);
      await a.tap(find.byKey(const Key('memories_empty_action')));
      await a.shot('Tap Add your first memory', step: 'create');
      expect(tester.widget<OmiButton>(find.byKey(const ValueKey('memory_save_button'))).onPressed, isNull);
      await a.tap(find.byKey(const ValueKey('memory_save_button')));
      await a.shot('Tap Save Memory with no content', step: 'empty-save');
      await a.enterText(find.byKey(const ValueKey('memory_content_field')), _preference);
      await a.shot('Enter a preference', step: 'draft');
      await a.tap(find.byKey(const ValueKey('memory_save_button')));
      await a.shot('Save the preference through the fixture backend', step: 'saved');
      await a.tap(find.text(_preference));
      await a.shot('Tap the saved card to open quick edit', step: 'edit');
      globalNavigatorKey.currentState!.pop();
      await a.settle();
      await a.enterText(find.byType(TextField).first, 'weekend');
      await a.shot('Search for a term absent from the saved memory', step: 'no-results');
      expect(find.text('No Memories Found'), findsOneWidget);
      await a.tap(find.byKey(const Key('memories_empty_action')));
      expect(find.text(_preference), findsOneWidget);
      final memories = tester.element(find.byType(MemoriesPage)).read<MemoriesProvider>();
      memories.clearCategoryFilter();
      memories.toggleCategoryFilter(MemoryCategory.system);
      await a.settle();
      await a.shot('Filter out the saved manual memory', step: 'filter-empty');
      await a.tap(find.byKey(const Key('memories_empty_action')));
      expect(find.text(_preference), findsOneWidget);
    },
  ),
  AuditScenario(
    id: 'memories-swipe-delete',
    title: 'Memories list, swipe to delete with Undo',
    page: 'lib/pages/memories/page.dart (MemoriesPage)',
    state: 'Fixture-backed MemoriesProvider holding one saved private memory',
    run: (a) async {
      final memories = MemoriesProvider();
      await a.tester.runAsync(
        () => memories.createMemory('Prefers morning meetings and keeps Fridays free.', MemoryVisibility.private),
      );
      await a.pump(const MemoriesPage(), providers: [ChangeNotifierProvider<MemoriesProvider>.value(value: memories)]);
      await a.shot('Memories list with one saved memory', step: 'list');
      await a.tester.drag(find.byType(Dismissible).first, const Offset(-500, 0));
      await a.settle();
      expect(find.text('Undo'), findsOneWidget);
      await a.shot('Swipe the memory row to delete; the Undo toast shows', step: 'undo');
      // Undo before the toast expires, so no delete request is left in flight.
      await a.tap(find.text('Undo'));
      expect(find.text('Prefers morning meetings and keeps Fridays free.'), findsOneWidget);
    },
  ),
  AuditScenario(
    id: 'memories-graph-loading',
    title: 'Memories list while the knowledge graph is still loading',
    page: 'lib/pages/memories/page.dart (MemoriesPage, MemoryMindMapPreview)',
    state: 'Fixture-backed MemoriesProvider holding four memories; the graph request never answers',
    run: (a) async {
      final memories = await _seededMemories(a);
      await a.pump(
        const MemoriesPage(loadGraph: _graphNeverLoads),
        providers: [ChangeNotifierProvider<MemoriesProvider>.value(value: memories)],
      );
      // The list renders without waiting for the graph.
      expect(find.byKey(const ValueKey('memories_mind_map_loading')), findsOneWidget);
      expect(find.text(_listed.first), findsOneWidget);
      await a.shot('Open Memories while the graph is loading');
    },
  ),
  AuditScenario(
    id: 'memories-graph-failed',
    title: 'Memories list after the knowledge graph failed to load',
    page: 'lib/pages/memories/page.dart (MemoriesPage, MemoryMindMapPreview)',
    state: 'Fixture-backed MemoriesProvider holding four memories; the graph request throws',
    run: (a) async {
      final memories = await _seededMemories(a);
      await a.pump(
        const MemoriesPage(loadGraph: _graphFails),
        providers: [ChangeNotifierProvider<MemoriesProvider>.value(value: memories)],
      );
      expect(find.byKey(const ValueKey('memories_mind_map_retry')), findsOneWidget);
      expect(find.text(_listed.last), findsOneWidget);
      await a.shot('Open Memories when the graph fails; it collapses to one row with Try Again');
    },
  ),
  AuditScenario(
    id: 'memories-graph-loaded',
    title: 'Memories list under a loaded knowledge graph preview',
    page: 'lib/pages/memories/page.dart (MemoriesPage, MemoryMindMapPreview)',
    state: 'Fixture-backed MemoriesProvider holding four memories; a seven-node graph fixture',
    run: (a) async {
      final memories = await _seededMemories(a);
      await a.pump(
        const MemoriesPage(loadGraph: _graphLoaded),
        providers: [ChangeNotifierProvider<MemoriesProvider>.value(value: memories)],
      );
      expect(find.byKey(const ValueKey('memories_mind_map_preview')), findsOneWidget);
      expect(find.byKey(const ValueKey('memories_mind_map_loading')), findsNothing);
      await a.shot('Open Memories with the graph loaded above the list');
    },
  ),
];
