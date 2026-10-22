import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Whether Home folds [conversation] into its day's "Also: …" line instead of giving it a row
/// (Episodes M3, David 2026-10-22): the notes pass called it background, and nothing the person
/// did to it (a star, a lock, unfinished processing) asks for a row of its own.
bool foldsIntoBackgroundLine(ServerConversation conversation) =>
    conversation.structured.isBackground &&
    conversation.status == ConversationStatus.completed &&
    !conversation.starred &&
    !conversation.isLocked &&
    !conversation.discarded;

/// The items of a day's background line: each title with its length, the first [shown], then "+N".
String backgroundLineItems(List<ServerConversation> background, String Function(int seconds) length, {int shown = 3}) {
  final items = <String>[
    for (final conversation in background.take(shown))
      [
        conversation.structured.title.trim(),
        if (conversation.getDurationInSeconds() >= 60) length(conversation.getDurationInSeconds()),
      ].where((part) => part.isNotEmpty).join(' '),
  ]..removeWhere((item) => item.isEmpty);
  final more = background.length - shown;
  if (more > 0) items.add('+$more');
  return items.join(' · ');
}

/// One line under a day header that stands for the day's background conversations; tapping it
/// shows them as rows (and tapping again folds them back).
class BackgroundDayLine extends StatelessWidget {
  final List<ServerConversation> background;
  final bool expanded;
  final VoidCallback onTap;

  const BackgroundDayLine({super.key, required this.background, required this.expanded, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // Whole minutes, as the rows round theirs.
    final text =
        l10n.homeBackgroundLine(backgroundLineItems(background, (s) => OmiDuration.compact((s ~/ 60) * 60, l10n)));
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 16, 0),
      child: Semantics(
        button: true,
        expanded: expanded,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(OmiRadius.sm),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    text,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                  ),
                ),
                Icon(expanded ? Icons.expand_less : Icons.chevron_right, size: 18, color: OmiColors.textTertiary),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
