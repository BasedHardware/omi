import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The completion mark of a task row (To do, Home's Up next): a thin ring while open, a disc in
/// the label colour with a check once done (v2 `Tasks`, the same mark as Home's Getting started).
/// Decorative — the tappable wrapper around it carries the semantics.
class TaskCompletionMark extends StatelessWidget {
  const TaskCompletionMark({super.key, required this.completed, this.size = 22});

  final bool completed;
  final double size;

  /// Done tasks and reached goals share this colour.
  static Color get doneColor => OmiColors.accent;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: completed ? doneColor : null,
        border: completed ? null : Border.all(color: OmiColors.textTertiary, width: 1.5),
      ),
      child: completed ? Icon(Icons.check_rounded, size: size * 0.7, color: OmiColors.onAccent) : null,
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

/// The name of an export destination ("Todoist", "Reminders") as a task row shows it.
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

/// A task row's second line (canvas Tasks): when it is due (amber today, red when overdue) and
/// the conversation it came from ("from App UX and battery"). Nothing when it has neither.
class TaskSubline extends StatelessWidget {
  const TaskSubline({super.key, required this.item});

  final ActionItemWithMetadata item;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final due = item.dueAt?.toLocal();
    String? source;
    final conversationId = item.conversationId;
    if (conversationId != null) {
      for (final c in context.read<ConversationProvider>().conversations) {
        if (c.id == conversationId) {
          final title = c.structured.title.trim();
          if (title.isNotEmpty) source = l10n.fromConversation(title);
          break;
        }
      }
    }
    if (due == null && source == null) return const SizedBox.shrink();
    String? dueText;
    Color? dueColor;
    if (due != null) {
      final dates = OmiDateFormat.of(context);
      final now = DateTime.now();
      final endOfToday = DateTime(now.year, now.month, now.day + 1);
      dueText = l10n.taskDueDayTime(dates.dayHeader(due), dates.time(due));
      if (!item.completed) {
        dueColor = due.isBefore(now) ? OmiColors.danger : (due.isBefore(endOfToday) ? OmiColors.warning : null);
      }
    }
    return Padding(
      padding: const EdgeInsets.only(top: 3),
      child: Text.rich(
        TextSpan(
          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          children: [
            if (dueText != null) TextSpan(text: dueText, style: dueColor == null ? null : TextStyle(color: dueColor)),
            if (dueText != null && source != null) const TextSpan(text: ' · '),
            if (source != null) TextSpan(text: source),
          ],
        ),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}

/// A section's tasks on one card, a hairline between rows (canvas Tasks).
class TaskSectionCard extends StatelessWidget {
  const TaskSectionCard({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return OmiCard(
      clip: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (i, child) in children.indexed) ...[
            if (i > 0) Divider(height: 0.5, thickness: 0.5, indent: 52, color: OmiColors.border),
            child,
          ],
        ],
      ),
    );
  }
}
