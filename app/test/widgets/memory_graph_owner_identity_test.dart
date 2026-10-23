import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// Real IDs from backend/models/memory_promotion.py:canonical_graph_entity_id.
// A canonical named person is distinct from the reserved owner endpoint "user".
const _personId = 'ent_1611f3f21a8027b7c4f5';
const _conceptId = 'ent_f33e07a0450b65412254';
const _codingId = 'ent_23041b101c368d43522a';

Widget _app(Map<String, dynamic> graph) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: MemoryGraphPage(trackOpenEvent: false, loadGraph: () async => graph),
    );

Map<String, Object> _snapshot(WidgetTester tester) {
  final graph = tester.state<MemoryGraphPageState>(find.byType(MemoryGraphPage)).simulation;
  return {
    'nodes': graph.nodes.map((node) => node.id).toSet(),
    'owner': graph.nodes.singleWhere((node) => node.isFixed).id,
    'edges': graph.edges.map((edge) => '${edge.sourceId}->${edge.targetId}:${edge.label}').toSet(),
  };
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    SharedPreferencesUtil().givenName = 'Sam';
    SharedPreferencesUtil().familyName = 'Altman';
  });

  for (final personFirst in [false, true]) {
    testWidgets('preserves a distinct full-name person (personFirst=$personFirst)', (tester) async {
      const owner = {'id': 'user', 'label': 'user', 'node_type': 'person'};
      const person = {'id': _personId, 'label': 'Sam Altman', 'node_type': 'person'};
      await tester.pumpWidget(_app({
        'nodes': [
          if (personFirst) person,
          owner,
          if (!personFirst) person,
          {'id': _codingId, 'label': 'Coding', 'node_type': 'concept'},
        ],
        'edges': [
          {'source_id': 'user', 'target_id': _personId, 'label': 'knows'},
          {'source_id': _personId, 'target_id': _codingId, 'label': 'enjoys'},
        ],
      }));
      await tester.pumpAndSettle();
      expect(_snapshot(tester), {
        'nodes': {'user', _personId, _codingId},
        'owner': 'user',
        'edges': {'user->$_personId:knows', '$_personId->$_codingId:enjoys'},
      });
    });
  }

  testWidgets('preserves a concept called I and its relationship', (tester) async {
    final data = <String, dynamic>{
      'nodes': [
        {'id': 'user', 'label': 'user', 'node_type': 'person'},
        {'id': _conceptId, 'label': 'I', 'node_type': 'concept'},
      ],
      'edges': [
        {'source_id': 'user', 'target_id': _conceptId, 'label': 'studies'},
      ],
    };
    await tester.pumpWidget(_app(data));
    await tester.pumpAndSettle();
    final expected = {
      'nodes': {'user', _conceptId},
      'owner': 'user',
      'edges': {'user->$_conceptId:studies'},
    };
    expect(_snapshot(tester), expected);
    // A fresh page instance reads the same records without any rebuild/write.
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(_app(data));
    await tester.pumpAndSettle();
    expect(_snapshot(tester), expected);
  });

  testWidgets('a saved given name cannot absorb a distinct legacy person', (tester) async {
    await tester.pumpWidget(_app({
      'nodes': [
        {'id': 'contact-sam', 'label': 'Sam', 'node_type': 'person'},
        {'id': 'user-node', 'label': 'Me', 'node_type': 'user'},
      ],
      'edges': [
        {'source_id': 'user-node', 'target_id': 'contact-sam', 'label': 'knows'},
      ],
    }));
    await tester.pumpAndSettle();
    expect(_snapshot(tester), {
      'nodes': {'user-node', 'contact-sam'},
      'owner': 'user-node',
      'edges': {'user-node->contact-sam:knows'},
    });
  });

  for (final reverse in [false, true]) {
    testWidgets('only explicit owner aliases remap incident edges (reverse=$reverse)', (tester) async {
      final nodes = [
        {'id': 'legacy-owner', 'label': 'Sam Altman', 'node_type': 'user'},
        {'id': 'user-node', 'label': 'Me', 'node_type': 'person'},
        {'id': 'user', 'label': 'user', 'node_type': 'person'},
        {'id': _codingId, 'label': 'Coding', 'node_type': 'concept'},
      ];
      await tester.pumpWidget(_app({
        'nodes': reverse ? nodes.reversed.toList() : nodes,
        'edges': [
          {'source_id': 'legacy-owner', 'target_id': _codingId, 'label': 'enjoys'},
          {'source_id': 'user', 'target_id': _codingId, 'label': 'enjoys'},
          {'source_id': _codingId, 'target_id': 'user-node', 'label': 'interests'},
        ],
      }));
      await tester.pumpAndSettle();
      expect(_snapshot(tester), {
        'nodes': {'user', _codingId},
        'owner': 'user',
        'edges': {'user->$_codingId:enjoys', '$_codingId->user:interests'},
      });
      final graph = tester.state<MemoryGraphPageState>(find.byType(MemoryGraphPage)).simulation;
      expect(graph.nodeMap['user']!.label, 'Sam');
      expect(graph.edges.length, 2, reason: 'duplicate alias edges must render once');
    });
  }

  testWidgets('unproven name-only entities keep their edges and a separate anchor', (tester) async {
    await tester.pumpWidget(_app({
      'nodes': [
        {'id': 'named-person', 'label': 'Sam', 'node_type': 'person'},
        {'id': 'pronoun-concept', 'label': 'Me', 'node_type': 'concept'},
      ],
      'edges': [
        {'source_id': 'named-person', 'target_id': 'pronoun-concept', 'label': 'studies'},
      ],
    }));
    await tester.pumpAndSettle();
    expect(_snapshot(tester), {
      'nodes': {'user-node', 'named-person', 'pronoun-concept'},
      'owner': 'user-node',
      'edges': {'named-person->pronoun-concept:studies'},
    });
  });

  testWidgets('canonical owner beyond the simulation bound still wins over an early legacy alias', (tester) async {
    await tester.pumpWidget(_app({
      'nodes': [
        {'id': 'legacy-owner', 'label': 'Sam', 'node_type': 'user'},
        for (var i = 0; i < 250; i++) {'id': 'concept:$i', 'label': 'Concept $i', 'node_type': 'concept'},
        {'id': 'user', 'label': 'user', 'node_type': 'person'},
      ],
      'edges': [
        {'source_id': 'legacy-owner', 'target_id': 'concept:0', 'label': 'enjoys'},
        {'source_id': 'user', 'target_id': 'concept:0', 'label': 'studies'},
      ],
    }));
    await tester.pumpAndSettle();
    final graph = tester.state<MemoryGraphPageState>(find.byType(MemoryGraphPage)).simulation;
    expect(graph.nodes.length, lessThanOrEqualTo(201));
    expect(graph.nodes.singleWhere((node) => node.isFixed).id, 'user');
    expect(graph.nodes.any((node) => node.id == 'legacy-owner'), isFalse);
    expect(graph.edges.map((edge) => '${edge.sourceId}->${edge.targetId}:${edge.label}').toSet(),
        {'user->concept:0:enjoys', 'user->concept:0:studies'});
  });
}
