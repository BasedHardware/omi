import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The conversation list with nothing to show under the current filters.
class EmptyConversationsWidget extends StatelessWidget {
  final bool isStarredFilterActive;

  const EmptyConversationsWidget({super.key, this.isStarredFilterActive = false});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.only(top: 48),
      child: isStarredFilterActive
          ? OmiEmptyState(
              icon: Icons.star_outline_rounded,
              title: l10n.noStarredConversations,
              message: l10n.starConversationHint,
            )
          : OmiEmptyState(icon: Icons.forum_outlined, title: l10n.noConversationsYet),
    );
  }
}
