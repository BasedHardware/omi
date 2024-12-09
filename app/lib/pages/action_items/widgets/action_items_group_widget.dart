import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/conversations.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:friend_private/pages/conversation_detail/page.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

class ActionItemsGroupWidget extends StatefulWidget {
  final List<ServerConversation> conversations;
  final DateTime date;
  const ActionItemsGroupWidget({
    super.key,
    required this.conversations,
    required this.date,
  });

  @override
  State<ActionItemsGroupWidget> createState() => _ActionItemsGroupWidgetState();
}

class _ActionItemsGroupWidgetState extends State<ActionItemsGroupWidget> {
  @override
  Widget build(BuildContext context) {
    if (widget.conversations.isNotEmpty) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: widget.conversations.map((conversation) {
          if (conversation.structured.actionItems.isEmpty) {
            return const SizedBox.shrink();
          }
          return InkWell(
            onTap: () async {
              var convoIdx = widget.conversations.indexOf(conversation);
              // MixpanelManager().memoryListItemClicked(conversation, convoIdx);
              context.read<ConversationDetailProvider>().updateConversation(convoIdx, widget.date);
              context.read<ConversationProvider>().onConversationTap(convoIdx);
              await routeToPage(
                context,
                ConversationDetailPage(conversation: conversation, isFromOnboarding: false),
              );
            },
            child: Container(
              width: double.maxFinite,
              padding: const EdgeInsets.only(left: 16.0, right: 16.0, top: 20.0),
              margin: const EdgeInsets.only(left: 2.0, right: 2.0, bottom: 16.0),
              decoration: BoxDecoration(
                color: Colors.grey.shade900,
                borderRadius: BorderRadius.circular(16.0),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SizedBox(
                            width: MediaQuery.of(context).size.width * 0.8,
                            child: Text(
                              conversation.structured.title,
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                          ),
                          const SizedBox(
                            height: 6,
                          ),
                          Text(
                            dateTimeFormat('MMM d, h:mm a', conversation.startedAt ?? conversation.createdAt),
                            style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                          ),
                          const SizedBox(
                            height: 6,
                          ),
                        ],
                      ),
                      const Spacer(),
                      const Icon(
                        Icons.arrow_forward,
                        size: 20,
                      ),
                      const SizedBox(
                        width: 6,
                      ),
                    ],
                  ),
                  Consumer<ConversationProvider>(builder: (context, convoProvider, child) {
                    return ListView.builder(
                      itemCount: conversation.structured.actionItems.where((e) => !e.deleted).length,
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemBuilder: (context, idx) {
                        var item = conversation.structured.actionItems.where((e) => !e.deleted).toList()[idx];
                        return Dismissible(
                          key: Key(item.description),
                          direction: DismissDirection.endToStart,
                          background: Container(
                            alignment: Alignment.centerRight,
                            padding: const EdgeInsets.only(right: 20.0),
                            color: Colors.red,
                            child: const Icon(Icons.delete, color: Colors.white),
                          ),
                          onDismissed: (direction) {
                            // var tempItem = provider.memory.structured.actionItems[idx];
                            var tempIdx = idx;
                            // provider.deleteActionItem(idx);
                            ScaffoldMessenger.of(context)
                                .showSnackBar(
                                  SnackBar(
                                    content: const Text('Action Item deleted successfully 🗑️'),
                                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                                    action: SnackBarAction(
                                      label: 'Undo',
                                      textColor: Colors.white,
                                      onPressed: () {
                                        // provider.undoDeleteActionItem(idx);
                                      },
                                    ),
                                  ),
                                )
                                .closed
                                .then((reason) {
                              if (reason != SnackBarClosedReason.action) {
                                // provider.deleteActionItemPermanently(tempItem, tempIdx);
                                // MixpanelManager().deletedActionItem(provider.memory);
                              }
                            });
                          },
                          child: Padding(
                            padding: const EdgeInsets.only(top: 10, bottom: 2),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                Padding(
                                  padding: const EdgeInsets.only(top: 6.0),
                                  child: SizedBox(
                                    height: 22.0,
                                    width: 22.0,
                                    child: Checkbox(
                                      shape: const CircleBorder(),
                                      value: item.completed,
                                      onChanged: (value) {
                                        if (value != null) {
                                          if (value != item.completed) {
                                            setState(() {
                                              item.completed = value;
                                            });
                                            convoProvider.updateActionItemState(
                                                conversation.id, value, idx, widget.date);
                                            setConversationActionItemState(conversation.id, [idx], [value]);
                                          }
                                          if (value) {
                                            MixpanelManager().checkedActionItem(conversation, idx);
                                          } else {
                                            MixpanelManager().uncheckedActionItem(conversation, idx);
                                          }
                                        }
                                      },
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: SelectionArea(
                                    child: Padding(
                                      padding: const EdgeInsets.only(top: 6.0),
                                      child: Text(
                                        item.description.decodeString,
                                        style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    );
                  }),
                ],
              ),
            ),
          );
        }).toList(),
      );
    } else {
      return const SizedBox.shrink();
    }
  }
}
