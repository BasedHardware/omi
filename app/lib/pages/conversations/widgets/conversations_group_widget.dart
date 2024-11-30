import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/conversation.dart';

import 'date_list_item.dart';
import 'conversation_list_item.dart';

class ConversationsgroupWidget extends StatelessWidget {
  final List<ServerConversation> memories;
  final DateTime date;
  final bool showDiscardedMemories;
  final bool hasDiscardedMemories;
  final bool hasNonDiscardedMemories;
  final bool isFirst;
  const ConversationsgroupWidget(
      {super.key,
      required this.memories,
      required this.date,
      required this.hasNonDiscardedMemories,
      required this.showDiscardedMemories,
      required this.hasDiscardedMemories,
      required this.isFirst});

  @override
  Widget build(BuildContext context) {
    if (memories.isNotEmpty) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (!showDiscardedMemories && hasDiscardedMemories && !hasNonDiscardedMemories)
            const SizedBox.shrink()
          else
            DateListItem(date: date, isFirst: isFirst),
          ...memories.map((memory) {
            if (!showDiscardedMemories && memory.discarded) {
              return const SizedBox.shrink();
            }
            return ConversationListItem(memory: memory, memoryIdx: memories.indexOf(memory), date: date);
          }),
          if (!showDiscardedMemories && hasDiscardedMemories && !hasNonDiscardedMemories)
            const SizedBox.shrink()
          else
            const SizedBox(height: 16),
        ],
      );
    } else {
      return const SizedBox.shrink();
    }
  }
}
