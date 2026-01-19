import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart' show rootBundle;

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:vector_math/vector_math_64.dart' as v;

import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';

class GraphNode3D {
  final String id;
  final String label;
  final String nodeType;
  final Color baseColor;
  final bool isFixed;

  v.Vector3 position;
  v.Vector3 velocity;
  v.Vector3 force;

  double mass = 1.0;
  double radius = 12.0;

  GraphNode3D({
    required this.id,
    required this.label,
    required this.nodeType,
    required this.baseColor,
    required v.Vector3 initialPosition,
    this.isFixed = false,
  })  : position = initialPosition,
        velocity = v.Vector3.zero(),
        force = v.Vector3.zero();
}

class GraphEdge3D {
  final String sourceId;
  final String targetId;
  final String label;

  GraphEdge3D({
    required this.sourceId,
    required this.targetId,
    required this.label,
  });
}

class ForceDirectedSimulation3D {
  final List<GraphNode3D> nodes = [];
  final List<GraphEdge3D> edges = [];
  final Map<String, GraphNode3D> nodeMap = {};

  double repulsion = 120000.0;
  double attraction = 0.0015;
  double centerGravity = 0.0002;
  double damping = 0.9;
  double dt = 0.016;

  bool isStable = false;
  int _tickCounter = 0;
  int _stableCounter = 0;

  void wake() {
    isStable = false;
    _stableCounter = 0;
  }

  void addNode(GraphNode3D node) {
    nodes.add(node);
    nodeMap[node.id] = node;
  }

  void addEdge(GraphEdge3D edge) {
    edges.add(edge);
  }

  bool tick() {
    if (isStable) return false;

    _tickCounter++;
    if (_tickCounter % 4 != 0) return false;

    double totalEnergy = 0.0;
    final nodeCount = nodes.length;

    for (var node in nodes) {
      node.force.setZero();
    }

    final maxPairs = 5000;
    final totalPairs = (nodeCount * (nodeCount - 1)) ~/ 2;
    final skipFactor = totalPairs > maxPairs ? totalPairs ~/ maxPairs : 1;
    int pairIndex = 0;

    for (int i = 0; i < nodeCount; i++) {
      for (int j = i + 1; j < nodeCount; j++) {
        pairIndex++;
        if (skipFactor > 1 && pairIndex % skipFactor != 0) continue;

        final n1 = nodes[i];
        final n2 = nodes[j];

        final dx = n1.position.x - n2.position.x;
        final dy = n1.position.y - n2.position.y;
        final dz = n1.position.z - n2.position.z;
        double distSq = dx * dx + dy * dy + dz * dz;
        if (distSq < 1.0) distSq = 1.0;
        if (distSq > 10000000) continue;

        var forceVal = (repulsion * skipFactor) / distSq;
        final dist = sqrt(distSq);

        // Collision prevention
        if (dist < 100.0) {
          forceVal += (100.0 - dist) * 50.0;
        }

        final fx = (dx / dist) * forceVal;
        final fy = (dy / dist) * forceVal;
        final fz = (dz / dist) * forceVal;

        if (!n1.isFixed) {
          n1.force.x += fx;
          n1.force.y += fy;
          n1.force.z += fz;
        }
        if (!n2.isFixed) {
          n2.force.x -= fx;
          n2.force.y -= fy;
          n2.force.z -= fz;
        }
      }
    }

    for (var edge in edges) {
      final n1 = nodeMap[edge.sourceId];
      final n2 = nodeMap[edge.targetId];
      if (n1 == null || n2 == null) continue;

      final dx = n2.position.x - n1.position.x;
      final dy = n2.position.y - n1.position.y;
      final dz = n2.position.z - n1.position.z;
      final dist = sqrt(dx * dx + dy * dy + dz * dz);
      if (dist < 0.1) continue;

      const restLength = 1500.0;
      final forceVal = (dist - restLength) * attraction;
      final fx = (dx / dist) * forceVal;
      final fy = (dy / dist) * forceVal;
      final fz = (dz / dist) * forceVal;

      if (!n1.isFixed) {
        n1.force.x += fx;
        n1.force.y += fy;
        n1.force.z += fz;
      }
      if (!n2.isFixed) {
        n2.force.x -= fx;
        n2.force.y -= fy;
        n2.force.z -= fz;
      }
    }

    for (var node in nodes) {
      if (node.isFixed) continue;
      final cx = -node.position.x * centerGravity;
      final cy = -node.position.y * centerGravity;
      final cz = -node.position.z * centerGravity;
      node.force.x += cx;
      node.force.y += cy;
      node.force.z += cz;
    }

    for (var node in nodes) {
      if (node.isFixed) {
        node.velocity.setZero();
        node.position.setZero(); // Force to center
        continue;
      }

      node.velocity.x = (node.velocity.x + node.force.x * dt) * damping;
      node.velocity.y = (node.velocity.y + node.force.y * dt) * damping;
      node.velocity.z = (node.velocity.z + node.force.z * dt) * damping;

      final speed = node.velocity.length;
      totalEnergy += speed * speed;

      if (speed > 40.0) {
        final scale = 40.0 / speed;
        node.velocity.x *= scale;
        node.velocity.y *= scale;
        node.velocity.z *= scale;
      }

      node.position.x += node.velocity.x;
      node.position.y += node.velocity.y;
      node.position.z += node.velocity.z;
    }

    if (totalEnergy < 0.2) {
      _stableCounter++;
      if (_stableCounter > 10) {
        isStable = true;
      }
    } else {
      _stableCounter = 0;
    }

    return true;
  }
}

class MemoryGraphPage extends StatefulWidget {
  const MemoryGraphPage({super.key});

  @override
  State<MemoryGraphPage> createState() => _MemoryGraphPageState();
}

class _MemoryGraphPageState extends State<MemoryGraphPage> with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  late ForceDirectedSimulation3D simulation;
  late Ticker _ticker;

  final Random _rnd = Random();
  final GlobalKey _graphKey = GlobalKey();

  double _rotationX = 0.0;
  double _rotationY = 0.0;
  double _panX = 0.0;
  double _panY = 0.0;
  double _zoom = 1.0;
  double _baseZoom = 1.0;

  Offset? _lastPanStart;

  bool _isLoading = true;
  bool _isRebuilding = false;
  String? _error;

  final _repaintNotifier = ValueNotifier<int>(0);

  String? _selectedNodeId;
  Set<String> _highlightedNodeIds = {};

  @override
  void initState() {
    super.initState();
    simulation = ForceDirectedSimulation3D();
    WidgetsBinding.instance.addObserver(this);

    _ticker = createTicker((elapsed) {
      if (simulation.tick()) {
        _repaintNotifier.value++;
      } else if (_ticker.isTicking) {
        _ticker.stop();
      }
    });

    MixpanelManager().brainMapOpened();
    _loadGraph();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _ticker.dispose();
    _repaintNotifier.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _loadGraph(silent: true);
    }
  }

  void _runLayoutSync() {
    for (int i = 0; i < 200 && !simulation.isStable; i++) {
      simulation.tick();
    }
    _repaintNotifier.value++;
  }

  Future<void> _loadGraph({bool silent = false}) async {
    if (!silent) {
      setState(() {
        _isLoading = true;
        _error = null;
      });
    }

    try {
      final data = await KnowledgeGraphApi.getKnowledgeGraph();
      if (!mounted) return;

      final newNodes = data['nodes'] as List<dynamic>? ?? [];
      final newEdges = data['edges'] as List<dynamic>? ?? [];

      if (_isSameGraph(newNodes, newEdges)) {
        if (!silent) {
          setState(() {
            _isLoading = false;
          });
        }
        return;
      }

      _populateGraph(data);
      _runLayoutSync();
    } catch (e) {
      if (!mounted) return;
      if (!silent) {
        setState(() {
          _error = e.toString();
        });
      }
    } finally {
      if (mounted && !silent) {
        setState(() {
          _isLoading = false;
        });
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

  Future<void> _rebuildGraph() async {
    setState(() {
      _isRebuilding = true;
      _error = null;
    });

    try {
      MixpanelManager().brainMapRebuilt();
      await KnowledgeGraphApi.rebuildKnowledgeGraph();
      if (!mounted) return;

      final data = await KnowledgeGraphApi.waitForGraphStability();
      if (!mounted) return;

      _populateGraph(data);
      _runLayoutSync();

      simulation.wake();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _isRebuilding = false;
        });
      }
    }
  }

  void _populateGraph(Map<String, dynamic> data) {
    simulation.nodes.clear();
    simulation.edges.clear();
    simulation.nodeMap.clear();

    final nodes = data['nodes'] as List<dynamic>? ?? [];
    final edges = data['edges'] as List<dynamic>? ?? [];

    final userName = SharedPreferencesUtil().givenName;
    final userLabel = userName.isNotEmpty ? userName : 'Me';
    bool userNodeFound = false;

    for (var nodeData in nodes) {
      final label = nodeData['label'] as String? ?? '';
      final isUser = label.trim().toLowerCase() == userLabel.toLowerCase();

      if (isUser) userNodeFound = true;

      final node = GraphNode3D(
        id: nodeData['id'] ?? '',
        label: label,
        nodeType: nodeData['node_type'] ?? 'concept',
        baseColor: isUser ? Colors.white : _colorForType(nodeData['node_type'] ?? 'concept'),
        initialPosition: isUser ? v.Vector3.zero() : _randomPos3D(),
        isFixed: isUser,
      );

      if (isUser) node.position.setZero();

      simulation.addNode(node);
    }

    if (!userNodeFound) {
      if (!simulation.nodeMap.containsKey('user-node')) {
        final userNode = GraphNode3D(
          id: 'user-node',
          label: userLabel,
          nodeType: 'person',
          baseColor: Colors.white,
          initialPosition: v.Vector3.zero(),
          isFixed: true,
        );
        userNode.position.setZero();
        simulation.addNode(userNode);
      }
    }

    for (var edgeData in edges) {
      final edge = GraphEdge3D(
        sourceId: edgeData['source_id'] ?? '',
        targetId: edgeData['target_id'] ?? '',
        label: edgeData['label'] ?? '',
      );
      simulation.addEdge(edge);
    }

    simulation.wake();
    _repaintNotifier.value++;
  }

  v.Vector3 _randomPos3D({double spread = 1000.0}) {
    return v.Vector3(
      (_rnd.nextDouble() - 0.5) * spread,
      (_rnd.nextDouble() - 0.5) * spread,
      (_rnd.nextDouble() - 0.5) * spread,
    );
  }

  Color _colorForType(String nodeType) {
    switch (nodeType) {
      case 'person':
        return Colors.cyanAccent;
      case 'place':
        return const Color(0xFF00FF9D);
      case 'organization':
        return Colors.orangeAccent;
      case 'thing':
        return Colors.purpleAccent;
      default:
        return Colors.blueAccent;
    }
  }

  Future<void> _shareGraph() async {
    MixpanelManager().brainMapShareClicked();
    try {
      final boundary = _graphKey.currentContext?.findRenderObject() as RenderRepaintBoundary?;
      if (boundary == null) return;

      final image = await boundary.toImage(pixelRatio: 3.0);
      final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
      if (byteData == null) return;

      // Load branding requirements manually for the share image
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      final paint = Paint();

      // Draw graph image
      canvas.drawImage(image, Offset.zero, paint);

      // Draw minimal branding "omi.me" at top center
      final textSpan = TextSpan(
        text: 'omi.me',
        style: const TextStyle(
          color: Colors.white,
          fontSize: 72,
          fontWeight: FontWeight.bold,
          letterSpacing: -1.0,
        ),
      );
      final textPainter = TextPainter(
        text: textSpan,
        textDirection: TextDirection.ltr,
      );
      textPainter.layout();

      // Center horizontally, near top
      final xPos = (image.width - textPainter.width) / 2;
      final yPos = 140.0; // Margin from top (increased to avoid notch/edge feeling)

      textPainter.paint(canvas, Offset(xPos, yPos));

      final finalImage = await recorder.endRecording().toImage(image.width, image.height);
      final finalByteData = await finalImage.toByteData(format: ui.ImageByteFormat.png);
      if (finalByteData == null) return;

      final tempDir = await getTemporaryDirectory();
      final file = await File('${tempDir.path}/memory_graph.png').create();
      await file.writeAsBytes(finalByteData.buffer.asUint8List());

      await Share.shareXFiles([XFile(file.path)], text: 'Check out my memory graph!');
    } catch (e) {
      Logger.debug('Error sharing graph: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text(
          'omi.me',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        centerTitle: true,
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.share),
            onPressed: _shareGraph,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(color: Colors.purpleAccent),
            SizedBox(height: 16),
            Text('Loading Knowledge Graph...', style: TextStyle(color: Colors.white70)),
          ],
        ),
      );
    }

    if (_error != null) {
      return Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline, color: Colors.redAccent, size: 48),
              const SizedBox(height: 16),
              Text(_error!, style: const TextStyle(color: Colors.white70), textAlign: TextAlign.center),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: _loadGraph,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    // Check if graph is effectively empty (only has user node or truly empty)
    final bool isEmpty =
        simulation.nodes.isEmpty || (simulation.nodes.length == 1 && simulation.nodes.first.id == 'user-node');

    if (isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.hub_outlined, color: Colors.white30, size: 64),
              const SizedBox(height: 16),
              const Text('No knowledge graph yet', style: TextStyle(color: Colors.white70, fontSize: 18)),
              const SizedBox(height: 12),
              Text(
                _isRebuilding
                    ? 'Building your knowledge graph from memories...'
                    : 'Your knowledge graph will be built automatically as you create new memories.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white38, fontSize: 14),
              ),
              const SizedBox(height: 24),
              if (_isRebuilding)
                SizedBox(
                  width: 200,
                  child: LinearProgressIndicator(
                    backgroundColor: Colors.white10,
                    color: Colors.purpleAccent,
                    borderRadius: BorderRadius.circular(2),
                  ),
                )
              else
                ElevatedButton.icon(
                  onPressed: _rebuildGraph,
                  icon: const Icon(Icons.auto_fix_high),
                  label: const Text('Build Graph'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.purpleAccent.withOpacity(0.2),
                    foregroundColor: Colors.purpleAccent,
                  ),
                ),
            ],
          ),
        ),
      );
    }

    return LayoutBuilder(builder: (context, constraints) {
      return Stack(
        children: [
          GestureDetector(
            onTapUp: (details) => _handleTap(details, Size(constraints.maxWidth, constraints.maxHeight)),
            onScaleStart: (details) {
              simulation.wake();
              _lastPanStart = details.focalPoint;
              _baseZoom = _zoom;
            },
            onScaleUpdate: (details) {
              if (_lastPanStart != null) {
                final delta = details.focalPoint - _lastPanStart!;

                if (details.pointerCount >= 2) {
                  _panX += delta.dx;
                  _panY += delta.dy;
                  if (details.scale != 1.0) {
                    _zoom = _baseZoom * details.scale;
                    _zoom = _zoom.clamp(0.2, 5.0);
                  }
                } else {
                  _rotationY -= delta.dx * 0.005;
                  _rotationX += delta.dy * 0.005;
                }

                _lastPanStart = details.focalPoint;
                _repaintNotifier.value++;
              }
            },
            onScaleEnd: (_) => _lastPanStart = null,
            child: RepaintBoundary(
              key: _graphKey,
              child: ValueListenableBuilder<int>(
                valueListenable: _repaintNotifier,
                builder: (context, _, __) {
                  return CustomPaint(
                    size: Size.infinite,
                    painter: GraphPainter3D(
                      nodes: simulation.nodes,
                      edges: simulation.edges,
                      nodeMap: simulation.nodeMap,
                      rotationX: _rotationX,
                      rotationY: _rotationY,
                      panX: _panX,
                      panY: _panY,
                      zoom: _zoom,
                      highlightedNodeIds: _highlightedNodeIds,
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      );
    });
  }

  void _handleTap(TapUpDetails details, Size size) {
    // 1. CLEAR SELECTION if background tapped (default)
    String? hitNodeId;

    // 2. HIT TEST
    final centerX = size.width / 2;
    final centerY = size.height / 2;
    final cosY = cos(_rotationY);
    final sinY = sin(_rotationY);
    final cosX = cos(_rotationX);
    final sinX = sin(_rotationX);

    // Sort nodes by depth (z) to hit the front-most one, similar to painter
    // Actually painter sorts by Z, but for hit test we can just check distance in 2D
    // But front nodes should block back nodes?
    // For simplicity, we just find the closest node to the tap within a radius.
    // If overlapping, maybe closest Z wins? Let's just do simple radius check.

    double minDist = 30.0; // Hit radius
    _ProjectedNode? closestHit;

    for (var node in simulation.nodes) {
      // Manual Projection
      final px = node.position.x;
      final py = node.position.y;
      final pz = node.position.z;
      final x1 = px * cosY - pz * sinY;
      final z1 = px * sinY + pz * cosY;
      final y2 = py * cosX - z1 * sinX;
      final z2 = py * sinX + z1 * cosX;
      const cameraZ = 1500.0;

      if (cameraZ - z2 <= 0) continue; // Behind camera

      final perspective = (cameraZ / (cameraZ - z2)) * _zoom;
      final projX = centerX + x1 * perspective + _panX;
      final projY = centerY + y2 * perspective + _panY;

      final dist = (Offset(projX, projY) - details.localPosition).distance;

      // Dynamic radius based on scale
      final radius = 12.0 * perspective;
      // Give it a bit of padding for easier tapping
      final hitThreshold = max(radius * 1.5, 20.0);

      if (dist < hitThreshold && dist < minDist) {
        minDist = dist;
        // Store simplified projected info for z-check if needed, but simple min dist is okay for sparse graphs
        closestHit = _ProjectedNode(node: node, x: projX, y: projY, z: z2, scale: perspective, alpha: 1.0);
      }
    }

    if (closestHit != null) {
      hitNodeId = closestHit.node.id;
    }

    if (hitNodeId == _selectedNodeId && hitNodeId != null) {
      // Toggle off if tapping same node? Or maybe keep it?
      // User might want to deselect. Let's allowing toggling off.
      hitNodeId = null;
    }

    setState(() {
      _selectedNodeId = hitNodeId;
      _highlightedNodeIds.clear();

      if (hitNodeId != null) {
        _highlightedNodeIds.add(hitNodeId!);

        final node = simulation.nodeMap[hitNodeId];
        if (node != null) {
          MixpanelManager().brainMapNodeClicked(node.id, node.label, node.nodeType);
        }

        // Find neighbors
        final neighbors = <String>[];
        for (var edge in simulation.edges) {
          if (edge.sourceId == hitNodeId) neighbors.add(edge.targetId);
          if (edge.targetId == hitNodeId) neighbors.add(edge.sourceId);
        }

        // "Closest 4" - sorting by 3D distance
        // We need the GraphNode3D objects
        final centerNode = simulation.nodeMap[hitNodeId];
        if (centerNode != null) {
          neighbors.sort((a, b) {
            final na = simulation.nodeMap[a];
            final nb = simulation.nodeMap[b];
            if (na == null || nb == null) return 0;
            // distSq
            final da = _distSq(centerNode.position, na.position);
            final db = _distSq(centerNode.position, nb.position);
            return da.compareTo(db);
          });
        }

        // Take top 4 and add them
        _highlightedNodeIds.addAll(neighbors.take(4));
      }
    });
  }

  double _distSq(v.Vector3 a, v.Vector3 b) {
    final dx = a.x - b.x;
    final dy = a.y - b.y;
    final dz = a.z - b.z;
    return dx * dx + dy * dy + dz * dz;
  }
}

class GraphPainter3D extends CustomPainter {
  final List<GraphNode3D> nodes;
  final List<GraphEdge3D> edges;
  final Map<String, GraphNode3D> nodeMap;
  final double rotationX;
  final double rotationY;
  final double panX;
  final double panY;
  final double zoom;
  final bool screenshotMode;
  final Set<String> highlightedNodeIds;

  final Paint _edgePaint = Paint()..strokeCap = StrokeCap.round;
  final Paint _nodePaint = Paint();
  final Paint _ringPaint = Paint()..style = PaintingStyle.stroke;

  GraphPainter3D({
    required this.nodes,
    required this.edges,
    required this.nodeMap,
    required this.rotationX,
    required this.rotationY,
    required this.panX,
    required this.panY,
    required this.zoom,
    this.screenshotMode = false,
    this.highlightedNodeIds = const {},
  });

  @override
  void paint(Canvas canvas, Size size) {
    final centerX = size.width / 2;
    final centerY = size.height / 2;

    final cosY = cos(rotationY);
    final sinY = sin(rotationY);
    final cosX = cos(rotationX);
    final sinX = sin(rotationX);

    final projectedNodes = <_ProjectedNode>[];
    final projectedMap = <String, _ProjectedNode>{};

    for (var node in nodes) {
      final px = node.position.x;
      final py = node.position.y;
      final pz = node.position.z;

      final x1 = px * cosY - pz * sinY;
      final z1 = px * sinY + pz * cosY;

      final y2 = py * cosX - z1 * sinX;
      final z2 = py * sinX + z1 * cosX;

      const cameraZ = 1500.0;
      final perspective = (cameraZ / (cameraZ - z2)) * zoom;

      final projectedX = centerX + x1 * perspective + panX;
      final projectedY = centerY + y2 * perspective + panY;

      final alpha = (1.0 + (z2 / 2500.0)).clamp(0.0, 1.0);

      // Dimming logic
      double finalAlpha = alpha;
      if (highlightedNodeIds.isNotEmpty && !highlightedNodeIds.contains(node.id)) {
        finalAlpha *= 0.15; // Dim significantly
      }

      final proj = _ProjectedNode(
        node: node,
        x: projectedX,
        y: projectedY,
        z: z2,
        scale: perspective,
        alpha: finalAlpha,
      );

      projectedNodes.add(proj);
      projectedMap[node.id] = proj;
    }

    projectedNodes.sort((a, b) => a.z.compareTo(b.z));

    for (var edge in edges) {
      final p1 = projectedMap[edge.sourceId];
      final p2 = projectedMap[edge.targetId];
      if (p1 == null || p2 == null) continue;

      final alpha = ((p1.alpha + p2.alpha) / 2.0 * 0.25).clamp(0.0, 1.0);
      if (alpha < 0.05) continue;

      _edgePaint.color = Colors.white.withOpacity(alpha);
      _edgePaint.strokeWidth = 0.8 * ((p1.scale + p2.scale) / 2);

      // Drawn above with logic

      final avgScale = (p1.scale + p2.scale) / 2;

      // Highlight edge if BOTH nodes are in the highlighted set
      final isHighlightedEdge =
          highlightedNodeIds.contains(edge.sourceId) && highlightedNodeIds.contains(edge.targetId);
      final isDimmed = highlightedNodeIds.isNotEmpty && !isHighlightedEdge;

      if (isDimmed) {
        _edgePaint.color = _edgePaint.color.withOpacity(alpha * 0.1);
      } else if (isHighlightedEdge) {
        _edgePaint.color = Colors.white.withOpacity(max(alpha, 0.8)); // Pop
      }

      canvas.drawLine(Offset(p1.x, p1.y), Offset(p2.x, p2.y), _edgePaint);

      if (edge.label.isNotEmpty && avgScale > 0.6 && alpha > 0.1 && (!isDimmed || isHighlightedEdge)) {
        final midX = (p1.x + p2.x) / 2;
        final midY = (p1.y + p2.y) / 2;
        final textSpan = TextSpan(
          text: edge.label,
          style: TextStyle(
            color: Colors.white54.withOpacity(alpha * 2),
            fontSize: (9 * avgScale).clamp(7, 11),
          ),
        );
        final tp = TextPainter(text: textSpan, textDirection: TextDirection.ltr);
        tp.layout();
        tp.paint(canvas, Offset(midX - tp.width / 2, midY - tp.height / 2 - 8));
      }
    }

    for (var p in projectedNodes) {
      final node = p.node;
      final centerOffset = Offset(p.x, p.y);
      final radius = node.radius * p.scale;

      if (radius < 0.5) continue;

      if (radius > 3) {
        _ringPaint.color = node.baseColor.withOpacity(p.alpha * 0.3);
        _ringPaint.strokeWidth = 1.5 * p.scale;
        canvas.drawCircle(centerOffset, radius * 1.8, _ringPaint);

        _ringPaint.color = node.baseColor.withOpacity(p.alpha * 0.15);
        _ringPaint.strokeWidth = 1.0 * p.scale;
        canvas.drawCircle(centerOffset, radius * 2.5, _ringPaint);
      }

      final gradient = ui.Gradient.radial(
        centerOffset + Offset(-radius * 0.25, -radius * 0.25),
        radius * 1.2,
        [
          Colors.white.withOpacity(p.alpha * 0.9),
          Color.lerp(Colors.white, node.baseColor, 0.5)!.withOpacity(p.alpha),
          node.baseColor.withOpacity(p.alpha),
        ],
        [0.0, 0.3, 1.0],
      );
      _nodePaint.shader = gradient;
      canvas.drawCircle(centerOffset, radius, _nodePaint);
      _nodePaint.shader = null;

      final showLabel = screenshotMode || (p.scale > 0.7 && p.alpha > 0.5 && radius > 4);
      if (showLabel) {
        final textSpan = TextSpan(
          text: node.label,
          style: TextStyle(
            color: Colors.white.withOpacity(screenshotMode ? 0.95 : p.alpha * 0.9),
            fontSize: screenshotMode ? 11.0 : (10 * p.scale).clamp(8, 14),
            fontWeight: FontWeight.w600,
          ),
        );
        final tp = TextPainter(text: textSpan, textDirection: TextDirection.ltr);
        tp.layout();
        tp.paint(canvas, centerOffset + Offset(-tp.width / 2, radius + 3));
      }
    }
  }

  @override
  bool shouldRepaint(covariant GraphPainter3D oldDelegate) => true;
}

class _ProjectedNode {
  final GraphNode3D node;
  final double x;
  final double y;
  final double z;
  final double scale;
  final double alpha;

  _ProjectedNode({
    required this.node,
    required this.x,
    required this.y,
    required this.z,
    required this.scale,
    required this.alpha,
  });
}
