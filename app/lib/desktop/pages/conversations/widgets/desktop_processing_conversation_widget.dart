import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopProcessingConversationWidget extends StatelessWidget {
  final ServerConversation conversation;

  const DesktopProcessingConversationWidget({
    super.key,
    required this.conversation,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
          width: 1,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header row
          Row(
            children: [
              // Icon circle
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundQuaternary,
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              const SizedBox(width: 12),
              // Processing label
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF35343B),
                  borderRadius: BorderRadius.circular(20),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                child: Text(
                  context.l10n.processing,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
              const Spacer(),
              // Timestamp placeholder
              Container(
                width: 60,
                height: 14,
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundQuaternary,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          // Title placeholder bar
          Container(
            width: double.maxFinite,
            height: 12,
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundQuaternary,
              borderRadius: BorderRadius.circular(6),
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
