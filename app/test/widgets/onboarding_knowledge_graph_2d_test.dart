import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vector_math/vector_math_64.dart' as v;

import 'package:omi/pages/memories/widgets/memory_graph_page.dart';

void main() {
  test('onboarding 2D painter draws only white nodes and edges on black', () async {
    final nodes = [
      GraphNode3D(
        id: 'user-node',
        label: 'Me',
        nodeType: 'person',
        baseColor: Colors.purple,
        initialPosition: v.Vector3.zero(),
        isFixed: true,
      ),
      GraphNode3D(
        id: 'work',
        label: 'Work',
        nodeType: 'thing',
        baseColor: Colors.cyanAccent,
        initialPosition: v.Vector3(200, 80, 400),
      ),
    ];
    final edges = [GraphEdge3D(sourceId: 'user-node', targetId: 'work', label: 'does')];
    final painter = GraphPainter2D(nodes: nodes, edges: edges, panX: 0, panY: 0, zoom: 1);

    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    painter.paint(canvas, const Size(300, 400));
    final picture = recorder.endRecording();
    final image = await picture.toImage(300, 400);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    expect(bytes, isNotNull);

    var sawNonBlack = false;
    var sawPurple = false;
    var sawCyan = false;
    final data = bytes!.buffer.asUint8List();
    for (var i = 0; i < data.length; i += 4) {
      final r = data[i];
      final g = data[i + 1];
      final b = data[i + 2];
      final a = data[i + 3];
      if (a == 0) continue;
      if (r > 8 || g > 8 || b > 8) sawNonBlack = true;
      if (r > 80 && b > 80 && g < 40) sawPurple = true;
      if (g > 180 && b > 180 && r < 80) sawCyan = true;
    }

    expect(sawNonBlack, isTrue);
    expect(sawPurple, isFalse);
    expect(sawCyan, isFalse);
  });

  test('default MemoryGraphPage stays 3D', () {
    const page = MemoryGraphPage();
    expect(page.flat2d, isFalse);
    expect(page.embedded, isFalse);
  });
}
