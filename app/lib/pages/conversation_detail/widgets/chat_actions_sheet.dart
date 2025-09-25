import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/conversation_chat.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';

class ChatActionsBottomSheet extends StatelessWidget {
  const ChatActionsBottomSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.3,
      minChildSize: 0.2,
      maxChildSize: 0.5,
      expand: false,
      builder: (context, scrollController) {
        return Consumer<ConversationDetailProvider>(
          builder: (context, provider, _) {
            return _SheetContainer(
              scrollController: scrollController,
              children: [
                const _SheetHeader(),
                _ActionsList(provider: provider),
              ],
            );
          },
        );
      },
    );
  }
}

class _SheetContainer extends StatelessWidget {
  final ScrollController scrollController;
  final List<Widget> children;

  const _SheetContainer({
    required this.scrollController,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1F1F25),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(24),
          topRight: Radius.circular(24),
        ),
      ),
      child: Column(
        children: children,
      ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  const _SheetHeader();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.only(top: 16, bottom: 8),
      child: Column(
        children: [
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.grey[600],
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Chat Actions',
            style: Theme.of(context).textTheme.titleLarge!.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                ),
          ),
        ],
      ),
    );
  }
}

class _ActionsList extends StatelessWidget {
  final ConversationDetailProvider provider;

  const _ActionsList({required this.provider});

  void _showClearChatDialog(BuildContext context) {
    Navigator.pop(context); // Close bottom sheet first

    HapticFeedback.lightImpact();

    showDialog(
      context: context,
      builder: (dialogContext) {
        return getDialog(
          dialogContext,
          () {
            Navigator.of(dialogContext).pop(); // Cancel - use dialog context
          },
          () {
            // Close dialog first
            Navigator.of(dialogContext).pop();

            // Clear chat with haptic feedback (no context needed)
            HapticFeedback.mediumImpact();

            // Call API to clear chat
            clearConversationChat(provider.conversation.id).then((success) {
              if (success) {
                // Clear UI messages immediately after API success
                provider.clearChatMessages();
              }
            });
          },
          "Clear Chat?",
          "Are you sure you want to clear this conversation chat? This action cannot be undone.",
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 16),
      child: Column(
        children: [
          // Clear Chat Action
          _ActionItem(
            icon: FontAwesomeIcons.trashCan,
            title: 'Clear Chat',
            subtitle: 'Remove all messages from this conversation chat',
            iconColor: Colors.red[400]!,
            onTap: () => _showClearChatDialog(context),
          ),

          // Future actions can be added here
          // _ActionItem(
          //   icon: FontAwesomeIcons.download,
          //   title: 'Export Chat',
          //   subtitle: 'Download chat history as text file',
          //   iconColor: Colors.blue[400]!,
          //   onTap: () => _exportChat(context),
          // ),
        ],
      ),
    );
  }
}

class _ActionItem extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Color iconColor;
  final VoidCallback onTap;

  const _ActionItem({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.iconColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.grey[900],
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: iconColor.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                icon,
                color: iconColor,
                size: 16,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: TextStyle(
                      color: Colors.grey[400],
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              FontAwesomeIcons.chevronRight,
              color: Colors.grey[500],
              size: 12,
            ),
          ],
        ),
      ),
    );
  }
}
