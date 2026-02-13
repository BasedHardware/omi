import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopProcessingConversationWidget extends StatelessWidget {
  final ServerConversation? conversation;

  const DesktopProcessingConversationWidget({
    super.key,
    this.conversation,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.maxFinite,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          // Shimmer emoji placeholder (matches DesktopConversationCard 44x44 rounded square)
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.8),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Center(
              child: SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: ResponsiveHelper.textTertiary,
                ),
              ),
            ),
          ),
          const SizedBox(width: 14),
          // Title and subtitle placeholders
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  context.l10n.processing,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w500,
                    color: ResponsiveHelper.textTertiary,
                    height: 1.3,
                  ),
                ),
                const SizedBox(height: 6),
                // Shimmer bar for subtitle
                Container(
                  width: 80,
                  height: 10,
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(5),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Widget to display processing conversations in a list
Widget getDesktopProcessingConversationsWidget(List<ServerConversation> conversations) {
  if (conversations.isEmpty) {
    return const SizedBox.shrink();
  }

  // Show only the first (most recent) processing conversation
  return DesktopProcessingConversationWidget(conversation: conversations.first);
}
