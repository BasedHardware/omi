import 'dart:async';
import 'dart:math';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:vector_math/vector_math_64.dart' as v;

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/memories/widgets/memory_graph_controller.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../mobile/native_ui/native_test_host.dart';

MemoryGraphController _controller(Future<Map<String, dynamic>> Function() load) {
  final controller = MemoryGraphController(
      loadGraph: load, localizations: () => lookupAppLocalizations(const Locale('en')), random: Random(1));
  addTearDown(controller.dispose);
  return controller;
}

Map<String, dynamic> _node(String id, String label, [String? type]) =>
    {'id': id, 'label': label, if (type != null) 'node_type': type};

Map<String, dynamic> _edge(String source, String target, [String label = '']) =>
    {'source_id': source, 'target_id': target, 'label': label};

final class _OtherOwner implements AuthTokenGateway {
  const _OtherOwner();

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'another-account');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('populate', () {
    test('merges user-like nodes into one fixed user node and dedupes edges', () {
      final graph = _controller(() async => {});
      graph.populate({
        'nodes': [
          _node('me-1', 'Me', 'concept'),
          _node('me-2', 'the user'),
          _node('ada', 'Ada', 'person'),
          _node('omi', 'Omi', 'organization'),
          _node('', 'No id'),
        ],
        'edges': [
          _edge('me-2', 'ada', 'knows'),
          _edge('me-1', 'ada', 'knows'),
          _edge('ada', 'ada', 'self'),
          _edge('ada', 'omi', 'works at'),
          _edge('ada', 'omi', 'works at'),
          _edge('ada', 'missing', 'dangling'),
        ],
      });

      expect(graph.simulation.nodes.map((node) => node.id), ['me-1', 'ada', 'omi']);
      final user = graph.simulation.nodeMap['me-1']!;
      expect(user.isFixed, isTrue);
      expect(user.label, 'You');
      expect(user.position, v.Vector3.zero());
      expect(graph.simulation.edges.map((edge) => '${edge.sourceId}>${edge.targetId}:${edge.label}'),
          ['me-1>ada:knows', 'ada>omi:works at']);
      expect(graph.isEmpty, isFalse);
    });

    test('adds a synthetic user node when the data has none', () {
      final graph = _controller(() async => {});
      graph.populate({
        'nodes': [_node('ada', 'Ada', 'person')],
        'edges': const [],
      });

      final user = graph.simulation.nodeMap['user-node']!;
      expect(user.isFixed, isTrue);
      expect(user.nodeType, 'person');
      expect(user.label, 'You');
      expect(graph.simulation.nodes, hasLength(2));

      graph.populate({'nodes': const [], 'edges': const []});
      expect(graph.simulation.nodes.single.id, 'user-node');
      expect(graph.isEmpty, isTrue);
    });
  });

  group('select', () {
    test('toggles and highlights the 4 nearest neighbours', () {
      final graph = _controller(() async => {});
      graph.populate({
        'nodes': [
          for (final id in ['c', 'n1', 'n2', 'n3', 'n4', 'n5', 'n6']) _node(id, id)
        ],
        'edges': [
          for (final id in ['n6', 'n5', 'n4', 'n3', 'n2', 'n1']) _edge('c', id)
        ],
      });
      graph.simulation.nodeMap['c']!.position = v.Vector3.zero();
      for (var i = 1; i <= 6; i++) {
        graph.simulation.nodeMap['n$i']!.position = v.Vector3(i * 100.0, 0, 0);
      }
      var notified = 0;
      graph.addListener(() => notified++);

      graph.select('c');
      expect(graph.selectedNodeId, 'c');
      expect(graph.highlightedNodeIds, {'c', 'n1', 'n2', 'n3', 'n4'});

      graph.select('c');
      expect(graph.selectedNodeId, isNull);
      expect(graph.highlightedNodeIds, isEmpty);

      graph.select('n6');
      expect(graph.highlightedNodeIds, {'n6', 'c'});
      graph.select(null);
      expect(graph.selectedNodeId, isNull);
      expect(graph.highlightedNodeIds, isEmpty);
      expect(notified, 4);
    });
  });

  group('load', () {
    test('a load that finishes after the account session changed is dropped', () async {
      NativeTestHost.installOwner();
      IosNativeSurface.debugNativeHostForTest = true;
      addTearDown(() => IosNativeSurface.debugNativeHostForTest = false);
      final response = Completer<Map<String, dynamic>>();
      final graph = _controller(() => response.future);

      final load = graph.load();
      expect(graph.isLoading, isTrue);
      final previous = AuthService.installLocalHarnessTokenGateway(const _OtherOwner());
      addTearDown(() => AuthService.installLocalHarnessTokenGateway(previous));
      response.complete({
        'nodes': [_node('ada', 'Ada', 'person')],
        'edges': const [],
      });
      await load;

      expect(graph.simulation.nodes, isEmpty, reason: 'the stale result is not applied');
      expect(graph.isLoading, isFalse, reason: 'the graph does not stay loading');
      expect(graph.error, lookupAppLocalizations(const Locale('en')).couldNotLoadKnowledgeGraph,
          reason: 'Try Again reloads for the current session');
    });

    test('a load for the current session applies, and a failure reports the localized error', () async {
      NativeTestHost.installOwner();
      IosNativeSurface.debugNativeHostForTest = true;
      addTearDown(() => IosNativeSurface.debugNativeHostForTest = false);
      var fail = false;
      final graph = _controller(() async {
        if (fail) throw Exception('offline');
        return {
          'nodes': [_node('ada', 'Ada', 'person')],
          'edges': const [],
        };
      });

      await graph.load();
      expect(graph.isLoading, isFalse);
      expect(graph.simulation.nodeMap.keys, containsAll(['ada', 'user-node']));

      fail = true;
      await graph.load();
      expect(graph.error, lookupAppLocalizations(const Locale('en')).couldNotLoadKnowledgeGraph);
      expect(graph.isLoading, isFalse);
    });

    test('a silent reload replaces the graph only when its node ids change', () async {
      // The backend's own user node keeps the node counts comparable (the classic rule).
      var data = <String, dynamic>{
        'nodes': [_node('user-node', 'Me'), _node('ada', 'Ada', 'person'), _node('omi', 'Omi', 'organization')],
        'edges': [_edge('ada', 'omi', 'works at')],
      };
      final graph = _controller(() async => data);
      await graph.load();
      final first = graph.simulation.nodeMap['ada'];

      data = {
        'nodes': [
          _node('user-node', 'Me'),
          _node('ada', 'Ada Lovelace', 'person'),
          _node('omi', 'Omi', 'organization')
        ],
        'edges': [_edge('ada', 'omi', 'founded')],
      };
      await graph.load(silent: true);
      expect(graph.simulation.nodeMap['ada'], same(first), reason: 'same ids keep the laid-out graph');
      expect(graph.simulation.nodeMap['ada']!.label, 'Ada');

      data = {
        'nodes': [_node('user-node', 'Me'), _node('ada', 'Ada', 'person'), _node('paris', 'Paris', 'place')],
        'edges': const [],
      };
      await graph.load(silent: true);
      expect(graph.simulation.nodeMap.keys, containsAll(['ada', 'paris', 'user-node']));
      expect(graph.simulation.nodeMap.containsKey('omi'), isFalse);
      expect(graph.isLoading, isFalse);
    });
  });
}
