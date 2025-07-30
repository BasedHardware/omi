import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

import 'edit_action_item_sheet.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/backend/preferences.dart';

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
  static final Map<String, bool> _pendingStates = {}; // Track pending states by description

  @override
  void dispose() {
    // Clean up any pending state for this item when widget is disposed
    _pendingStates.remove(widget.actionItem.description);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<ConversationProvider>(context, listen: false);
    final conversation = provider.conversations.firstWhere(
      (c) => c.id == widget.conversationId,
      orElse: () => provider.searchedConversations.firstWhere((c) => c.id == widget.conversationId),
    );

    // Check if this specific item has a pending state change
    final isCompleted = _pendingStates.containsKey(widget.actionItem.description) ? _pendingStates[widget.actionItem.description]! : widget.actionItem.completed;

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
        color: const Color(0xFF1F1F25),
        borderRadius: borderRadius,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
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
            final prefsUtil = SharedPreferencesUtil();
            bool dontAskAgain = !(prefsUtil.showActionItemDeleteConfirmation);

            if (dontAskAgain) {
              context.read<ConversationProvider>().deleteActionItemAndUpdateLocally(
                    widget.conversationId,
                    widget.itemIndexInConversation,
                    widget.actionItem,
                  );
              return true;
            }

            // Delete action (swipe left) - show confirmation dialog
            return await showDialog<bool>(
                  context: context,
                  builder: (context) => ConfirmationDialog(
                    title: 'Delete Action Item',
                    description: 'Are you sure you want to delete this action item?',
                    checkboxText: "Don't ask again",
                    checkboxValue: dontAskAgain,
                    onCheckboxChanged: (value) {
                      prefsUtil.showActionItemDeleteConfirmation = !value;
                    },
                    confirmText: 'Delete',
                    cancelText: 'Cancel',
                    onConfirm: () {
                      context.read<ConversationProvider>().deleteActionItemAndUpdateLocally(
                            widget.conversationId,
                            widget.itemIndexInConversation,
                            widget.actionItem,
                          );
                      Navigator.pop(context, true);
                    },
                    onCancel: () => Navigator.pop(context, false),
                  ),
                ) ??
                false;
          } else if (direction == DismissDirection.startToEnd) {
            // Complete action (swipe right) - use same logic as tap
            _toggleCompletion(context, conversation);
            return false;
          }
          return false;
        },

        onDismissed: (direction) {},

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
                        onTap: () => _toggleCompletion(context, conversation),
                        child: AnimatedOpacity(
                          opacity: 1.0,
                          duration: const Duration(milliseconds: 300),
                          child: AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            height: 20,
                            width: 20,
                            decoration: BoxDecoration(
                              color: isCompleted ? Colors.green : Colors.transparent,
                              border: Border.all(
                                color: isCompleted ? Colors.green : Colors.grey[400]!,
                                width: 1.5,
                              ),
                              borderRadius: BorderRadius.circular(5),
                            ),
                            child: isCompleted
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
                                    color: isCompleted ? Colors.grey.shade500 : Colors.white,
                                    decoration: isCompleted ? TextDecoration.lineThrough : null,
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
                          if (widget.actionItem.description.toLowerCase().contains('february') || widget.actionItem.description.toLowerCase().contains('masterclass'))
                            Padding(
                              padding: const EdgeInsets.only(top: 8.0),
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                decoration: BoxDecoration(
                                  color: Color(0xFF35343B),
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

  void _toggleCompletion(BuildContext context, conversation) async {
    // Haptic feedback
    HapticFeedback.lightImpact();

    final newValue = !widget.actionItem.completed;
    final itemDescription = widget.actionItem.description;

    // Update pending state immediately for instant visual feedback
    setState(() {
      _pendingStates[itemDescription] = newValue;
    });

    try {
      // Update global state immediately
      await context.read<ConversationProvider>().updateGlobalActionItemState(
            conversation,
            itemDescription,
            newValue,
          );

      // Wait for 200ms before clearing pending state (allows user to see the change before item moves)
      Future.delayed(const Duration(milliseconds: 200), () {
        if (mounted) {
          setState(() {
            _pendingStates.remove(itemDescription); // Clear pending state so item moves to correct section
          });
        }
      });

      // Track analytics
      MixpanelManager().actionItemToggledCompletionOnActionItemsPage(
        conversationId: widget.conversationId,
        actionItemDescription: itemDescription,
        isCompleted: newValue,
      );
    } catch (e) {
      // If there's an error, revert pending state
      if (mounted) {
        setState(() {
          _pendingStates.remove(itemDescription);
        });
      }
      debugPrint('Error updating action item state: $e');
    }
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
