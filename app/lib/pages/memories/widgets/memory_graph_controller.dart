import 'dart:math';

import 'package:flutter/material.dart';
import 'package:vector_math/vector_math_64.dart' as v;

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'memory_graph_page.dart';

/// Owns one knowledge graph: its load, the force simulation and the node selection. The classic
/// painter and the native projection both read it; only [load] talks to the backend.
class MemoryGraphController extends ChangeNotifier {
  MemoryGraphController({required this.loadGraph, required this.localizations, Random? random})
      : _rnd = random ?? Random();

  final Future<Map<String, dynamic>> Function() loadGraph;

  /// The current localizations, for the user node's label and the error copy.
  final AppLocalizations Function() localizations;
  final Random _rnd;

  final ForceDirectedSimulation3D simulation = ForceDirectedSimulation3D();
  bool isLoading = true;
  String? error;
  String? selectedNodeId;
  final Set<String> highlightedNodeIds = {};
  bool _disposed = false;

  /// The graph has no content: no nodes, or only the synthetic user node.
  bool get isEmpty =>
      simulation.nodes.isEmpty || (simulation.nodes.length == 1 && simulation.nodes.first.id == 'user-node');

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  /// Loads the graph. A [silent] reload keeps the current state on screen and replaces the graph
  /// only when its node ids changed. A result that arrives after disposal or after the account
  /// session changed is dropped.
  Future<void> load({bool silent = false}) async {
    if (_disposed) return;
    // The native preview fences to the account; the default build keeps its original load.
    final session = nativePresentationEnabled ? AuthService.instance.captureSessionSnapshot() : null;
    final fenced = nativePresentationEnabled;
    bool current() =>
        !_disposed && (!fenced || session != null && AuthService.instance.isSessionSnapshotCurrent(session));
    if (!silent) {
      isLoading = true;
      error = null;
      _changed();
    }

    try {
      final data = await loadGraph();
      if (!current()) return;

      final newNodes = data['nodes'] as List<dynamic>? ?? [];
      final newEdges = data['edges'] as List<dynamic>? ?? [];

      if (error != null) {
        error = null;
        _changed();
      }

      if (_isSameGraph(newNodes, newEdges)) {
        if (!silent) {
          isLoading = false;
          _changed();
        }
        return;
      }

      populate(data);
      _runLayoutSync();
    } catch (e) {
      Logger.debug('Knowledge graph load failed: $e');
      if (!current()) return;
      if (!silent) {
        error = localizations().couldNotLoadKnowledgeGraph;
        _changed();
      }
    } finally {
      if (current() && !silent) {
        isLoading = false;
        _changed();
      } else if (!_disposed && !silent && isLoading) {
        // A stale result is dropped, but the graph must not stay loading: Try Again loads for the
        // current session.
        isLoading = false;
        error = localizations().couldNotLoadKnowledgeGraph;
        _changed();
      }
    }
  }

  bool _isSameGraph(List<dynamic> newNodes, List<dynamic> newEdges) {
    final hasUserNode = simulation.nodes.any((n) => n.id == 'user-node');
    // If we expect N+1 nodes (content + user), we should account for that
    if (newNodes.length + (hasUserNode ? 0 : 1) != simulation.nodes.length) return false;
    if (newEdges.length != simulation.edges.length) return false;

    final currentIds = simulation.nodes.map((n) => n.id).toSet();
    for (var n in newNodes) {
      if (!currentIds.contains(n['id'])) return false;
    }
    return true;
  }

  /// Replaces the graph with [data]: user-like nodes merge into one fixed user node (synthesized
  /// when the data has none), edges are remapped and deduplicated, and self loops are dropped.
  void populate(Map<String, dynamic> data) {
    simulation.nodes.clear();
    simulation.edges.clear();
    simulation.nodeMap.clear();

    final nodes = data['nodes'] as List<dynamic>? ?? [];
    final edges = data['edges'] as List<dynamic>? ?? [];

    final givenName = SharedPreferencesUtil().givenName;
    final userLabel = memoryGraphUserLabel(givenName, localizations());
    final knownUserLabels = memoryGraphKnownUserLabels(givenName);
    bool isUserLikeNode(Map<dynamic, dynamic> nodeData) {
      final label = (nodeData['label'] as String? ?? '').trim().toLowerCase();
      final nodeType = (nodeData['node_type'] as String? ?? '').trim().toLowerCase();
      return knownUserLabels.contains(label) || nodeType == 'user';
    }

    String? primaryUserId;
    for (final nodeData in nodes) {
      if (nodeData is Map && isUserLikeNode(nodeData)) {
        primaryUserId = (nodeData['id'] ?? '').toString();
        if (primaryUserId.isNotEmpty) break;
      }
    }
    primaryUserId ??= 'user-node';

    final remappedIds = <String, String>{};
    final addedNodeIds = <String>{};

    for (final rawNodeData in nodes) {
      if (rawNodeData is! Map) continue;
      final nodeData = rawNodeData;
      final originalId = (nodeData['id'] ?? '').toString();
      if (originalId.isEmpty) continue;

      final isUserLike = isUserLikeNode(nodeData);
      if (isUserLike && originalId != primaryUserId) {
        remappedIds[originalId] = primaryUserId;
        continue;
      }

      final nodeId = remappedIds[originalId] ?? originalId;
      if (addedNodeIds.contains(nodeId)) continue;

      final isUser = nodeId == primaryUserId;
      final label = isUser ? userLabel : (nodeData['label'] as String? ?? '');
      final nodeType = nodeData['node_type'] ?? 'concept';

      final node = GraphNode3D(
        id: nodeId,
        label: label,
        nodeType: nodeType,
        baseColor: isUser ? OmiColors.accent : memoryGraphColorForType(nodeType),
        initialPosition: isUser ? v.Vector3.zero() : _randomPos3D(),
        isFixed: isUser,
      );

      if (isUser) node.position.setZero();
      simulation.addNode(node);
      addedNodeIds.add(nodeId);
    }

    if (!simulation.nodeMap.containsKey(primaryUserId)) {
      final userNode = GraphNode3D(
        id: primaryUserId,
        label: userLabel,
        nodeType: 'person',
        baseColor: OmiColors.accent,
        initialPosition: v.Vector3.zero(),
        isFixed: true,
      );
      userNode.position.setZero();
      simulation.addNode(userNode);
      addedNodeIds.add(primaryUserId);
    }

    final edgeKeys = <String>{};
    void addUniqueEdge(String sourceId, String targetId, String label) {
      if (sourceId.isEmpty || targetId.isEmpty || sourceId == targetId) return;
      final key = '$sourceId->$targetId::$label';
      if (edgeKeys.contains(key)) return;
      edgeKeys.add(key);
      simulation.addEdge(GraphEdge3D(sourceId: sourceId, targetId: targetId, label: label));
    }

    for (final rawEdgeData in edges) {
      if (rawEdgeData is! Map) continue;
      final edgeData = rawEdgeData;
      final sourceId =
          remappedIds[(edgeData['source_id'] ?? '').toString()] ?? (edgeData['source_id'] ?? '').toString();
      final targetId =
          remappedIds[(edgeData['target_id'] ?? '').toString()] ?? (edgeData['target_id'] ?? '').toString();
      final label = (edgeData['label'] ?? '').toString();
      if (!addedNodeIds.contains(sourceId) || !addedNodeIds.contains(targetId)) continue;
      addUniqueEdge(sourceId, targetId, label);
    }

    simulation.wake();
    _changed();
  }

  v.Vector3 _randomPos3D({double spread = 1000.0}) {
    return v.Vector3(
      (_rnd.nextDouble() - 0.5) * spread,
      (_rnd.nextDouble() - 0.5) * spread,
      (_rnd.nextDouble() - 0.5) * spread,
    );
  }

  void _runLayoutSync() {
    for (int i = 0; i < 200 && !simulation.isStable; i++) {
      simulation.tick();
    }
    _changed();
  }

  /// Selects [hitNodeId], or clears the selection for null or the already selected node. The
  /// selection highlights the node and its 4 nearest neighbours by 3D distance.
  void select(String? hitNodeId) {
    if (hitNodeId == selectedNodeId && hitNodeId != null) {
      hitNodeId = null;
    }

    selectedNodeId = hitNodeId;
    highlightedNodeIds.clear();

    if (hitNodeId != null) {
      highlightedNodeIds.add(hitNodeId);

      final node = simulation.nodeMap[hitNodeId];
      if (node != null) {
        PlatformManager.instance.analytics.brainMapNodeClicked(node.id, node.label, node.nodeType);
      }

      final neighbors = <String>[];
      for (var edge in simulation.edges) {
        if (edge.sourceId == hitNodeId) neighbors.add(edge.targetId);
        if (edge.targetId == hitNodeId) neighbors.add(edge.sourceId);
      }

      final centerNode = simulation.nodeMap[hitNodeId];
      if (centerNode != null) {
        neighbors.sort((a, b) {
          final na = simulation.nodeMap[a];
          final nb = simulation.nodeMap[b];
          if (na == null || nb == null) return 0;
          final da = _distSq(centerNode.position, na.position);
          final db = _distSq(centerNode.position, nb.position);
          return da.compareTo(db);
        });
      }

      highlightedNodeIds.addAll(neighbors.take(4));
    }
    _changed();
  }

  double _distSq(v.Vector3 a, v.Vector3 b) {
    final dx = a.x - b.x;
    final dy = a.y - b.y;
    final dz = a.z - b.z;
    return dx * dx + dy * dy + dz * dz;
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

/// The classic node colour for a backend node type; anything unknown draws as a concept.
Color memoryGraphColorForType(String nodeType) {
  switch (nodeType) {
    case 'person':
      return Colors.cyanAccent;
    case 'place':
      return const Color(0xFF00FF9D); // omi-ux-allow: color-literal -- classic node colour, moved as-is
    case 'organization':
      return Colors.orangeAccent;
    case 'thing':
      return Colors.yellowAccent;
    default:
      return Colors.blueAccent;
  }
}
