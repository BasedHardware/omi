import 'package:flutter/widgets.dart' show StringCharacters;

/// Node types the native renderer colours. Producers map anything else to 'concept', as the
/// classic graph does; 'user' is the account's own node and takes the accent colour.
const nativeGraphNodeTypes = {'user', 'person', 'place', 'organization', 'thing', 'concept'};

/// A node label within [NativeGraph.maxLabelLength], so real-world data truncates instead of making
/// the whole surface fall back.
String nativeGraphLabel(String label) => _truncated(label, NativeGraph.maxLabelLength);

/// An edge label within [NativeGraph.maxEdgeLabelLength].
String nativeGraphEdgeLabel(String label) => _truncated(label, NativeGraph.maxEdgeLabelLength);

/// Cuts on a character boundary and ends with an ellipsis; the result fits [limit] UTF-16 units.
String _truncated(String label, int limit) {
  if (label.length <= limit) return label;
  final kept = StringBuffer();
  var length = 0;
  for (final character in label.characters) {
    if (length + character.length > limit - 1) break;
    kept.write(character);
    length += character.length;
  }
  return '$kept…';
}

/// One positioned node from the existing simulation owner. Coordinates are the owner's 3D layout;
/// the native camera projects them and never reports a position back.
class NativeGraphNode {
  const NativeGraphNode(this.id, this.label, this.type, this.x, this.y, this.z, [this.fixed = false]);

  final String id, label, type;
  final double x, y, z;

  /// The pinned centre node: at most one, of type 'user', at the origin.
  final bool fixed;

  Map<String, Object?> get projection =>
      {'id': id, 'label': label, 'type': type, 'x': x, 'y': y, 'z': z, 'fixed': fixed};
}

class NativeGraphEdge {
  const NativeGraphEdge(this.source, this.target, [this.label = '']);

  final String source, target, label;

  Map<String, Object?> get projection => {'source': source, 'target': target, 'label': label};
}

/// A knowledge graph drawn by the native renderer as a 'graph' row.
///
/// A 'card' is a fixed-height, non-interactive list row whose tap sends null. A 'fill' graph owns a
/// non-scrolling stage (labels above, buttons below) and, when [interactive], sends '' or a node id
/// on tap. Rotation, pan and zoom stay native and are never sent back. A graph over the limits
/// ([fits] is false), or otherwise invalid, is not projectable: the page keeps its classic Flutter
/// graph for it. Labels are truncated with [nativeGraphLabel] and [nativeGraphEdgeLabel] first.
class NativeGraph {
  const NativeGraph({
    required this.nodes,
    required this.edges,
    this.highlighted = const {},
    this.zoom = 1.0,
    this.interactive = true,
    this.layout = 'fill',
    this.height,
    required this.accent,
  }) : placeholder = false;

  /// A skeleton shown while the owner loads; it has no nodes or edges and sends no node.
  const NativeGraph.placeholder({this.layout = 'fill', this.height, required this.accent})
      : nodes = const [],
        edges = const [],
        highlighted = const {},
        zoom = 1.0,
        interactive = false,
        placeholder = true;

  static const maxNodes = 1024;
  static const maxEdges = 4096;
  static const maxIdLength = 256;
  static const maxLabelLength = 256;
  static const maxEdgeLabelLength = 128;
  static const maxHighlighted = 5;
  static const maxCoordinate = 1e6;
  static const minZoom = 0.05;
  static const maxZoom = 5.0;
  static const minCardHeight = 100.0;
  static const maxCardHeight = 600.0;

  /// Whether a graph of this size can be projected at all. Larger graphs keep the classic page.
  static bool fits(int nodes, int edges) => nodes >= 0 && nodes <= maxNodes && edges >= 0 && edges <= maxEdges;

  final List<NativeGraphNode> nodes;
  final List<NativeGraphEdge> edges;

  /// The selected node and its neighbours; non-highlighted elements dim while it is not empty.
  final Set<String> highlighted;

  /// The initial camera zoom. The native camera resets to it when the node set changes.
  final double zoom;
  final bool interactive, placeholder;

  /// 'fill' or 'card'.
  final String layout;

  /// Required for a card, in [minCardHeight]..[maxCardHeight]; null for a fill graph.
  final double? height;

  /// '#RRGGBB' for the user node.
  final String accent;

  Set<String> get nodeIds => {for (final node in nodes) node.id};

  Map<String, Object?> get projection => {
        'nodes': [for (final node in nodes) node.projection],
        'edges': [for (final edge in edges) edge.projection],
        'highlighted': highlighted.toList()..sort(),
        'zoom': zoom,
        'interactive': interactive,
        'layout': layout,
        'height': height,
        'placeholder': placeholder,
        'accent': accent,
      };

  /// The graph's own rules; NativeRow adds the value rules and IosNativeSurface the snapshot rules.
  /// NativeSurfaceContract.swift validates identically. Lengths count UTF-16 units on both sides.
  bool get valid {
    if (!RegExp(r'^#[0-9A-Fa-f]{6}$').hasMatch(accent) || !zoom.isFinite || zoom < minZoom || zoom > maxZoom) {
      return false;
    }
    final cardHeight = height;
    switch (layout) {
      case 'card':
        if (cardHeight == null || !cardHeight.isFinite || cardHeight < minCardHeight || cardHeight > maxCardHeight) {
          return false;
        }
        if (interactive) return false;
      case 'fill':
        if (cardHeight != null) return false;
      default:
        return false;
    }
    if (placeholder) return nodes.isEmpty && edges.isEmpty && highlighted.isEmpty && !interactive;
    if (nodes.isEmpty || nodes.length > maxNodes || edges.length > maxEdges) return false;
    final ids = <String>{};
    var fixed = 0;
    for (final node in nodes) {
      if (node.id.isEmpty || node.id.length > maxIdLength || !ids.add(node.id)) return false;
      if (node.label.length > maxLabelLength || !nativeGraphNodeTypes.contains(node.type)) return false;
      if ([node.x, node.y, node.z].any((value) => !value.isFinite || value.abs() > maxCoordinate)) return false;
      if (node.fixed && (++fixed > 1 || node.type != 'user' || node.x != 0 || node.y != 0 || node.z != 0)) {
        return false;
      }
    }
    final triples = <(String, String, String)>{};
    for (final edge in edges) {
      if (edge.source == edge.target ||
          !ids.contains(edge.source) ||
          !ids.contains(edge.target) ||
          edge.label.length > maxEdgeLabelLength ||
          !triples.add((edge.source, edge.target, edge.label))) {
        return false;
      }
    }
    return highlighted.length <= maxHighlighted && ids.containsAll(highlighted);
  }
}
