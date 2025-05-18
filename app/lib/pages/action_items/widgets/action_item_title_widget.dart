import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

import 'edit_action_item_sheet.dart';

class ActionItemTileWidget extends StatefulWidget {
  final ActionItem actionItem;
  final String conversationId;
  final int itemIndexInConversation;
  final bool hasRoundedCorners;
  final bool isLastInGroup;
  final bool isInGroup;

  const ActionItemTileWidget({
    super.key,
    required this.actionItem,
    required this.conversationId,
    required this.itemIndexInConversation,
    this.hasRoundedCorners = true,
    this.isLastInGroup = false,
    this.isInGroup = false,
  });

  @override
  State<ActionItemTileWidget> createState() => _ActionItemTileWidgetState();
}

class _ActionItemTileWidgetState extends State<ActionItemTileWidget> {
  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<ConversationProvider>(context, listen: false);
    final conversation = provider.conversations.firstWhere(
      (c) => c.id == widget.conversationId,
      orElse: () => provider.searchedConversations.firstWhere((c) => c.id == widget.conversationId),
    );

    BorderRadius borderRadius;
    if (widget.hasRoundedCorners) {
      borderRadius = BorderRadius.circular(16);
    } else if (widget.isLastInGroup) {
      borderRadius = const BorderRadius.only(
        bottomLeft: Radius.circular(16),
        bottomRight: Radius.circular(16),
      );
    } else {
      borderRadius = BorderRadius.zero;
    }

    return Container(
      decoration: BoxDecoration(
        color: Colors.grey[900],
        borderRadius: borderRadius,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      // ClipRRect to enforce rounded corners throughout the dismissible animation
      clipBehavior: Clip.antiAlias,
      child: Dismissible(
        key: Key("${widget.conversationId}_${widget.itemIndexInConversation}"),
        // Allow horizontal swipe in both directions
        direction: DismissDirection.horizontal,

        // Background for complete action (swipe right, startToEnd)
        background: Container(
          alignment: Alignment.centerLeft,
          color: Colors.green,
          child: const Padding(
            padding: EdgeInsets.only(left: 20),
            child: Row(
              children: [
                Icon(
                  Icons.check_circle,
                  color: Colors.white,
                  size: 30,
                ),
              ],
            ),
          ),
        ),

        // Background for delete action (swipe left, endToStart)
        secondaryBackground: Container(
          alignment: Alignment.centerRight,
          color: Colors.red,
          child: const Padding(
            padding: EdgeInsets.only(right: 20),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Icon(
                  Icons.delete,
                  color: Colors.white,
                  size: 30,
                ),
              ],
            ),
          ),
        ),

        confirmDismiss: (direction) async {
          if (direction == DismissDirection.endToStart) {
            // Delete action (swipe left) - show confirmation dialog
            return await showDialog(
              context: context,
              builder: (context) => AlertDialog(
                backgroundColor: Colors.grey.shade900,
                title: const Text(
                  'Delete Action Item',
                  style: TextStyle(color: Colors.white),
                ),
                content: Text(
                  'Are you sure you want to delete this action item?',
                  style: TextStyle(color: Colors.grey.shade300),
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: Text(
                      'Cancel',
                      style: TextStyle(color: Colors.grey.shade400),
                    ),
                  ),
                  TextButton(
                    onPressed: () => Navigator.pop(context, true),
                    child: const Text(
                      'Delete',
                      style: TextStyle(color: Colors.red),
                    ),
                  ),
                ],
              ),
            );
          } else if (direction == DismissDirection.startToEnd) {
            // Complete action (swipe right) - toggle completed state
            final newValue = !widget.actionItem.completed;
            context.read<ConversationProvider>().updateGlobalActionItemState(
                  conversation,
                  widget.itemIndexInConversation,
                  newValue,
                );
            return false;
          }
          return false;
        },

        onDismissed: (direction) {
          // if (direction == DismissDirection.endToStart) {
          //   ScaffoldMessenger.of(context).showSnackBar(
          //     SnackBar(
          //       content: const Text('Action item deleted'),
          //       action: SnackBarAction(
          //         label: 'Undo',
          //         onPressed: () {},
          //       ),
          //     ),
          //   );
          // }
        },

        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {
              HapticFeedback.lightImpact();
              MixpanelManager().actionItemTappedForEditOnActionItemsPage(
                conversationId: widget.conversationId,
                actionItemDescription: widget.actionItem.description,
              );
              _showEditActionItemBottomSheet(context, widget.actionItem);
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 16.0, horizontal: 16.0),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 20,
                    height: 20,
                    child: Transform.translate(
                      offset: const Offset(0, 2),
                      child: GestureDetector(
                        onTap: () {
                          HapticFeedback.lightImpact();
                          final newValue = !widget.actionItem.completed;
                          MixpanelManager().actionItemToggledCompletionOnActionItemsPage(
                            conversationId: widget.conversationId,
                            actionItemDescription: widget.actionItem.description,
                            isCompleted: newValue,
                          );
                          context.read<ConversationProvider>().updateGlobalActionItemState(
                                conversation,
                                widget.itemIndexInConversation,
                                newValue,
                              );
                        },
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 200),
                          height: 20,
                          width: 20,
                          decoration: BoxDecoration(
                            color: widget.actionItem.completed ? Colors.deepPurpleAccent : Colors.transparent,
                            border: Border.all(
                              color: widget.actionItem.completed ? Colors.deepPurpleAccent : Colors.grey[400]!,
                              width: 1.5,
                            ),
                            borderRadius: BorderRadius.circular(5),
                          ),
                          child: widget.actionItem.completed
                              ? const Icon(
                                  Icons.check,
                                  size: 14,
                                  color: Colors.white,
                                )
                              : null,
                        ),
                      ),
                    ),
                  ),

                  // Content
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.only(left: 14.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  widget.actionItem.description,
                                  style: TextStyle(
                                    color: widget.actionItem.completed ? Colors.grey.shade500 : Colors.white,
                                    decoration: widget.actionItem.completed ? TextDecoration.lineThrough : null,
                                    decorationColor: Colors.grey.shade600,
                                    fontSize: 16,
                                    height: 1.3,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ),
                            ],
                          ),

                          // Optional date/time for tasks
                          if (widget.actionItem.description.toLowerCase().contains('february') ||
                              widget.actionItem.description.toLowerCase().contains('masterclass'))
                            Padding(
                              padding: const EdgeInsets.only(top: 8.0),
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                decoration: BoxDecoration(
                                  color: Colors.grey.shade800,
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(
                                      Icons.notifications_outlined,
                                      size: 14,
                                      color: Colors.grey.shade400,
                                    ),
                                    const SizedBox(width: 6),
                                    Text(
                                      'February 28 - 11:00am',
                                      style: TextStyle(
                                        color: Colors.grey.shade400,
                                        fontSize: 13,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _showEditActionItemBottomSheet(BuildContext context, ActionItem item) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) {
        return EditActionItemBottomSheet(
          actionItem: item,
          conversationId: widget.conversationId,
          itemIndex: widget.itemIndexInConversation,
        );
      },
    );
  }
}
