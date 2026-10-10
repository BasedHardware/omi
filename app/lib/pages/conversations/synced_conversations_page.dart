import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/ui/ui.dart';
import 'widgets/synced_conversation_list_item.dart';

class SyncedConversationsPage extends StatelessWidget {
  const SyncedConversationsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return OmiGroupedPage(
      title: context.l10n.processedConversations,
      body: Consumer<SyncProvider>(
        builder: (context, syncProvider, child) {
          return SingleChildScrollView(
            padding: OmiGroupedPage.padding,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ConversationsListWidget(
                  conversations: syncProvider.syncedConversationsPointers
                      .where((e) => e.type == SyncedConversationType.updatedConversation)
                      .toList(),
                  title: context.l10n.updatedConversations,
                  showReprocess: true,
                ),
                ConversationsListWidget(
                  conversations: syncProvider.syncedConversationsPointers
                      .where((e) => e.type == SyncedConversationType.newConversation)
                      .toList(),
                  title: context.l10n.newConversations,
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
  const ConversationsListWidget({
    super.key,
    required this.conversations,
    required this.title,
    required this.showReprocess,
  });

  @override
  Widget build(BuildContext context) {
    if (conversations.isEmpty) {
      return const SizedBox();
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSectionHeader(title),
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemBuilder: (ctx, i) {
            var convo = conversations[i];
            return SyncedConversationListItem(
              conversation: convo.conversation,
              date: convo.key,
              conversationIdx: convo.index,
              showReprocess: showReprocess,
            );
          },
          separatorBuilder: (ctx, i) {
            return const SizedBox(height: OmiSpacing.xs);
          },
          itemCount: conversations.length,
        ),
        const SizedBox(height: OmiSpacing.xl),
      ],
    );
  }
}
