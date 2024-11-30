import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

import 'widgets/synced_memory_list_item.dart';

class SyncedConversationsPage extends StatelessWidget {
  const SyncedConversationsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synced Conversations'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: Consumer<ConversationProvider>(
        builder: (context, memoryProvider, child) {
          return SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ConversationsListWidget(
                  memories: memoryProvider.syncedConversationsPointers
                      .where((e) => e.type == SyncedConversationType.updatedConversation)
                      .toList(),
                  title: 'Updated Conversations',
                  showReprocess: true,
                ),
                ConversationsListWidget(
                  memories: memoryProvider.syncedConversationsPointers
                      .where((e) => e.type == SyncedConversationType.newConversation)
                      .toList(),
                  title: 'New Conversations',
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

class ConversationsListWidget extends StatelessWidget {
  final List<SyncedConversationPointer> memories;
  final String title;
  final bool showReprocess;
  const ConversationsListWidget({super.key, required this.memories, required this.title, required this.showReprocess});

  @override
  Widget build(BuildContext context) {
    if (memories.isEmpty) {
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
            var mem = memories[i];
            return SyncedMemoryListItem(
                memory: mem.memory, date: mem.key, memoryIdx: mem.index, showReprocess: showReprocess);
          },
          separatorBuilder: (ctx, i) {
            return const SizedBox(
              height: 10,
            );
          },
          itemCount: memories.length,
        ),
      ],
    );
  }
}
