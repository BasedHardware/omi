import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';

import 'date_list_item.dart';
import 'memory_list_item.dart';

class MemoriesGroupWidget extends StatelessWidget {
  final List<ServerMemory> memories;
  final DateTime date;
  final bool showDiscardedMemories;
  final bool hasDiscardedMemories;
  const MemoriesGroupWidget(
      {super.key,
      required this.memories,
      required this.date,
      required this.showDiscardedMemories,
      required this.hasDiscardedMemories});

  @override
  Widget build(BuildContext context) {
    if (memories.isNotEmpty) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showDiscardedMemories && hasDiscardedMemories)
            DateListItem(date: date, isFirst: true)
          else if (!showDiscardedMemories)
            DateListItem(date: date, isFirst: true)
          else
            const SizedBox.shrink(),
          ...memories.map((memory) {
            if (!showDiscardedMemories && memory.discarded) {
              return const SizedBox.shrink();
            }
            return MemoryListItem(memory: memory, memoryIdx: memories.indexOf(memory), date: date);
          }),
          const SizedBox(height: 16),
        ],
      );
    } else {
      return const SizedBox.shrink();
    }
  }
}
