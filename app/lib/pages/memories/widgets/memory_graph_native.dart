import 'package:omi/mobile/native_ui/native_graph.dart';
import 'package:omi/ui/ui.dart';

import 'memory_graph_controller.dart';

/// The accent colour the native renderer gives the user node, as '#RRGGBB'.
String memoryGraphAccentHex() =>
    '#${(OmiColors.accent.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0').toUpperCase()}';

/// The node types the classic painter colours; anything else draws as a concept.
const _classicNodeTypes = {'person', 'place', 'organization', 'thing'};

/// Projects [controller]'s current simulation for the native renderer: positions as laid out,
/// labels truncated, the fixed node as the 'user' node and, when [interactive], the selection's
/// highlight. Returns null when the graph cannot be drawn natively (empty, over the limits, an id
/// the contract refuses or a non-finite position); the caller then keeps its classic Flutter graph.
NativeGraph? projectNativeGraph(
  MemoryGraphController controller, {
  String layout = 'fill',
  bool interactive = true,
  double zoom = 1.0,
  double? height,
}) {
  final simulation = controller.simulation;
  if (simulation.nodes.isEmpty || !NativeGraph.fits(simulation.nodes.length, simulation.edges.length)) return null;
  final nodes = <NativeGraphNode>[];
  for (final node in simulation.nodes) {
    final position = node.position;
    if (![position.x, position.y, position.z].every((value) => value.isFinite)) return null;
    double clamp(double value) => value.clamp(-NativeGraph.maxCoordinate, NativeGraph.maxCoordinate).toDouble();
    nodes.add(node.isFixed
        ? NativeGraphNode(node.id, nativeGraphLabel(node.label), 'user', 0, 0, 0, true)
        : NativeGraphNode(
            node.id,
            nativeGraphLabel(node.label),
            _classicNodeTypes.contains(node.nodeType) ? node.nodeType : 'concept',
            clamp(position.x),
            clamp(position.y),
            clamp(position.z),
          ));
  }
  final ids = {for (final node in nodes) node.id};
  final triples = <(String, String, String)>{};
  final edges = <NativeGraphEdge>[];
  for (final edge in simulation.edges) {
    final label = nativeGraphEdgeLabel(edge.label);
    // Truncation can make two long labels equal; one edge is enough to draw.
    if (!triples.add((edge.sourceId, edge.targetId, label))) continue;
    edges.add(NativeGraphEdge(edge.sourceId, edge.targetId, label));
  }
  final selected = controller.selectedNodeId;
  final highlighted = interactive && selected != null && ids.contains(selected)
      ? controller.highlightedNodeIds.where(ids.contains).take(NativeGraph.maxHighlighted).toSet()
      : const <String>{};
  final graph = NativeGraph(
    nodes: nodes,
    edges: edges,
    highlighted: highlighted,
    zoom: zoom.isFinite ? zoom.clamp(NativeGraph.minZoom, NativeGraph.maxZoom).toDouble() : 1.0,
    interactive: interactive,
    layout: layout,
    height: height?.clamp(NativeGraph.minCardHeight, NativeGraph.maxCardHeight).toDouble(),
    accent: memoryGraphAccentHex(),
  );
  return graph.valid ? graph : null;
}

/// The interactive graph row's value: the selected node while the projection highlights it, else ''.
String nativeGraphSelection(MemoryGraphController controller, NativeGraph graph) =>
    graph.highlighted.isEmpty ? '' : controller.selectedNodeId ?? '';
