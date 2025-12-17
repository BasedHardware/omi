import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:vector_math/vector_math_64.dart' as v;

class GraphNode3D {
  final String id;
  final String label;
  final String nodeType;
  final Color baseColor;

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

        n1.force.x += fx;
        n1.force.y += fy;
        n1.force.z += fz;
        n2.force.x -= fx;
        n2.force.y -= fy;
        n2.force.z -= fz;
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

      n1.force.x += fx;
      n1.force.y += fy;
      n1.force.z += fz;
      n2.force.x -= fx;
      n2.force.y -= fy;
      n2.force.z -= fz;
    }

    for (var node in nodes) {
      final cx = -node.position.x * centerGravity;
      final cy = -node.position.y * centerGravity;
      final cz = -node.position.z * centerGravity;
      node.force.x += cx;
      node.force.y += cy;
      node.force.z += cz;
    }

    for (var node in nodes) {
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
  Timer? _refreshTimer;

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

    _loadGraph();
    _startAutoRefresh();
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
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

  void _startAutoRefresh() {
    _refreshTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted && !_isLoading && !_isRebuilding) {
        _loadGraph(silent: true);
      }
    });
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
    if (newNodes.length != simulation.nodes.length) return false;
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

    for (var nodeData in nodes) {
      final node = GraphNode3D(
        id: nodeData['id'] ?? '',
        label: nodeData['label'] ?? '',
        nodeType: nodeData['node_type'] ?? 'concept',
        baseColor: _colorForType(nodeData['node_type'] ?? 'concept'),
        initialPosition: _randomPos3D(),
      );
      simulation.addNode(node);
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
    try {
      final boundary = _graphKey.currentContext?.findRenderObject() as RenderRepaintBoundary?;
      if (boundary == null) return;

      final size = boundary.size;
      const double scale = 3.0;
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);

      final int width = (size.width * scale).toInt();
      final int height = (size.height * scale).toInt();

      canvas.drawRect(Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble()), Paint()..color = Colors.black);

      final screenshotPainter = GraphPainter3D(
        nodes: simulation.nodes,
        edges: simulation.edges,
        nodeMap: simulation.nodeMap,
        rotationX: _rotationX,
        rotationY: _rotationY,
        panX: _panX * scale,
        panY: _panY * scale,
        zoom: _zoom * scale,
        screenshotMode: true,
      );
      screenshotPainter.paint(canvas, Size(width.toDouble(), height.toDouble()));

      final Paint paint = Paint();

      final ByteData logoData = await rootBundle.load('assets/images/herologo.png');
      final Uint8List logoBytes = logoData.buffer.asUint8List();
      final ui.Codec codec = await ui.instantiateImageCodec(logoBytes);
      final ui.FrameInfo frameInfo = await codec.getNextFrame();
      final ui.Image logoImage = frameInfo.image;

      const double logoHeight = 100.0;
      final double logoScale = logoHeight / logoImage.height;
      final double logoWidth = logoImage.width * logoScale;

      canvas.drawImageRect(
        logoImage,
        Rect.fromLTWH(0, 0, logoImage.width.toDouble(), logoImage.height.toDouble()),
        Rect.fromLTWH(50, height - logoHeight - 50, logoWidth, logoHeight),
        paint,
      );

      final textSpan = TextSpan(
        text: 'omi.me',
        style: TextStyle(
          color: Colors.white.withOpacity(0.85),
          fontSize: 42,
          fontWeight: FontWeight.w500,
        ),
      );

      final textPainter = TextPainter(
        text: textSpan,
        textDirection: TextDirection.ltr,
      );
      textPainter.layout();
      textPainter.paint(canvas, Offset(50 + logoWidth + 20, height - logoHeight / 2 - textPainter.height / 2 - 50));

      final ui.Image brandedImage = await recorder.endRecording().toImage(width, height);
      final ByteData? brandedByteData = await brandedImage.toByteData(format: ui.ImageByteFormat.png);
      if (brandedByteData == null) return;

      final Uint8List pngBytes = brandedByteData.buffer.asUint8List();

      final tempDir = await getTemporaryDirectory();
      final file = File('${tempDir.path}/omi_knowledge_graph.png');
      await file.writeAsBytes(pngBytes);

      await Share.shareXFiles([XFile(file.path)], text: 'Check out my OMI Knowledge Graph! 🧠');
    } catch (e) {
      debugPrint('Error sharing graph: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Knowledge Graph', style: TextStyle(color: Colors.white70)),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.purpleAccent.withOpacity(0.2),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: Colors.purpleAccent.withOpacity(0.5)),
              ),
              child: const Text('BETA', style: TextStyle(color: Colors.purpleAccent, fontSize: 10, fontWeight: FontWeight.bold)),
            ),
          ],
        ),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        leading: const BackButton(color: Colors.white),
        actions: [
          if (simulation.nodes.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.ios_share, color: Colors.white),
              onPressed: _shareGraph,
              tooltip: 'Share',
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

    if (simulation.nodes.isEmpty) {
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

    return GestureDetector(
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
              ),
            );
          },
        ),
      ),
    );
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

      final proj = _ProjectedNode(
        node: node,
        x: projectedX,
        y: projectedY,
        z: z2,
        scale: perspective,
        alpha: alpha,
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

      canvas.drawLine(Offset(p1.x, p1.y), Offset(p2.x, p2.y), _edgePaint);

      final avgScale = (p1.scale + p2.scale) / 2;
      if (edge.label.isNotEmpty && avgScale > 0.6 && alpha > 0.1) {
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
