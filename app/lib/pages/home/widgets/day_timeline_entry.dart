import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/widgets/task_completion_circle.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

/// One conversation on the home day timeline: when it happened, what it was
/// about, how long it ran, and the tasks it produced.
class DayTimelineEntry extends StatelessWidget {
  const DayTimelineEntry({
    super.key,
    required this.conversation,
    required this.tasks,
    required this.onTap,
    required this.onToggleTask,
    this.dimmed = false,
    this.showTopDivider = true,
  });

  final ServerConversation conversation;
  final List<ActionItemWithMetadata> tasks;
  final VoidCallback onTap;
  final void Function(ActionItemWithMetadata task) onToggleTask;

  /// Short and discarded conversations render quieter than the day's real ones.
  final bool dimmed;

  /// The first row of a day sits directly under the header, where a rule would
  /// read as a box around the headline rather than as a list separator.
  final bool showTopDivider;

  static const double _timeColumnWidth = 58;

  @override
  Widget build(BuildContext context) {
    final startedAt = (conversation.startedAt ?? conversation.createdAt).toLocal();
    final durationSeconds = conversation.getDurationInSeconds();

    // The rule is inset on the left to line up with the time column and runs to
    // the screen edge on the right, so the day reads as one continuous list.
    return Container(
      margin: const EdgeInsets.only(left: 24),
      decoration: showTopDivider
          ? BoxDecoration(border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.06))))
          : null,
      padding: const EdgeInsets.fromLTRB(0, 15, 24, 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: _timeColumnWidth,
            child: Padding(
              // Right gap so a long label can never touch the title.
              padding: const EdgeInsets.only(top: 1, right: 8),
              child: Text(
                timelineTimeLabel(context, startedAt),
                maxLines: 1,
                overflow: TextOverflow.clip,
                style: TextStyle(color: Colors.white.withValues(alpha: dimmed ? 0.3 : 0.45), fontSize: 13),
              ),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onTap,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          conversationTitle(context, conversation),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: dimmed ? 0.55 : 1),
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                            height: 1.25,
                            letterSpacing: -0.2,
                          ),
                        ),
                      ),
                      if (durationSeconds > 0) ...[
                        const SizedBox(width: 10),
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                            formatConversationDuration(durationSeconds),
                            style: TextStyle(color: Colors.white.withValues(alpha: 0.4), fontSize: 13),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                for (final task in tasks) _DayTimelineTask(task: task, onToggle: () => onToggleTask(task)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DayTimelineTask extends StatelessWidget {
  const _DayTimelineTask({required this.task, required this.onToggle});

  final ActionItemWithMetadata task;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final due = taskDueLabel(context, task);

    return Padding(
      padding: const EdgeInsets.only(top: 20),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              HapticFeedback.lightImpact();
              onToggle();
            },
            child: Padding(
              padding: const EdgeInsets.only(right: 12),
              child: TaskCompletionCircle(completed: task.completed, size: 20),
            ),
          ),
          Expanded(
            child: Text(
              task.description.decodeString,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: task.completed ? Colors.white.withValues(alpha: 0.35) : Colors.white.withValues(alpha: 0.85),
                fontSize: 15,
                height: 1.3,
                decoration: task.completed ? TextDecoration.lineThrough : null,
                decorationColor: Colors.white.withValues(alpha: 0.35),
              ),
            ),
          ),
          if (due != null) ...[
            const SizedBox(width: 10),
            Padding(
              padding: const EdgeInsets.only(top: 1),
              child: Text(
                due.label,
                style: TextStyle(
                  color: due.overdue ? const Color(0xFFFF5C47) : Colors.white.withValues(alpha: 0.4),
                  fontSize: 13,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// A discarded conversation has no generated title — show what was said instead,
/// the same way the conversations list does.
String conversationTitle(BuildContext context, ServerConversation conversation) {
  if (conversation.discarded) {
    final transcript = conversation.getTranscript(maxCount: 80).trim();
    if (transcript.isNotEmpty) return transcript;
  }
  final title = conversation.structured.title.decodeString.trim();
  return title.isNotEmpty ? title : context.l10n.untitledConversation;
}

/// The start time as the day timeline shows it: "9:02", not "9:02 AM".
///
/// The rows are already ordered through the day, so the meridiem only adds
/// width to the narrowest column on the screen. Locales on a 24-hour clock keep
/// their own format, which is unambiguous already.
String timelineTimeLabel(BuildContext context, DateTime at) {
  final localizations = MaterialLocalizations.of(context);
  final use24Hour = MediaQuery.maybeOf(context)?.alwaysUse24HourFormat ?? false;
  final formatted = localizations.formatTimeOfDay(TimeOfDay.fromDateTime(at), alwaysUse24HourFormat: use24Hour);
  if (use24Hour) return formatted;
  return formatted
      .replaceAll(localizations.anteMeridiemAbbreviation, '')
      .replaceAll(localizations.postMeridiemAbbreviation, '')
      // Some locales separate the meridiem with a non-breaking or narrow space.
      .replaceAll(RegExp(r'[\s\u00A0\u202F]+'), ' ')
      .trim();
}

String formatConversationDuration(int seconds) {
  if (seconds < 60) return '${seconds}s';
  final minutes = seconds ~/ 60;
  if (minutes < 60) return '${minutes}m';
  final hours = minutes ~/ 60;
  final remainder = minutes % 60;
  return remainder == 0 ? '${hours}h' : '${hours}h ${remainder}m';
}

/// The trailing due marker on a task row. Past-due open tasks read red; the
/// next week reads as a weekday, anything further out as a date.
({String label, bool overdue})? taskDueLabel(BuildContext context, ActionItemWithMetadata task) {
  final due = task.dueAt?.toLocal();
  if (due == null) return null;

  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final dueDay = DateTime(due.year, due.month, due.day);

  if (dueDay.isBefore(today)) {
    return task.completed
        ? (label: MaterialLocalizations.of(context).formatMediumDate(dueDay), overdue: false)
        : (label: context.l10n.overdue, overdue: true);
  }
  if (dueDay == today) return (label: context.l10n.today, overdue: false);
  if (dueDay == DateTime(now.year, now.month, now.day + 1)) return (label: context.l10n.tomorrow, overdue: false);
  if (dueDay.isBefore(DateTime(now.year, now.month, now.day + 7))) {
    return (label: _weekdayLabel(context, dueDay), overdue: false);
  }
  return (label: MaterialLocalizations.of(context).formatMediumDate(dueDay), overdue: false);
}

/// "Fri" out of the localized medium date ("Fri, Sep 5"). Locales that don't
/// lead with a weekday keep the full medium date.
String _weekdayLabel(BuildContext context, DateTime day) {
  final mediumDate = MaterialLocalizations.of(context).formatMediumDate(day);
  final separator = mediumDate.indexOf(',');
  return separator > 0 ? mediumDate.substring(0, separator) : mediumDate;
}
