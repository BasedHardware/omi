import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';

import 'date_list_item.dart';
import 'memory_list_item.dart';

class MemoriesGroupWidget extends StatelessWidget {
  final List<ServerMemory> memories;
  final DateTime date;
  const MemoriesGroupWidget({super.key, required this.memories, required this.date});

  @override
  Widget build(BuildContext context) {
    if (memories.isNotEmpty) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DateListItem(date: date, isFirst: true),
          ...memories.map((memory) {
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
