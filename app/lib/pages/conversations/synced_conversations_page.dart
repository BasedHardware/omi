import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

import 'widgets/synced_conversation_list_item.dart';

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
        builder: (context, convoProvider, child) {
          return SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ConversationsListWidget(
                  conversations: convoProvider.syncedConversationsPointers
                      .where((e) => e.type == SyncedConversationType.updatedConversation)
                      .toList(),
                  title: 'Updated Conversations',
                  showReprocess: true,
                ),
                ConversationsListWidget(
                  conversations: convoProvider.syncedConversationsPointers
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
  final List<SyncedConversationPointer> conversations;
  final String title;
  final bool showReprocess;
  const ConversationsListWidget(
      {super.key, required this.conversations, required this.title, required this.showReprocess});

  @override
  Widget build(BuildContext context) {
    if (conversations.isEmpty) {
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
            var convo = conversations[i];
            return SyncedConversationListItem(
                conversation: convo.conversation,
                date: convo.key,
                conversationIdx: convo.index,
                showReprocess: showReprocess);
          },
          separatorBuilder: (ctx, i) {
            return const SizedBox(
              height: 10,
            );
          },
          itemCount: conversations.length,
        ),
      ],
    );
  }
}
