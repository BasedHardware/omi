import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The completion mark of a task row (Tasks page, the shared-tasks sheet): a thin solid ring while
/// open, a filled disc with a check once done, both in the accent (black in light, white in dark).
/// Decorative — the tappable wrapper around it carries the semantics.
class TaskCompletionMark extends StatelessWidget {
  const TaskCompletionMark({super.key, required this.completed, this.size = 22});

  final bool completed;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: completed ? OmiColors.accent : Colors.transparent,
        border: completed ? null : Border.all(color: OmiColors.accent, width: 1.5),
      ),
      child: completed ? Icon(Icons.check, size: size * 0.64, color: OmiColors.onAccent) : null,
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
      child: selected ? Icon(Icons.check, size: 14, color: OmiColors.onAccent) : null,
    );
  }
}
