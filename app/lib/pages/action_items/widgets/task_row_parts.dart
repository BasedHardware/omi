import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

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

/// The display name of a task app a task was exported to; unknown platforms keep their id.
String taskExportPlatformLabel(String platform) {
  switch (platform) {
    case 'todoist':
      return 'Todoist';
    case 'asana':
      return 'Asana';
    case 'google_tasks':
      return 'Google Tasks';
    case 'clickup':
      return 'ClickUp';
    case 'apple_reminders':
      return 'Reminders';
    default:
      return platform;
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
      child: selected ? Icon(Icons.check, size: 14, color: OmiColors.onAccent) : null,
    );
  }
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

/// Vertical padding of a task section header: the space above the label line
/// and the sliver of space between it and the first task row.
const EdgeInsets taskSectionHeaderLinePadding = EdgeInsets.only(top: 16, bottom: 4);

/// A section header's label ("TODAY", "OVERDUE").
// Title Case like OmiSectionHeader (the contract's section header is not all caps), at a label's
// size so the groups stay quieter than the page title.
final TextStyle taskSectionLabelStyle = OmiType.footnote.copyWith(
  color: OmiColors.textTertiary,
  fontWeight: FontWeight.w600,
);

/// The count beside a section header, read out as "3 tasks" rather than a bare number.
class TaskSectionCount extends StatelessWidget {
  const TaskSectionCount(this.count, {super.key});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Text(
      '$count',
      semanticsLabel: context.l10n.tasksCountLabel(count),
      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
    );
  }
}

/// A tappable part of a task section header.
///
/// Section headers are one 12pt line of text, which made the collapse chevrons
/// ~19pt targets and the "clear completed" ✕ a 14pt one. A task row starts 4pt
/// below the line, so there is no room to grow a target downwards. Instead the
/// header's vertical padding moves inside each child ([taskSectionHeaderLinePadding])
/// and the tappable ones own it, plus [reach] of width on the side that faces
/// the header's Spacer. The child stays where it was on the text line and
/// nothing in the list moves; the target becomes the header's full 36pt height.
class TaskSectionHeaderTapTarget extends StatelessWidget {
  const TaskSectionHeaderTapTarget(
      {super.key, required this.onTap, required this.child, required this.reach, this.semanticLabel});

  final VoidCallback onTap;
  final Widget child;
  final EdgeInsets reach;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticLabel,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Padding(padding: taskSectionHeaderLinePadding + reach, child: child),
      ),
    );
  }
}
