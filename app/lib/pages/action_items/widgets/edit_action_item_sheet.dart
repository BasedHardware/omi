import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

class EditActionItemBottomSheet extends StatefulWidget {
  final ActionItem actionItem;
  final String conversationId;
  final int itemIndex;

  const EditActionItemBottomSheet({
    super.key,
    required this.actionItem,
    required this.conversationId,
    required this.itemIndex,
  });

  @override
  State<EditActionItemBottomSheet> createState() => _EditActionItemBottomSheetState();
}

class _EditActionItemBottomSheetState extends State<EditActionItemBottomSheet> {
  late TextEditingController _textController;
  late bool _isCompleted;

  @override
  void initState() {
    super.initState();
    _textController = TextEditingController(text: widget.actionItem.description);
    _textController.selection = TextSelection.fromPosition(
      TextPosition(offset: _textController.text.length),
    );
    _isCompleted = widget.actionItem.completed;
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  void _saveActionItem() async {
    if (_textController.text.trim().isEmpty) {
      // Optionally, show a message that description can't be empty
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Action item description cannot be empty.'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    String oldDescription = widget.actionItem.description;
    String newDescription = _textController.text.trim();

    updateActionItemDescription(widget.conversationId, oldDescription, newDescription, widget.itemIndex);

    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);
    convoProvider.updateActionItemDescriptionInConversation(
      widget.conversationId,
      widget.itemIndex, // This should be the index of the item in the conversation's list
      newDescription,
    );

    if (mounted) {
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                // Completed status toggle
                Row(
                  children: [
                    SizedBox(
                      height: 24,
                      width: 24,
                      child: Checkbox(
                        value: _isCompleted,
                        activeColor: Colors.deepPurpleAccent,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(5),
                        ),
                        onChanged: (bool? value) {
                          HapticFeedback.lightImpact();
                          if (value == null) return;

                          final convoProvider = Provider.of<ConversationProvider>(context, listen: false);
                          ServerConversation? conversation = convoProvider.conversations.firstWhere(
                            (c) => c.id == widget.conversationId,
                            orElse: () => throw Exception('Conversation not found for ID: ${widget.conversationId}'),
                          );

                          convoProvider.updateGlobalActionItemState(
                            conversation,
                            widget.itemIndex,
                            value,
                          );

                          setState(() {
                            _isCompleted = value;
                          });
                        },
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      _isCompleted ? 'Completed' : 'Mark complete',
                      style: TextStyle(
                        color: Colors.grey.shade300,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
                // Delete button
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: Colors.red),
                  onPressed: () {
                    // Show delete confirmation dialog
                    showDialog(
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
                            onPressed: () {
                              Navigator.pop(context, true); // Close dialog
                              Navigator.pop(context); // Close bottom sheet

                              // Show confirmation
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Action item deleted'),
                                  duration: Duration(seconds: 2),
                                ),
                              );
                            },
                            child: const Text(
                              'Delete',
                              style: TextStyle(color: Colors.red),
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ],
            ),
            const SizedBox(height: 12),
            // Text field for editing the action item
            TextField(
              controller: _textController,
              autofocus: true,
              maxLines: null,
              textInputAction: TextInputAction.done,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                height: 1.4,
              ),
              decoration: const InputDecoration(
                border: InputBorder.none,
                contentPadding: EdgeInsets.zero,
                isDense: true,
              ),
              onSubmitted: (value) {
                if (value.trim().isNotEmpty) {
                  _saveActionItem();
                }
              },
            ),
            const SizedBox(height: 18),
            // Bottom row with helper text and character count
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.05),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.keyboard_return,
                        size: 13,
                        color: Colors.grey.shade400,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        'Press done to save',
                        style: TextStyle(
                          color: Colors.grey.shade400,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                ),
                Text(
                  '${_textController.text.length}/200',
                  style: TextStyle(
                    color: Colors.grey.shade500,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
