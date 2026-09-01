import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Completion indicator for a task row: a dashed outline circle while the task
/// is open, a filled check once it is done.
///
/// Shared by the tasks page and the home day timeline so both surfaces read as
/// the same control.
class TaskCompletionCircle extends StatelessWidget {
  const TaskCompletionCircle({super.key, required this.completed, this.size = 22});

  final bool completed;
  final double size;

  @override
  Widget build(BuildContext context) {
    if (completed) {
      return Container(
        width: size,
        height: size,
        decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.amber),
        child: Icon(Icons.check, size: size * 0.64, color: Colors.black),
      );
    }
    return CustomPaint(
      size: Size(size, size),
      painter: DashedCirclePainter(color: Colors.grey[500]!, strokeWidth: 1.5, dashLength: 3, gapLength: 3),
    );
  }
}

class DashedCirclePainter extends CustomPainter {
  final Color color;
  final double strokeWidth;
  final double dashLength;
  final double gapLength;

  DashedCirclePainter({
    required this.color,
    required this.strokeWidth,
    required this.dashLength,
    required this.gapLength,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width / 2) - (strokeWidth / 2);
    final circumference = 2 * math.pi * radius;
    final segmentLength = dashLength + gapLength;
    final segments = (circumference / segmentLength).floor();
    if (segments <= 0) return;
    final adjustedSegment = circumference / segments;
    final dashAngle = (dashLength / adjustedSegment) * (2 * math.pi / segments);
    final stepAngle = 2 * math.pi / segments;

    for (var i = 0; i < segments; i++) {
      canvas.drawArc(Rect.fromCircle(center: center, radius: radius), i * stepAngle, dashAngle, false, paint);
    }
  }

  @override
  bool shouldRepaint(DashedCirclePainter oldDelegate) =>
      oldDelegate.color != color ||
      oldDelegate.strokeWidth != strokeWidth ||
      oldDelegate.dashLength != dashLength ||
      oldDelegate.gapLength != gapLength;
}
