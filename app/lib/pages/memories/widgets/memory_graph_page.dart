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
  double radius = 15.0;

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

  double repulsion = 75000.0;
  double attraction = 0.002;
  double centerGravity = 0.0003;
  double damping = 0.88;
  double dt = 0.016;
  
  bool isStable = false;
  int _tickCounter = 0;

  void wake() {
    isStable = false;
  }

  void addNode(GraphNode3D node) {
    nodes.add(node);
    nodeMap[node.id] = node;
  }

  void addEdge(GraphEdge3D edge) {
    edges.add(edge);
  }

  void tick() {
    if (isStable) return;

    _tickCounter++;
    if (_tickCounter % 3 != 0) return;
    
    double totalEnergy = 0.0;
    
    for (var node in nodes) {
      node.force.setZero();
    }

    for (int i = 0; i < nodes.length; i++) {
      for (int j = i + 1; j < nodes.length; j++) {
        final n1 = nodes[i];
        final n2 = nodes[j];

        v.Vector3 delta = n1.position - n2.position;
        double distSq = delta.length2;
        if (distSq < 1.0) distSq = 1.0;

        double forceVal = repulsion / distSq;

        v.Vector3 param = delta.normalized() * forceVal;
        n1.force += param;
        n2.force -= param;
      }
    }

    for (var edge in edges) {
      final n1 = nodeMap[edge.sourceId];
      final n2 = nodeMap[edge.targetId];
      if (n1 == null || n2 == null) continue;

      v.Vector3 delta = n2.position - n1.position;
      double distance = delta.length;
      double restLength = 1800.0;

      double forceVal = (distance - restLength) * attraction;

      v.Vector3 param = delta.normalized() * forceVal;
      n1.force += param;
      n2.force -= param;
    }

    for (var node in nodes) {
      v.Vector3 toCenter = -node.position;
      node.force += toCenter.normalized() * (toCenter.length * centerGravity * node.mass);
    }

    for (var node in nodes) {
      v.Vector3 acceleration = node.force / node.mass;
      node.velocity += acceleration * dt;
      node.velocity *= damping;
      
      totalEnergy += node.velocity.length2;

      if (node.velocity.length > 50.0) {
        node.velocity = node.velocity.normalized() * 50.0;
      }

      node.position += node.velocity;
    }
    
    if (totalEnergy < 0.3) {
      isStable = true;
    }
  }
}

class MemoryGraphPage extends StatefulWidget {
  const MemoryGraphPage({super.key});

  @override
  State<MemoryGraphPage> createState() => _MemoryGraphPageState();
}

class _MemoryGraphPageState extends State<MemoryGraphPage> with SingleTickerProviderStateMixin {
  late ForceDirectedSimulation3D simulation;
  late Ticker _ticker;

  final Random _rnd = Random();
  final GlobalKey _graphKey = GlobalKey();

  double _rotationX = 0.0;
  double _rotationY = 0.0;
  double _zoom = 1.0;
  double _baseZoom = 1.0;

  Offset? _lastPanStart;

  bool _isLoading = true;
  bool _isRebuilding = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    simulation = ForceDirectedSimulation3D();

    _ticker = createTicker((elapsed) {
      simulation.tick();
      setState(() {});
    });

    _loadGraph();
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  Future<void> _loadGraph() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final data = await KnowledgeGraphApi.getKnowledgeGraph();
      if (!mounted) return;
      _populateGraph(data);
      _ticker.start();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _rebuildGraph() async {
    setState(() {
      _isRebuilding = true;
      _error = null;
    });

    try {
      await KnowledgeGraphApi.rebuildKnowledgeGraph();
      if (!mounted) return;
      
      await Future.delayed(const Duration(seconds: 3));
      if (!mounted) return;
      
      await _loadGraph();
      if (!mounted) return;
      
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
  }

  v.Vector3 _randomPos3D({double spread = 800.0}) {
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

      final ui.Image image = await boundary.toImage(pixelRatio: 2.0);
      final ByteData? byteData = await image.toByteData(format: ui.ImageByteFormat.png);
      if (byteData == null) return;

      // Add Branding
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      final int width = image.width;
      final int height = image.height;

      final Paint paint = Paint();
      canvas.drawImage(image, Offset.zero, paint);

      // Load Logo
      final ByteData logoData = await rootBundle.load('assets/images/herologo.png');
      final Uint8List logoBytes = logoData.buffer.asUint8List();
      final ui.Codec codec = await ui.instantiateImageCodec(logoBytes);
      final ui.FrameInfo frameInfo = await codec.getNextFrame();
      final ui.Image logoImage = frameInfo.image;

      // Draw Logo
      final double logoHeight = 80.0;
      final double logoScale = logoHeight / logoImage.height;
      final double logoWidth = logoImage.width * logoScale;

      canvas.drawImageRect(
        logoImage,
        Rect.fromLTWH(0, 0, logoImage.width.toDouble(), logoImage.height.toDouble()),
        Rect.fromLTWH(40, height - logoHeight - 40, logoWidth, logoHeight),
        paint,
      );

      // Draw Text
      final textSpan = TextSpan(
        children: [
          const TextSpan(
            text: 'OMI',
            style: TextStyle(
              color: Colors.white,
              fontSize: 48,
              fontWeight: FontWeight.bold,
              fontFamily: 'SF Pro Display',
            ),
          ),
          TextSpan(
            text: ' | omi.me',
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 32,
              fontFamily: 'SF Pro Display',
            ),
          ),
        ],
      );

      final textPainter = TextPainter(
        text: textSpan,
        textDirection: TextDirection.ltr,
      );
      textPainter.layout();
      // Draw text to the right of the logo
      textPainter.paint(canvas, Offset(40 + logoWidth + 24, height - textPainter.height - 50));

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
        title: const Text('Knowledge Graph', style: TextStyle(color: Colors.white70)),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        leading: const BackButton(color: Colors.white),
        actions: [
          if (_isRebuilding)
            const Padding(
              padding: EdgeInsets.all(16.0),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
              ),
            )
          else
            IconButton(
              icon: const Icon(Icons.refresh, color: Colors.white),
              onPressed: _rebuildGraph,
              tooltip: 'Regenerate Graph',
            ),
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
            CircularProgressIndicator(color: Colors.cyanAccent),
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
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.hub_outlined, color: Colors.white30, size: 64),
            const SizedBox(height: 16),
            const Text('No knowledge graph yet', style: TextStyle(color: Colors.white70, fontSize: 18)),
            const SizedBox(height: 8),
            const Text('Tap rebuild to generate from your memories', style: TextStyle(color: Colors.white38)),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _isRebuilding ? null : _rebuildGraph,
              icon: const Icon(Icons.auto_fix_high),
              label: const Text('Build Graph'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.cyanAccent.withOpacity(0.2),
                foregroundColor: Colors.cyanAccent,
              ),
            ),
          ],
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
        simulation.wake();
        if (_lastPanStart != null) {
          final delta = details.focalPoint - _lastPanStart!;

          setState(() {
            if (details.scale == 1.0) {
              _rotationY += delta.dx * 0.005;
              _rotationX -= delta.dy * 0.005;
            }

            if (details.scale != 1.0) {
              _zoom = _baseZoom * details.scale;
              _zoom = _zoom.clamp(0.2, 5.0);
            }
          });

          _lastPanStart = details.focalPoint;
        }
      },
      onScaleEnd: (_) => _lastPanStart = null,
        child: RepaintBoundary(
          key: _graphKey,
          child: CustomPaint(
            size: Size.infinite,
            painter: GraphPainter3D(
              nodes: simulation.nodes,
              edges: simulation.edges,
              nodeMap: simulation.nodeMap,
              rotationX: _rotationX,
              rotationY: _rotationY,
              zoom: _zoom,
            ),
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
  final double zoom;

  GraphPainter3D({
    required this.nodes,
    required this.edges,
    required this.nodeMap,
    required this.rotationX,
    required this.rotationY,
    required this.zoom,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = v.Vector2(size.width / 2, size.height / 2);

    List<_ProjectedNode> projectedNodes = [];
    Map<String, _ProjectedNode> projectedMap = {};

    for (var node in nodes) {
      var p = v.Vector3.copy(node.position);

      double x = p.x * cos(rotationY) - p.z * sin(rotationY);
      double z = p.x * sin(rotationY) + p.z * cos(rotationY);
      p.x = x;
      p.z = z;

      double y = p.y * cos(rotationX) - p.z * sin(rotationX);
      z = p.y * sin(rotationX) + p.z * cos(rotationX);
      p.y = y;
      p.z = z;

      double cameraZ = 1200.0;
      double perspective = cameraZ / (cameraZ - p.z);
      perspective *= zoom;

      final projectedX = center.x + p.x * perspective;
      final projectedY = center.y + p.y * perspective;

      double alpha = (1.0 + (p.z / 2000.0)).clamp(0.0, 1.0);

      final proj = _ProjectedNode(
        node: node,
        x: projectedX,
        y: projectedY,
        z: p.z,
        scale: perspective,
        alpha: alpha,
      );

      projectedNodes.add(proj);
      projectedMap[node.id] = proj;
    }

    projectedNodes.sort((a, b) => a.z.compareTo(b.z));

    final Paint edgePaint = Paint()..strokeCap = StrokeCap.round;

    for (var edge in edges) {
      final p1 = projectedMap[edge.sourceId];
      final p2 = projectedMap[edge.targetId];

      if (p1 == null || p2 == null) continue;

      double alpha = (p1.alpha + p2.alpha) / 2.0;
      alpha *= 0.3;

      edgePaint.color = Colors.white.withOpacity(alpha.clamp(0.0, 1.0));
      edgePaint.strokeWidth = 1.0 * ((p1.scale + p2.scale) / 2);

      canvas.drawLine(Offset(p1.x, p1.y), Offset(p2.x, p2.y), edgePaint);

      if (edge.label.trim().isNotEmpty && alpha > 0.1) {
        final midX = (p1.x + p2.x) / 2;
        final midY = (p1.y + p2.y) / 2;

        final textSpan = TextSpan(
          text: edge.label,
          style: TextStyle(
            color: Colors.cyanAccent.withOpacity(p1.alpha),
            fontSize: 12 * p1.scale,
            fontWeight: FontWeight.w500,
            shadows: const [Shadow(blurRadius: 4, color: Colors.black)],
          ),
        );
        final tp = TextPainter(text: textSpan, textDirection: TextDirection.ltr);
        tp.layout();
        tp.paint(canvas, Offset(midX - tp.width / 2, midY - tp.height / 2));
      }
    }

    for (var p in projectedNodes) {
      final node = p.node;
      final centerOffset = Offset(p.x, p.y);
      final radius = node.radius * p.scale;

      final glowRadius = radius * 3.0;
      if (glowRadius > 1.0) {
        final glowPaint = Paint()
          ..shader = ui.Gradient.radial(
            centerOffset,
            glowRadius,
            [
              node.baseColor.withOpacity(p.alpha * 0.8),
              node.baseColor.withOpacity(0.0),
            ],
          );
        canvas.drawCircle(centerOffset, glowRadius, glowPaint);
      }

      canvas.drawCircle(
        centerOffset,
        radius,
        Paint()..color = node.baseColor.withOpacity(p.alpha),
      );

      if (p.scale > 0.6 && p.alpha > 0.4) {
        final textSpan = TextSpan(
          text: node.label,
          style: TextStyle(
            color: Colors.white.withOpacity(p.alpha),
            fontSize: 12 * p.scale,
            fontWeight: FontWeight.bold,
            shadows: [Shadow(blurRadius: 3, color: Colors.black.withOpacity(p.alpha))],
          ),
        );
        final tp = TextPainter(text: textSpan, textDirection: TextDirection.ltr);
        tp.layout();
        tp.paint(canvas, centerOffset + Offset(-tp.width / 2, radius + 4));
      }
    }
  }

  @override
  bool shouldRepaint(covariant GraphPainter3D oldDelegate) {
    return true;
  }
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
