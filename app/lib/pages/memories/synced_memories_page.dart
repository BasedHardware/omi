import 'package:flutter/material.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:provider/provider.dart';

import 'widgets/synced_memory_list_item.dart';

class SyncedMemoriesPage extends StatelessWidget {
  final Map<String, dynamic>? res;
  const SyncedMemoriesPage({super.key, this.res});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synced Memories'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: Consumer<MemoryProvider>(
        builder: (context, memoryProvider, child) {
          return SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                MemoriesListWidget(
                  memories: memoryProvider.syncedMemoriesPointers!['updated_memories'],
                  title: 'Updated Memories',
                  showReprocess: true,
                ),
                MemoriesListWidget(
                  memories: memoryProvider.syncedMemoriesPointers!['new_memories'],
                  title: 'New Memories',
                  showReprocess: false,
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class MemoriesListWidget extends StatelessWidget {
  final List<Record>? memories;
  final String title;
  final bool showReprocess;
  const MemoriesListWidget({super.key, required this.memories, required this.title, required this.showReprocess});

  @override
  Widget build(BuildContext context) {
    if (memories == null || memories!.isEmpty) {
      return const SizedBox();
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const SizedBox(
          height: 18,
        ),
        Text(
          title,
          style: const TextStyle(color: Colors.white, fontSize: 20),
        ),
        const SizedBox(
          height: 10,
        ),
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemBuilder: (ctx, i) {
            dynamic mem = memories![i];
            return SyncedMemoryListItem(memory: mem.$3, date: mem.$1, memoryIdx: mem.$2, showReprocess: showReprocess);
          },
          separatorBuilder: (ctx, i) {
            return const SizedBox(
              height: 10,
            );
          },
          itemCount: memories!.length,
        ),
      ],
    );
  }
}
