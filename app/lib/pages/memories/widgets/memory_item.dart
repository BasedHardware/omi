import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/pages/memories/page.dart';

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
      onTap: () => onTap(context, memory, provider),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingL, vertical: AppStyles.spacingL),
        decoration: BoxDecoration(
          color: AppStyles.backgroundSecondary,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.1),
              blurRadius: 4,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    memory.content.decodeString,
                    style: AppStyles.body,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
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
                _buildVisibilityButton(context),
              ],
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
        child: const Icon(
          Icons.chat_bubble_outline,
          size: 16,
          color: Colors.white70,
        ),
      ),
    );
  }

  Future<void> _navigateToConversation(BuildContext context) async {
    if (memory.conversationId == null) return;
    
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const Center(
        child: CircularProgressIndicator(),
      ),
    );

    final conversation = await getConversationById(memory.conversationId!);
    
    if (context.mounted) {
      Navigator.of(context).pop();
    }
    
    if (conversation != null && context.mounted) {
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => ChangeNotifierProxyProvider2<ConversationProvider, AppProvider, ConversationDetailProvider>(
            create: (context) {
              var provider = ConversationDetailProvider();
              provider.conversationIdx = 0;
              provider.selectedDate = DateTime(
                conversation.createdAt.year,
                conversation.createdAt.month,
                conversation.createdAt.day,
              );
              return provider;
            },
            update: (context, conversationProvider, appProvider, previous) {
              if (previous == null) {
                var provider = ConversationDetailProvider();
                provider.conversationIdx = 0;
                provider.selectedDate = DateTime(
                  conversation.createdAt.year,
                  conversation.createdAt.month,
                  conversation.createdAt.day,
                );
                provider.conversationProvider = conversationProvider;
                provider.appProvider = appProvider;
                final date = DateTime(
                  conversation.createdAt.year,
                  conversation.createdAt.month,
                  conversation.createdAt.day,
                );
                if (!conversationProvider.groupedConversations.containsKey(date)) {
                  conversationProvider.groupedConversations[date] = [];
                }
                if (!conversationProvider.groupedConversations[date]!.any((c) => c.id == conversation.id)) {
                  conversationProvider.groupedConversations[date]!.insert(0, conversation);
                }
                return provider;
              }
              previous.conversationProvider = conversationProvider;
              previous.appProvider = appProvider;
              return previous;
            },
            child: ConversationDetailPage(
               conversation: conversation,
             ),
           ),
         ),
       );
    } else if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Conversation not found or has been deleted'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Widget _buildVisibilityButton(BuildContext context) {
    return PopupMenuButton<MemoryVisibility>(
      padding: EdgeInsets.zero,
      position: PopupMenuPosition.under,
      surfaceTintColor: Colors.transparent,
      color: AppStyles.backgroundTertiary,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
      ),
      offset: const Offset(0, 4),
      child: Container(
        height: 36,
        width: 56,
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.1),
          borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              memory.visibility == MemoryVisibility.private ? Icons.lock_outline : Icons.public,
              size: 16,
              color: Colors.white70,
            ),
            const SizedBox(width: 6),
            const Icon(
              Icons.keyboard_arrow_down,
              size: 18,
              color: Colors.white70,
            ),
          ],
        ),
      ),
      itemBuilder: (context) => [
        _buildVisibilityItem(
          context,
          MemoryVisibility.private,
          Icons.lock_outline,
          'Will not be used for personas',
        ),
        _buildVisibilityItem(
          context,
          MemoryVisibility.public,
          Icons.public,
          'Will be used for personas',
        ),
      ],
      onSelected: (visibility) {
        provider.updateMemoryVisibility(memory, visibility);
        MixpanelManager().memoryVisibilityChanged(memory, visibility);
      },
    );
  }

  PopupMenuItem<MemoryVisibility> _buildVisibilityItem(
    BuildContext context,
    MemoryVisibility visibility,
    IconData icon,
    String description,
  ) {
    final isSelected = memory.visibility == visibility;
    return PopupMenuItem<MemoryVisibility>(
      value: visibility,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Icon(
              icon,
              size: 18,
              color: isSelected ? Colors.white : Colors.white70,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    visibility.name[0].toUpperCase() + visibility.name.substring(1),
                    style: TextStyle(
                      color: isSelected ? Colors.white : Colors.white70,
                      fontSize: 14,
                      fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                    ),
                  ),
                  Text(
                    description,
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 12,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            if (isSelected)
              const Icon(
                Icons.check,
                size: 18,
                color: Colors.white,
              ),
          ],
        ),
      ),
    );
  }
}
