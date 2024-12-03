import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/pages/action_items/widgets/action_items_group_widget.dart';
import 'package:friend_private/pages/conversations/widgets/empty_conversations.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

class ActionItemsPage extends StatelessWidget {
  const ActionItemsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Action Items'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      body: Consumer<ConversationProvider>(
        builder: (context, convoProvider, child) {
          return CustomScrollView(
            slivers: [
              const SliverToBoxAdapter(
                child: SizedBox(height: 12),
              ),
              if (convoProvider.groupedConversations.isEmpty && !convoProvider.isLoadingConversations)
                const SliverToBoxAdapter(
                  child: Center(
                    child: Padding(
                      padding: EdgeInsets.only(top: 32.0),
                      child: EmptyConversationsWidget(),
                    ),
                  ),
                )
              else if (convoProvider.groupedConversations.isEmpty && convoProvider.isLoadingConversations)
                const SliverToBoxAdapter(
                  child: Center(
                    child: Padding(
                      padding: EdgeInsets.only(top: 32.0),
                      child: CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                    ),
                  ),
                )
              else
                SliverList(
                  delegate: SliverChildBuilderDelegate(
                    childCount: convoProvider.groupedConversations.length + 1,
                    (context, index) {
                      if (index == convoProvider.groupedConversations.length) {
                        if (convoProvider.isLoadingConversations) {
                          return const Center(
                            child: Padding(
                              padding: EdgeInsets.only(top: 18.0, bottom: 32.0),
                              child: CircularProgressIndicator(
                                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                              ),
                            ),
                          );
                        }
                        return VisibilityDetector(
                          key: const Key('action-items-key'),
                          onVisibilityChanged: (visibilityInfo) {
                            if (visibilityInfo.visibleFraction > 0 && !convoProvider.isLoadingConversations) {
                              if (convoProvider.queryAlreadyFetched) {
                                return;
                              } else {
                                convoProvider.getMoreConversationsFromServer();
                              }
                            }
                          },
                          child: const SizedBox(height: 20, width: double.maxFinite),
                        );
                      } else {
                        var date = convoProvider.groupedConversations.keys.elementAt(index);
                        List<ServerConversation> convosForDate = convoProvider.groupedConversations[date]!;

                        return Padding(
                          padding: const EdgeInsets.only(left: 4, right: 4),
                          child: ActionItemsGroupWidget(
                            conversations: convosForDate,
                            date: date,
                          ),
                        );
                      }
                    },
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
