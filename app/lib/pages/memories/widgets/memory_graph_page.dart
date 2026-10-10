// Copyright 2024 BasedHardware Ltd
// SPDX-License-Identifier: Apache-2.0

import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/app/lib/pages/memories/models/memory_node_model.dart';
import 'package:omi/app/lib/pages/memories/models/graph_edge_model.dart';
import 'package:omi/app/lib/widgets/graph/edge_line.dart';
import 'package:omi/app/lib/widgets/graph/node_circle.dart';
import 'package:omi/app/lib/constants/app_colors.dart';
import 'package:reactive/reactive.dart';

/// A 3D knowledge graph visualization rendered with a perspective camera.
///
/// Nodes are positioned using a force-directed layout simulation. The camera
/// sits at a fixed distance (`kCameraDistance`) along the Z axis, and nodes
/// start in a random cube around the origin. Spring rest length (`kRestLength`)
/// controls how far apart connected nodes tend to sit.
///
/// This widget computes its own AABB after layout so callers can frame-fit it.
class MemoryGraphPage extends StatefulWidget {
  final List<MemoryNodeModel> nodes;
  final List<GraphEdgeModel> edges;
  final Color nodeColor;
  final Color edgeColor;
  final bool showEdges;
  final bool showNodes;
  final VoidCallback? onNodeTap;

  const MemoryGraphPage({
    super.key,
    required this.nodes,
    required this.edges,
    this.nodeColor = AppColors.primary,
    this.edgeColor = AppColors.muted,
    this.showEdges = true,
    this.showNodes = true,
    this.onNodeTap,
  });

  @override
  State<MemoryGraphPage> createState() => _MemoryGraphPageState();
}

class _MemoryGraphPageState extends State<MemoryGraphPage>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final ReactiveModel<Vector3d> _cameraPosition;
  late final ReactiveModel<double> _cameraZoom;
  final ReactiveModel<Size> _panelSize = ReactiveModel<Size>(Size.zero);
  final ReactiveModel<bool> _isLaidOut = ReactiveModel<bool>(false);

  // Physics constants.
  static const double kRestLength = 1500.0;
  static const double kSpringStrength = 0.001;
  static const double kRepulsionStrength = 500000.0;
  static const double kGravityStrength = 0.0001;
  static const double kDamping = 0.85;
  static const int kIterationsPerFrame = 3;
  static const double kCameraDistance = 1500.0;
  static const double kInitialZoom = 1.0;
  static const double kFramingPadding = 0.15;

  final Map<int, Vector3d> _nodePositions = {};
  final Set<int> _pinnedNodes = {};
  final List<Vector3d> _velocities = [];

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _cameraPosition = ReactiveModel<Vector3d>(Vector3d(0, 0, kCameraDistance));
    _cameraZoom = ReactiveModel<double>(kInitialZoom);
    _initializePositions();
    _startSimulation();
  }

  void _initializePositions() {
    final random = math.Random();
    for (final node in widget.nodes) {
      _nodePositions[node.id] = Vector3d(
        (random.nextDouble() - 0.5) * 1000,
        (random.nextDouble() - 0.5) * 1000,
        (random.nextDouble() - 0.5) * 1000,
      );
      _velocities.add(Vector3d(0, 0, 0));
    }
  }

  void _startSimulation() {
    _controller.repeat(period: const Duration(milliseconds: 16));
    _controller.addListener(_simulateStep);
  }

  void _simulateStep() {
    for (var i = 0; i < kIterationsPerFrame; i++) {
      _applyForces();
    }
    _updatePositions();
  }

  void _applyForces() {
    final nodes = widget.nodes;
    final edges = widget.edges;

    // Repulsion between all pairs.
    for (var i = 0; i < nodes.length; i++) {
      for (var j = i + 1; j < nodes.length; j++) {
        final p1 = _nodePositions[nodes[i].id]!;
        final p2 = _nodePositions[nodes[j].id]!;
        final diff = p1 - p2;
        final dist = math.max(diff.length, 1.0);
        final force = kRepulsionStrength / (dist * dist);
        final dir = diff.normalize();
        _velocities[i] = _velocities[i] + dir * force;
        _velocities[j] = _velocities[j] - dir * force;
      }
    }

    // Spring attraction along edges.
    for (final edge in edges) {
      final p1 = _nodePositions[edge.sourceId]!;
      final p2 = _nodePositions[edge.targetId]!;
      final diff = p1 - p2;
      final dist = diff.length;
      final displacement = dist - kRestLength;
      final force = kSpringStrength * displacement;
      final dir = diff.normalize();
      _velocities[edge.sourceIndex] = _velocities[edge.sourceIndex] - dir * force;
      _velocities[edge.targetIndex] = _velocities[edge.targetIndex] + dir * force;
    }

    // Gravity toward center.
    for (var i = 0; i < nodes.length; i++) {
      final pos = _nodePositions[nodes[i].id]!;
      final toCenter = -pos;
      _velocities[i] = _velocities[i] + toCenter * kGravityStrength;
    }
  }

  void _updatePositions() {
    for (var i = 0; i < widget.nodes.length; i++) {
      if (_pinnedNodes.contains(widget.nodes[i].id)) continue;
      _velocities[i] = _velocities[i] * kDamping;
      _nodePositions[widget.nodes[i].id] =
          _nodePositions[widget.nodes[i].id]! + _velocities[i];
    }
  }

  /// Compute the axis-aligned bounding box of all nodes in world space.
  ///
  /// Returns [null] if there are no nodes.
  AABB? _computeBounds() {
    if (widget.nodes.isEmpty) return null;
    var minX = double.infinity, minY = double.infinity, minZ = double.infinity;
    var maxX = double.negativeInfinity, maxY = double.negativeInfinity, maxZ = double.negativeInfinity;
    for (final node in widget.nodes) {
      final pos = _nodePositions[node.id]!;
      minX = math.min(minX, pos.x);
      minY = math.min(minY, pos.y);
      minZ = math.min(minZ, pos.z);
      maxX = math.max(maxX, pos.x);
      maxY = math.max(maxY, pos.y);
      maxZ = math.max(maxZ, pos.z);
    }
    return AABB(
      min: Vector3d(minX, minY, minZ),
      max: Vector3d(maxX, maxY, maxZ),
    );
  }

  /// Frame-fit the camera so all nodes fit within the panel with padding.
  ///
  /// Called after the first layout pass when the panel size is known.
  void _frameToFit() {
    final bounds = _computeBounds();
    if (bounds == null) return;

    final center = bounds.center;
    final size = _panelSize.value;
    if (size.isEmpty) return;

    // Fit within the smaller dimension to preserve aspect ratio.
    final worldSize = math.max(bounds.diagonal.x, bounds.diagonal.y);
    final minPanelDim = math.min(size.width, size.height);
    final neededZoom = minPanelDim / (worldSize * (1 + kFramingPadding));
    final clampedZoom = math.max(0.2, math.min(3.0, neededZoom));

    _cameraZoom.value = clampedZoom;
    _cameraPosition.value = Vector3d(center.x, center.y, kCameraDistance);
    _isLaidOut.value = true;
  }

  void _handleTap(int nodeId) {
    if (widget.onNodeTap != null) widget.onNodeTap!(nodeId);
  }

  @override
  void didUpdateWidget(MemoryGraphPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Re-initialize positions if the node list changed significantly.
    if (oldWidget.nodes.length != widget.nodes.length) {
      _initializePositions();
      _startSimulation();
    }
  }

  @override
  Widget build(BuildContext context) {
    return ResponsiveBuilder(
      builder: (context, constraints) {
        _panelSize.value = constraints.biggest;
        if (!_isLaidOut.value) {
          WidgetsBinding.instance.addPostFrameCallback((_) => _frameToFit());
        }
        return Stack(
          children: [
            _buildGraph(),
            _buildControls(),
          ],
        );
      },
    );
  }

  Widget _buildGraph() {
    return ClipRect(
      child: ReactiveBuilder<Vector3d>(
        model: _cameraPosition,
        builder: (context, camPos, _) {
          return ReactiveBuilder<double>(
            model: _cameraZoom,
            builder: (context, zoom, _) {
              return CustomPaint(
                size: Size.infinite,
                painter: _GraphPainter(
                  nodes: widget.nodes,
                  edges: widget.edges,
                  positions: _nodePositions,
                  cameraPos: camPos,
                  zoom: zoom,
                  nodeColor: widget.nodeColor,
                  edgeColor: widget.edgeColor,
                  showEdges: widget.showEdges,
                  showNodes: widget.showNodes,
                  onTap: _handleTap,
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _buildControls() {
    return Positioned(
      bottom: 16,
      left: 16,
      right: 16,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _IconButton(
            icon: Icons.zoom_in,
            onTap: () => _cameraZoom.value = (_cameraZoom.value * 1.2).clamp(0.2, 5.0),
          ),
          _IconButton(
            icon: Icons.zoom_out,
            onTap: () => _cameraZoom.value = (_cameraZoom.value / 1.2).clamp(0.2, 5.0),
            onLongPress: () => _frameToFit(),
          ),
          _IconButton(
            icon: Icons.replay,
            onTap: () {
              _initializePositions();
              _frameToFit();
            },
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }
}

class _GraphPainter extends CustomPainter {
  final List<MemoryNodeModel> nodes;
  final List<GraphEdgeModel> edges;
  final Map<int, Vector3d> positions;
  final Vector3d cameraPos;
  final double zoom;
  final Color nodeColor;
  final Color edgeColor;
  final bool showEdges;
  final bool showNodes;
  final void Function(int) onTap;

  _GraphPainter({
    required this.nodes,
    required this.edges,
    required this.positions,
    required this.cameraPos,
    required this.zoom,
    required this.nodeColor,
    required this.edgeColor,
    required this.showEdges,
    required this.showNodes,
    required this.onTap,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final matrix = _buildMatrix(size);
    canvas.save();
    canvas.transform(matrix);

    if (showEdges) {
      for (final edge in edges) {
        final p1 = _project(edge.sourcePos, size);
        final p2 = _project(edge.targetPos, size);
        if (p1 != null && p2 != null) {
          canvas.drawLine(p1!, p2!, Paint()..color = edgeColor);
        }
      }
    }

    if (showNodes) {
      for (final node in nodes) {
        final pos = positions[node.id]!;
        final screenPos = _project(pos, size);
        if (screenPos != null) {
          canvas.drawCircle(
            screenPos,
            20 * zoom,
            Paint()..color = nodeColor,
          );
        }
      }
    }

    canvas.restore();
  }

  Vector3d? _project(Vector3d worldPos, Size size) {
    final offset = worldPos - cameraPos;
    if (offset.z <= 0) return null;
    final scale = zoom * size.width / offset.z;
    return Vector2d(
      size.width / 2 + offset.x * scale,
      size.height / 2 - offset.y * scale,
    );
  }

  List<double> _buildMatrix(Size size) {
    // Simple affine transform for perspective projection.
    return [
      zoom * size.width, 0, 0, 0,
      0, zoom * size.height, 0, 0,
      0, 0, 1, 0,
      size.width / 2, size.height / 2, 0, 1,
    ];
  }

  @override
  bool shouldRepaint(_GraphPainter oldDelegate) {
    return oldDelegate.nodes != nodes ||
        oldDelegate.edges != edges ||
        oldDelegate.positions != positions ||
        oldDelegate.cameraPos != cameraPos ||
        oldDelegate.zoom != zoom;
  }
}

class AABB {
  final Vector3d min;
  final Vector3d max;

  AABB({required this.min, required this.max});

  Vector3d get center => Vector3d(
    (min.x + max.x) / 2,
    (min.y + max.y) / 2,
    (min.z + max.z) / 2,
  );

  double get diagonal {
    final dx = max.x - min.x;
    final dy = max.y - min.y;
    final dz = max.z - min.z;
    return math.sqrt(dx * dx + dy * dy + dz * dz);
  }
}

class Vector3d {
  final double x, y, z;
  const Vector3d(this.x, this.y, this.z);

  Vector3d operator +(Vector3d other) => Vector3d(x + other.x, y + other.y, z + other.z);
  Vector3d operator -(Vector3d other) => Vector3d(x - other.x, y - other.y, z - other.z);
  Vector3d operator *(double scalar) => Vector3d(x * scalar, y * scalar, z * scalar);
  Vector3d normalize() {
    final len = length;
    return len > 0 ? Vector3d(x / len, y / len, z / len) : Vector3d(0, 0, 0);
  }

  double get length => math.sqrt(x * x + y * y + z * z);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Vector3d && x == other.x && y == other.y && z == other.z;

  @override
  int get hashCode => Object.hash(x, y, z);
}

class Vector2d {
  final double x, y;
  const Vector2d(this.x, this.y);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Vector2d && x == other.x && y == other.y;

  @override
  int get hashCode => Object.hash(x, y);
}

class _IconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final VoidCallback? onLongPress;

  const _IconButton({
    required this.icon,
    required this.onTap,
    this.onLongPress,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.card.withOpacity(0.8),
      borderRadius: BorderRadius.circular(24),
      child: InkWell(
        borderRadius: BorderRadius.circular(24),
        onTap: onTap,
        onLongPress: onLongPress,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Icon(icon, color: AppColors.text, size: 24),
        ),
      ),
    );
  }
}
