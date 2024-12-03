import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/conversation.dart';

import 'date_list_item.dart';
import 'conversation_list_item.dart';

class ConversationsGroupWidget extends StatelessWidget {
  final List<ServerConversation> conversations;
  final DateTime date;
  final bool showDiscardedMemories;
  final bool hasDiscardedMemories;
  final bool hasNonDiscardedMemories;
  final bool isFirst;
  const ConversationsGroupWidget(
      {super.key,
      required this.conversations,
      required this.date,
      required this.hasNonDiscardedMemories,
      required this.showDiscardedMemories,
      required this.hasDiscardedMemories,
      required this.isFirst});

  @override
  Widget build(BuildContext context) {
    if (conversations.isNotEmpty) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (!showDiscardedMemories && hasDiscardedMemories && !hasNonDiscardedMemories)
            const SizedBox.shrink()
          else
            DateListItem(date: date, isFirst: isFirst),
          ...conversations.map((conversation) {
            if (!showDiscardedMemories && conversation.discarded) {
              return const SizedBox.shrink();
            }
            return ConversationListItem(
                conversation: conversation, memoryIdx: conversations.indexOf(conversation), date: date);
          }),
          if (!showDiscardedMemories && hasDiscardedMemories && !hasNonDiscardedMemories)
            const SizedBox.shrink()
          else
            const SizedBox(height: 10),
        ],
      );
    } else {
      return const SizedBox.shrink();
    }
  }
}
