import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

class DesktopEditActionSheet extends StatefulWidget {
  final ActionItem actionItem;
  final ServerConversation conversation;
  final int itemIndex;

  const DesktopEditActionSheet({
    super.key,
    required this.actionItem,
    required this.conversation,
    required this.itemIndex,
  });

  @override
  State<DesktopEditActionSheet> createState() => _DesktopEditActionSheetState();
}

class _DesktopEditActionSheetState extends State<DesktopEditActionSheet> {
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
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Action item description cannot be empty.'),
          backgroundColor: Colors.red.shade400,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          duration: const Duration(seconds: 2),
        ),
      );
      return;
    }

    String oldDescription = widget.actionItem.description;
    String newDescription = _textController.text.trim();

    updateActionItemDescription(widget.conversation.id, oldDescription, newDescription, widget.itemIndex);

    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);
    convoProvider.updateActionItemDescriptionInConversation(
      widget.conversation.id,
      widget.itemIndex,
      newDescription,
    );

    if (mounted) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Action item updated'),
          backgroundColor: ResponsiveHelper.backgroundTertiary,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 480,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.2),
              blurRadius: 30,
              offset: const Offset(0, 15),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(
              children: [
                Icon(
                  FontAwesomeIcons.pen,
                  color: ResponsiveHelper.textSecondary,
                  size: 18,
                ),
                const SizedBox(width: 12),
                Text(
                  'Edit Action Item',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const Spacer(),
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: Icon(
                    FontAwesomeIcons.xmark,
                    color: ResponsiveHelper.textSecondary,
                    size: 16,
                  ),
                ),
              ],
            ),

            const SizedBox(height: 8),

            // Conversation context
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Icon(
                    FontAwesomeIcons.message,
                    color: ResponsiveHelper.textTertiary,
                    size: 12,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      widget.conversation.structured.title.isNotEmpty ? widget.conversation.structured.title : 'Untitled Conversation',
                      style: TextStyle(
                        color: ResponsiveHelper.textTertiary,
                        fontSize: 12,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 20),

            // Completion status toggle
            Row(
              children: [
                GestureDetector(
                  onTap: () {
                    HapticFeedback.lightImpact();
                    final newValue = !_isCompleted;

                    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);
                    convoProvider.updateGlobalActionItemState(
                      widget.conversation,
                      widget.itemIndex,
                      newValue,
                    );

                    setState(() {
                      _isCompleted = newValue;
                    });
                  },
                  child: Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      color: _isCompleted ? ResponsiveHelper.purplePrimary : Colors.transparent,
                      border: Border.all(
                        color: _isCompleted ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                        width: 1.5,
                      ),
                      borderRadius: BorderRadius.circular(5),
                    ),
                    child: _isCompleted
                        ? Icon(
                            FontAwesomeIcons.check,
                            size: 12,
                            color: Colors.white,
                          )
                        : null,
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  _isCompleted ? 'Completed' : 'Mark as complete',
                  style: TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),

            const SizedBox(height: 20),

            // Text input
            Container(
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                  width: 1,
                ),
              ),
              child: TextField(
                controller: _textController,
                autofocus: true,
                maxLines: 4,
                maxLength: 200,
                textInputAction: TextInputAction.done,
                style: TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 15,
                  height: 1.4,
                ),
                decoration: InputDecoration(
                  hintText: 'Describe the action item...',
                  hintStyle: TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 15,
                  ),
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.all(16),
                  counterStyle: TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 12,
                  ),
                ),
                onSubmitted: (value) {
                  if (value.trim().isNotEmpty) {
                    _saveActionItem();
                  }
                },
              ),
            ),

            const SizedBox(height: 24),

            // Actions
            Row(
              children: [
                // Delete button
                TextButton.icon(
                  onPressed: _showDeleteConfirmation,
                  icon: Icon(
                    FontAwesomeIcons.trash,
                    color: Colors.red.shade400,
                    size: 16,
                  ),
                  label: Text(
                    'Delete',
                    style: TextStyle(
                      color: Colors.red.shade400,
                      fontSize: 14,
                    ),
                  ),
                ),
                const Spacer(),
                // Cancel button
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: Text(
                    'Cancel',
                    style: TextStyle(
                      color: ResponsiveHelper.textSecondary,
                      fontSize: 14,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                // Save button
                Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: _saveActionItem,
                    borderRadius: BorderRadius.circular(12),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.purplePrimary,
                        borderRadius: BorderRadius.circular(12),
                        boxShadow: [
                          BoxShadow(
                            color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                            blurRadius: 8,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: Text(
                        'Save Changes',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _showDeleteConfirmation() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: ResponsiveHelper.backgroundSecondary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
        title: Text(
          'Delete Action Item',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        content: Text(
          'Are you sure you want to delete this action item?',
          style: TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 14,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(
              'Cancel',
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
              ),
            ),
          ),
          TextButton(
            onPressed: () {
              context.read<ConversationProvider>().deleteActionItemAndUpdateLocally(
                    widget.conversation.id,
                    widget.itemIndex,
                    widget.actionItem,
                  );
              Navigator.pop(context); // Close confirmation
              Navigator.pop(context); // Close edit dialog
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: const Text('Action item deleted'),
                  backgroundColor: ResponsiveHelper.backgroundTertiary,
                  behavior: SnackBarBehavior.floating,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  duration: const Duration(seconds: 2),
                ),
              );
            },
            child: Text(
              'Delete',
              style: TextStyle(
                color: Colors.red.shade400,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
