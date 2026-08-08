import 'hud_content.dart';

/// A task reduced to what a HUD can show. Keeping the projector off the wire
/// schema means it stays unit-testable without generated types.
class HudTask {
  final String description;
  final DateTime? dueAt;
  final String? priority;
  final bool completed;

  const HudTask({
    required this.description,
    this.dueAt,
    this.priority,
    this.completed = false,
  });
}

/// Projects app state onto a display-glasses HUD.
///
/// The line budget is the whole problem: a glasses HUD shows a handful of
/// lines, so the projector decides what survives rather than letting a caller
/// push an unbounded list and have the renderer clip it silently.
class HudProjector {
  final int maxLines;
  final int maxLineChars;

  const HudProjector({this.maxLines = 5, this.maxLineChars = 48});

  static const Map<String, int> _priorityRank = {'high': 0, 'medium': 1, 'low': 2};

  HudScreen tasks(List<HudTask> tasks, {DateTime? now}) {
    final pending = tasks.where((t) => !t.completed).toList();
    if (pending.isEmpty) {
      return const HudScreen(
        kind: HudScreenKind.tasks,
        title: 'Tasks',
        lines: [HudLine('Nothing due', style: HudLineStyle.meta, muted: true)],
      );
    }

    final reference = now ?? DateTime.now();
    pending.sort((a, b) => _taskOrder(a, b, reference));

    final overflow = pending.length > maxLines;
    final shown = overflow ? pending.take(maxLines - 1) : pending.take(maxLines);

    final lines = <HudLine>[
      for (final task in shown) HudLine(_truncate(task.description)),
    ];
    if (overflow) {
      lines.add(HudLine('+${pending.length - lines.length} more', style: HudLineStyle.meta, muted: true));
    }

    return HudScreen(
      kind: HudScreenKind.tasks,
      title: 'Tasks',
      lines: lines,
      actions: const [HudAction('tasks.next', 'Next'), HudAction('tasks.done', 'Done')],
    );
  }

  HudScreen capture({required bool recording, String? lastLine}) {
    final lines = <HudLine>[
      HudLine(recording ? 'Listening' : 'Paused', style: HudLineStyle.meta, muted: !recording),
    ];
    final trimmed = lastLine?.trim();
    if (trimmed != null && trimmed.isNotEmpty) {
      lines.add(HudLine(_truncate(trimmed)));
    }
    return HudScreen(
      kind: HudScreenKind.capture,
      title: 'Omi',
      lines: lines,
      actions: [HudAction('capture.toggle', recording ? 'Pause' : 'Resume')],
    );
  }

  HudScreen answer(String question, String answer) {
    final lines = <HudLine>[
      HudLine(_truncate(question.trim()), style: HudLineStyle.meta, muted: true),
      ..._wrap(answer.trim(), maxLines - 1),
    ];
    return HudScreen(
      kind: HudScreenKind.answer,
      title: 'Omi',
      lines: lines,
      actions: const [HudAction('answer.dismiss', 'Dismiss')],
    );
  }

  int _taskOrder(HudTask a, HudTask b, DateTime now) {
    final aDue = a.dueAt;
    final bDue = b.dueAt;
    if (aDue != null && bDue != null && aDue != bDue) return aDue.compareTo(bDue);
    if (aDue != null && bDue == null) return -1;
    if (aDue == null && bDue != null) return 1;

    final aRank = _priorityRank[a.priority?.toLowerCase()] ?? _priorityRank.length;
    final bRank = _priorityRank[b.priority?.toLowerCase()] ?? _priorityRank.length;
    if (aRank != bRank) return aRank.compareTo(bRank);

    return a.description.compareTo(b.description);
  }

  String _truncate(String text) {
    final collapsed = text.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (collapsed.length <= maxLineChars) return collapsed;
    return '${collapsed.substring(0, maxLineChars - 1).trimRight()}…';
  }

  List<HudLine> _wrap(String text, int budget) {
    if (budget <= 0) return const [];
    final collapsed = text.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (collapsed.isEmpty) return const [];

    final lines = <String>[];
    var remaining = collapsed;
    while (remaining.isNotEmpty && lines.length < budget) {
      if (remaining.length <= maxLineChars) {
        lines.add(remaining);
        break;
      }
      final isLast = lines.length == budget - 1;
      if (isLast) {
        lines.add(_truncate(remaining));
        break;
      }
      var cut = remaining.lastIndexOf(' ', maxLineChars);
      if (cut <= 0) cut = maxLineChars;
      lines.add(remaining.substring(0, cut).trimRight());
      remaining = remaining.substring(cut).trimLeft();
    }
    return [for (final line in lines) HudLine(line)];
  }
}
