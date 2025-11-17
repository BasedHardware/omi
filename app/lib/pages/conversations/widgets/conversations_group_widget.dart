import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';

import 'date_list_item.dart';
import 'conversation_list_item.dart';

class ConversationsGroupWidget extends StatelessWidget {
  final List<ServerConversation> conversations;
  final DateTime date;
  final bool isFirst;
  final bool isSelectionMode;
  final Set<String> selectedConversationIds;
  final Function(String) onLongPress;
  final Function(String) onSelectionToggle;

  const ConversationsGroupWidget({
    super.key,
    required this.conversations,
    required this.date,
    required this.isFirst,
    this.isSelectionMode = false,
    this.selectedConversationIds = const {},
    required this.onLongPress,
    required this.onSelectionToggle,
  });

  @override
  Widget build(BuildContext context) {
    if (conversations.isNotEmpty) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DateListItem(date: date, isFirst: isFirst),
          ...conversations.map((conversation) {
            return ConversationListItem(
              conversation: conversation,
              conversationIdx: conversations.indexOf(conversation),
              date: date,
              isSelectionMode: isSelectionMode,
              isSelected: selectedConversationIds.contains(conversation.id),
              onLongPress: () => onLongPress(conversation.id),
              onSelectionToggle: () => onSelectionToggle(conversation.id),
            );
          }),
          const SizedBox(height: 10),
        ],
      );
    } else {
      return const SizedBox.shrink();
    }
  }
}
