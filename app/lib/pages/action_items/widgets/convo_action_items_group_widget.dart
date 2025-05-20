import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';

import 'action_item_title_widget.dart';

class ConversationActionItemsGroupWidget extends StatelessWidget {
  final ServerConversation conversation;
  final List<ActionItem> actionItems;

  const ConversationActionItemsGroupWidget({
    super.key,
    required this.conversation,
    required this.actionItems,
  });

  @override
  Widget build(BuildContext context) {
    final sortedItems = [...actionItems]..sort((a, b) {
        if (a.completed == b.completed) return 0;
        return a.completed ? 1 : -1;
      });

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 6.0),
      decoration: BoxDecoration(
        color: Colors.grey[900],
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () {
              _navigateToConversationDetail(context);
            },
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          conversation.structured.title.isNotEmpty
                              ? conversation.structured.title
                              : 'Untitled Conversation',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${sortedItems.where((item) => !item.completed).length} remaining',
                          style: TextStyle(
                            color: Colors.grey[400],
                            fontSize: 14,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    Icons.chevron_right,
                    color: Colors.grey[400],
                  ),
                ],
              ),
            ),
          ),

          // Action Items List
          ...sortedItems.asMap().entries.map((entry) {
            final index = entry.key;
            final item = entry.value;
            final isLastItem = index == sortedItems.length - 1;

            return ActionItemTileWidget(
              actionItem: item,
              conversationId: conversation.id,
              itemIndexInConversation: conversation.structured.actionItems.indexOf(item),
              hasRoundedCorners: false,
              isLastInGroup: isLastItem,
              isInGroup: true,
            );
          }),
          const SizedBox(height: 8),
        ],
      ),
    );
  }

  void _navigateToConversationDetail(BuildContext context) async {
    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);

    DateTime? date;
    int? index;

    for (final entry in convoProvider.groupedConversations.entries) {
      final foundIndex = entry.value.indexWhere((c) => c.id == conversation.id);
      if (foundIndex != -1) {
        date = entry.key;
        index = foundIndex;
        break;
      }
    }

    if (date != null && index != null) {
      final detailProvider = Provider.of<ConversationDetailProvider>(context, listen: false);
      detailProvider.updateConversation(index, date);

      convoProvider.onConversationTap(index);

      await routeToPage(
        context,
        ConversationDetailPage(conversation: conversation),
      );
    }
  }
}
