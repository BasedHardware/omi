import 'package:flutter/widgets.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Confirms merging the selected conversations, warning when there is more than an hour between two
/// of them. Drawn by the shared dialog system (`showOmiConfirm`).
abstract final class MergeConfirmationDialog {
  /// Gaps of more than an hour between consecutive conversations, as compact lengths ("1h 30m").
  static List<String>? _checkForLargeGaps(BuildContext context, List<ServerConversation> conversations) {
    if (conversations.length < 2) return null;

    // Sort by start time
    final sorted = List<ServerConversation>.from(conversations);
    sorted.sort((a, b) => (a.startedAt ?? a.createdAt).compareTo(b.startedAt ?? b.createdAt));

    final gaps = <String>[];
    for (int i = 1; i < sorted.length; i++) {
      final prevEnd = sorted[i - 1].finishedAt ?? sorted[i - 1].createdAt;
      final currStart = sorted[i].startedAt ?? sorted[i].createdAt;
      final gap = currStart.difference(prevEnd);
      if (gap.inMinutes > 60) gaps.add(OmiDuration.compact(gap.inSeconds, context.l10n));
    }

    if (gaps.isEmpty) return null;
    return gaps;
  }

  /// Format the gap warning message using localization
  static String _formatGapWarning(BuildContext context, List<String> gaps) {
    if (gaps.length == 1) {
      return context.l10n.largeTimeGapDetected(gaps.first);
    }
    return context.l10n.largeTimeGapsDetected(gaps.join(', '));
  }

  static Future<bool> show(BuildContext context, List<ServerConversation> selectedConversations) async {
    if (selectedConversations.length < 2) return false;
    final l10n = context.l10n;

    // Check for large gaps and format warning message if any
    final gaps = _checkForLargeGaps(context, selectedConversations);
    final warning = gaps != null ? _formatGapWarning(context, gaps) : null;
    final message = l10n.mergeConversationsMessage(selectedConversations.length);

    return showOmiConfirm(
      context,
      title: l10n.mergeConversations,
      message: warning == null ? message : '$message\n\n$warning',
      confirmLabel: l10n.merge,
    );
  }
}
