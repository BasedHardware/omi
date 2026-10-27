import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The unfiltered Home empty state, shared by initial and typed empty results.
class NoConversationsHero extends StatelessWidget {
  const NoConversationsHero({super.key, this.message});

  /// Why the list is empty after a recording that did not become a conversation.
  final String? message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 120),
      child: OmiEmptyState(
        icon: Icons.forum_rounded,
        title: context.l10n.noConversationsYet,
        titleLayoutReference: context.l10n.noTasksYet,
        message: message,
        messageLayoutReference: message == null ? context.l10n.tasksEmptyStateMessage : null,
      ),
    );
  }
}

/// The conversation list with nothing to show under the current filters.
class EmptyConversationsWidget extends StatelessWidget {
  final bool isStarredFilterActive;
  final String? dateFilterLabel;

  const EmptyConversationsWidget({super.key, this.isStarredFilterActive = false, this.dateFilterLabel});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.only(top: 48),
      child: dateFilterLabel != null
          ? OmiEmptyState(icon: Icons.forum_rounded, title: l10n.noConversationsOnDate(dateFilterLabel!))
          : isStarredFilterActive
              ? OmiEmptyState(
                  glyph: const FaIcon(FontAwesomeIcons.star),
                  title: l10n.noStarredConversations,
                  message: l10n.starConversationHint,
                )
              : OmiEmptyState(icon: Icons.forum_rounded, title: l10n.noConversationsYet),
    );
  }
}
