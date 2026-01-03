import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/extensions/string.dart';

import 'delete_confirmation.dart';

class MemoryItem extends StatelessWidget {
  final Memory memory;
  final MemoriesProvider provider;
  final Function(BuildContext, Memory, MemoriesProvider) onTap;
  final bool showDismissible;

  const MemoryItem({
    super.key,
    required this.memory,
    required this.provider,
    required this.onTap,
    this.showDismissible = true,
  });

  @override
  Widget build(BuildContext context) {
    final Widget memoryWidget = GestureDetector(
      onTap: () {
        onTap(context, memory, provider);
      },
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.fromLTRB(18, 18, 16, 18),
        decoration: BoxDecoration(
          color: AppStyles.backgroundSecondary,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.1),
              blurRadius: 4,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Stack(
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        memory.content.decodeString,
                        style: AppStyles.body,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: AppStyles.spacingM),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (memory.conversationId != null) ...[
                      _buildConversationLinkButton(context),
                      const SizedBox(width: AppStyles.spacingS),
                    ],
                    // _buildVisibilityButton(context),
                  ],
                ),
              ],
            ),
            if (memory.isLocked)
              Positioned.fill(
                child: ClipRRect(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 2.0, sigmaY: 2.0),
                    child: GestureDetector(
                      onTap: () {
                        MixpanelManager().paywallOpened('Action Item');
                        routeToPage(
                          context,
                          const UsagePage(showUpgradeDialog: true),
                        );
                        return;
                      },
                      child: Container(
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.01),
                          borderRadius: const BorderRadius.all(
                            Radius.circular(8),
                          ),
                        ),
                        child: const Text(
                          'Upgrade to unlimited',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );

    if (!showDismissible) {
      return memoryWidget;
    }

    return Dismissible(
      key: Key(memory.id),
      direction: DismissDirection.endToStart,
      confirmDismiss: (direction) async {
        HapticFeedback.mediumImpact();
        final shouldDelete = await DeleteConfirmation.show(context);
        return shouldDelete;
      },
      onDismissed: (direction) {
        final memoryContent = memory.content.decodeString;

        provider.deleteMemory(memory);
        MixpanelManager().memoriesPageDeletedMemory(memory);

        if (context.findAncestorStateOfType<MemoriesPageState>() != null) {
          context.findAncestorStateOfType<MemoriesPageState>()!.showDeleteNotification(memoryContent, memory);
        }
      },
      background: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        decoration: BoxDecoration(
          color: AppStyles.error,
          borderRadius: BorderRadius.circular(16),
        ),
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        child: const Icon(Icons.delete_outline, color: Colors.white),
      ),
      child: memoryWidget,
    );
  }

  Widget _buildConversationLinkButton(BuildContext context) {
    return GestureDetector(
      onTap: () => _navigateToConversation(context),
      child: Container(
        height: 36,
        width: 36,
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.1),
          borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
        ),
        child: const Center(
          child: FaIcon(
            FontAwesomeIcons.message,
            size: 16,
            color: Colors.white70,
          ),
        ),
      ),
    );
  }

  DateTime _getConversationDate(DateTime createdAt) {
    return DateTime(createdAt.year, createdAt.month, createdAt.day);
  }

  void _ensureConversationInGroup(
    ConversationProvider conversationProvider,
    dynamic conversation,
  ) {
    final date = _getConversationDate(conversation.createdAt);
    conversationProvider.groupedConversations.putIfAbsent(date, () => []);

    final conversations = conversationProvider.groupedConversations[date]!;
    if (!conversations.any((c) => c.id == conversation.id)) {
      conversations.insert(0, conversation);
    }
  }

  Future<void> _navigateToConversation(BuildContext context) async {
    if (memory.conversationId == null) return;

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const Center(child: CircularProgressIndicator()),
    );

    final conversation = await getConversationById(memory.conversationId!);

    if (!context.mounted) return;
    Navigator.of(context).pop();

    if (conversation != null) {
      final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);
      final detailProvider = Provider.of<ConversationDetailProvider>(context, listen: false);

      _ensureConversationInGroup(conversationProvider, conversation);

      final conversationDate = _getConversationDate(conversation.createdAt);
      detailProvider.updateConversation(conversation.id, conversationDate);

      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => ConversationDetailPage(conversation: conversation),
        ),
      );
    } else {
      _showConversationNotFoundError(context);
    }
  }

  void _showConversationNotFoundError(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Conversation not found or has been deleted'),
        backgroundColor: Colors.red,
      ),
    );
  }

  // Widget _buildVisibilityButton(BuildContext context) {
  //   return PopupMenuButton<MemoryVisibility>(
  //     padding: EdgeInsets.zero,
  //     position: PopupMenuPosition.under,
  //     surfaceTintColor: Colors.transparent,
  //     color: AppStyles.backgroundTertiary,
  //     shape: RoundedRectangleBorder(
  //       borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
  //     ),
  //     offset: const Offset(0, 4),
  //     child: Container(
  //       height: 36,
  //       width: 56,
  //       decoration: BoxDecoration(
  //         color: Colors.white.withValues(alpha: 0.1),
  //         borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
  //       ),
  //       child: Row(
  //         mainAxisSize: MainAxisSize.min,
  //         mainAxisAlignment: MainAxisAlignment.center,
  //         children: [
  //           Icon(
  //             memory.visibility == MemoryVisibility.private ? Icons.lock_outline : Icons.public,
  //             size: 16,
  //             color: Colors.white70,
  //           ),
  //           const SizedBox(width: 6),
  //           const Icon(
  //             Icons.keyboard_arrow_down,
  //             size: 18,
  //             color: Colors.white70,
  //           ),
  //         ],
  //       ),
  //     ),
  //     itemBuilder: (context) => [
  //       _buildVisibilityItem(
  //         context,
  //         MemoryVisibility.private,
  //         Icons.lock_outline,
  //         'Will not be used for personas',
  //       ),
  //       _buildVisibilityItem(
  //         context,
  //         MemoryVisibility.public,
  //         Icons.public,
  //         'Will be used for personas',
  //       ),
  //     ],
  //     onSelected: (visibility) {
  //       provider.updateMemoryVisibility(memory, visibility);
  //       MixpanelManager().memoryVisibilityChanged(memory, visibility);
  //     },
  //   );
  // }

  // PopupMenuItem<MemoryVisibility> _buildVisibilityItem(
  //   BuildContext context,
  //   MemoryVisibility visibility,
  //   IconData icon,
  //   String description,
  // ) {
  //   final isSelected = memory.visibility == visibility;
  //   return PopupMenuItem<MemoryVisibility>(
  //     value: visibility,
  //     child: Container(
  //       padding: const EdgeInsets.symmetric(vertical: 4),
  //       child: Row(
  //         children: [
  //           Icon(
  //             icon,
  //             size: 18,
  //             color: isSelected ? Colors.white : Colors.white70,
  //           ),
  //           const SizedBox(width: 12),
  //           Expanded(
  //             child: Column(
  //               crossAxisAlignment: CrossAxisAlignment.start,
  //               children: [
  //                 Text(
  //                   visibility.name[0].toUpperCase() + visibility.name.substring(1),
  //                   style: TextStyle(
  //                     color: isSelected ? Colors.white : Colors.white70,
  //                     fontSize: 14,
  //                     fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
  //                   ),
  //                 ),
  //                 Text(
  //                   description,
  //                   style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
  //                   maxLines: 2,
  //                   overflow: TextOverflow.ellipsis,
  //                 ),
  //               ],
  //             ),
  //           ),
  //           if (isSelected) const Icon(Icons.check, size: 18, color: Colors.white),
  //         ],
  //       ),
  //     ),
  //   );
  // }
}
