import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The completion mark of a task row (Tasks page, Home's Today card): a quiet dashed ring while
/// open, a filled amber disc with a check once done. Decorative — the tappable wrapper around it
/// carries the semantics.
class TaskCompletionMark extends StatelessWidget {
  const TaskCompletionMark({super.key, required this.completed, this.size = 22});

  final bool completed;
  final double size;

  /// Done tasks and reached goals share this colour.
  static const Color doneColor = Colors.amber;

  @override
  Widget build(BuildContext context) {
    if (completed) {
      return Container(
        width: size,
        height: size,
        decoration: const BoxDecoration(shape: BoxShape.circle, color: doneColor),
        child: Icon(Icons.check, size: size * 0.64, color: OmiColors.onAccent),
      );
    }
    // Dashed outline: quieter than a solid ring so the task title carries the visual weight.
    return CustomPaint(
      size: Size(size, size),
      painter: _DashedCirclePainter(color: OmiColors.textTertiary, strokeWidth: 1.5, dashLength: 3, gapLength: 3),
    );
  }
}

/// Trailing selection box shown only in selection mode: a rounded **square**, a different shape
/// from the leading completion circle so "selected for a bulk action" never reads as "done".
class TaskSelectionSquare extends StatelessWidget {
  const TaskSelectionSquare({super.key, required this.selected});

  final bool selected;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: OmiMotion.of(context).quick,
      width: 22,
      height: 22,
      decoration: BoxDecoration(
        borderRadius: const BorderRadius.all(Radius.circular(6)),
        border: Border.all(color: selected ? OmiColors.accent : OmiColors.textTertiary, width: 2),
        color: selected ? OmiColors.accent : Colors.transparent,
      ),
      child: selected ? const Icon(Icons.check, size: 14, color: OmiColors.onAccent) : null,
    );
  }
}

/// A goal's progress as a filled pie inside a ring.
class GoalProgressPainter extends CustomPainter {
  GoalProgressPainter({required this.progress, required this.color});

  final double progress;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..color = color.withValues(alpha: 0.2)
        ..style = PaintingStyle.fill,
    );

    if (progress > 0) {
      final rect = Rect.fromCircle(center: center, radius: radius);
      canvas.drawArc(
        rect,
        -math.pi / 2,
        progress * 2 * math.pi,
        true,
        Paint()
          ..color = color
          ..style = PaintingStyle.fill,
      );
    }

    canvas.drawCircle(
      center,
      radius - 1,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );
  }

  @override
  bool shouldRepaint(GoalProgressPainter oldDelegate) => oldDelegate.progress != progress || oldDelegate.color != color;
}

class _DashedCirclePainter extends CustomPainter {
  _DashedCirclePainter({
    required this.color,
    required this.strokeWidth,
    required this.dashLength,
    required this.gapLength,
  });

  final Color color;
  final double strokeWidth;
  final double dashLength;
  final double gapLength;

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
    final segments = (circumference / (dashLength + gapLength)).floor();
    final adjustedSegment = circumference / segments;
    final dashAngle = (dashLength / adjustedSegment) * (2 * math.pi / segments);
    final stepAngle = 2 * math.pi / segments;

    for (var i = 0; i < segments; i++) {
      canvas.drawArc(Rect.fromCircle(center: center, radius: radius), i * stepAngle, dashAngle, false, paint);
    }
  }

  @override
  bool shouldRepaint(_DashedCirclePainter oldDelegate) =>
      oldDelegate.color != color ||
      oldDelegate.strokeWidth != strokeWidth ||
      oldDelegate.dashLength != dashLength ||
      oldDelegate.gapLength != gapLength;
}
