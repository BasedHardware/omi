import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

class DesktopActionItem extends StatefulWidget {
  final ActionItem actionItem;
  final ServerConversation conversation;
  final int itemIndex;

  const DesktopActionItem({
    super.key,
    required this.actionItem,
    required this.conversation,
    required this.itemIndex,
  });

  @override
  State<DesktopActionItem> createState() => _DesktopActionItemState();
}

class _DesktopActionItemState extends State<DesktopActionItem> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  bool _isEditing = false;
  late TextEditingController _textController;
  late FocusNode _focusNode;

  @override
  void initState() {
    super.initState();
    debugPrint('🔧 DesktopActionItem.initState() - Item: "${widget.actionItem.description}", Index: ${widget.itemIndex}');
    _textController = TextEditingController();
    _focusNode = FocusNode();
  }

  @override
  void didUpdateWidget(DesktopActionItem oldWidget) {
    super.didUpdateWidget(oldWidget);
    debugPrint('🔧 DesktopActionItem.didUpdateWidget() - Old: "${oldWidget.actionItem.description}", New: "${widget.actionItem.description}"');
    if (oldWidget.actionItem.description != widget.actionItem.description) {
      debugPrint('🔧 Action item description changed from "${oldWidget.actionItem.description}" to "${widget.actionItem.description}"');
    }
  }

  @override
  void dispose() {
    debugPrint('🔧 DesktopActionItem.dispose() - Item: "${widget.actionItem.description}"');
    _textController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _startEditing() {
    debugPrint('🔧 Starting edit mode for: "${widget.actionItem.description}"');
    setState(() {
      _isEditing = true;
      _textController.text = widget.actionItem.description;
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNode.requestFocus();
      _textController.selection = TextSelection(
        baseOffset: 0,
        extentOffset: _textController.text.length,
      );
      debugPrint('🔧 Edit mode activated, text controller set to: "${_textController.text}"');
    });
  }

  void _cancelEditing() {
    debugPrint('🔧 Canceling edit mode for: "${widget.actionItem.description}"');
    setState(() {
      _isEditing = false;
    });
  }

  void _saveChanges() async {
    final newText = _textController.text.trim();
    final originalText = widget.actionItem.description;

    debugPrint('🔧 _saveChanges() called');
    debugPrint('🔧 Original text: "$originalText"');
    debugPrint('🔧 New text: "$newText"');
    debugPrint('🔧 Conversation ID: ${widget.conversation.id}');
    debugPrint('🔧 Item index: ${widget.itemIndex}');

    if (newText.isEmpty) {
      debugPrint('🔧 Save failed: empty text');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Action item description cannot be empty'),
          backgroundColor: Colors.red.shade400,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          duration: const Duration(seconds: 2),
        ),
      );
      return;
    }

    if (newText == originalText) {
      debugPrint('🔧 Save skipped: no changes detected');
      _cancelEditing();
      return;
    }

    debugPrint('🔧 Proceeding with save operation...');

    // Update API in background (don't await like mobile does)
    debugPrint('🔧 Calling updateActionItemDescription API...');
    updateActionItemDescription(
      widget.conversation.id,
      originalText,
      newText,
      widget.itemIndex,
    ).then((success) {
      debugPrint('🔧 API call completed. Success: $success');
    }).catchError((error) {
      debugPrint('🔧 API call failed: $error');
    });

    // Update provider immediately (like mobile does)
    debugPrint('🔧 Updating provider...');
    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);

    // Log provider state before update
    final conversation = convoProvider.conversations.firstWhere(
      (c) => c.id == widget.conversation.id,
      orElse: () => throw Exception('Conversation not found'),
    );
    debugPrint('🔧 Before provider update - Action item at index ${widget.itemIndex}: "${conversation.structured.actionItems[widget.itemIndex].description}"');

    convoProvider.updateActionItemDescriptionInConversation(
      widget.conversation.id,
      widget.itemIndex,
      newText,
    );

    // Log provider state after update
    final updatedConversation = convoProvider.conversations.firstWhere(
      (c) => c.id == widget.conversation.id,
      orElse: () => throw Exception('Conversation not found'),
    );
    debugPrint('🔧 After provider update - Action item at index ${widget.itemIndex}: "${updatedConversation.structured.actionItems[widget.itemIndex].description}"');

    // Exit editing mode
    debugPrint('🔧 Exiting edit mode...');
    setState(() {
      _isEditing = false;
    });

    // Show success message
    debugPrint('🔧 Showing saved message...');
    _showSavedMessage();

    debugPrint('🔧 Save operation completed successfully');
  }

  void _showSavedMessage() {
    debugPrint('🔧 Displaying "Saved" notification');
    final overlay = Overlay.of(context);
    late OverlayEntry overlayEntry;

    overlayEntry = OverlayEntry(
      builder: (context) => Positioned(
        top: 50,
        right: 20,
        child: Material(
          color: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.green.shade600,
              borderRadius: BorderRadius.circular(8),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.2),
                  blurRadius: 8,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  FontAwesomeIcons.check,
                  color: Colors.white,
                  size: 14,
                ),
                const SizedBox(width: 8),
                Text(
                  'Saved',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    overlay.insert(overlayEntry);

    Future.delayed(const Duration(seconds: 2), () {
      debugPrint('🔧 Removing "Saved" notification');
      overlayEntry.remove();
    });
  }

  bool get _hasChanges => _textController.text.trim() != widget.actionItem.description;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    debugPrint('🔧 DesktopActionItem.build() - Current description: "${widget.actionItem.description}", Is editing: $_isEditing');

    return Container(
      margin: const EdgeInsets.only(left: 20, right: 20, bottom: 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: _isEditing ? ResponsiveHelper.purplePrimary.withOpacity(0.5) : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.05),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            GestureDetector(
              onTap: _isEditing ? null : () => _toggleCompletion(context),
              child: Container(
                width: 20,
                height: 20,
                margin: const EdgeInsets.only(top: 2),
                decoration: BoxDecoration(
                  color: widget.actionItem.completed ? ResponsiveHelper.purplePrimary : Colors.transparent,
                  border: Border.all(
                    color: widget.actionItem.completed ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                    width: 1.5,
                  ),
                  borderRadius: BorderRadius.circular(5),
                ),
                child: widget.actionItem.completed
                    ? Icon(
                        FontAwesomeIcons.check,
                        size: 12,
                        color: Colors.white,
                      )
                    : null,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _isEditing
                      ? TextField(
                          controller: _textController,
                          focusNode: _focusNode,
                          style: TextStyle(
                            color: ResponsiveHelper.textPrimary,
                            fontSize: 15,
                            height: 1.4,
                            fontWeight: FontWeight.w500,
                          ),
                          decoration: InputDecoration(
                            border: InputBorder.none,
                            contentPadding: EdgeInsets.zero,
                            isDense: true,
                          ),
                          maxLines: null,
                          onSubmitted: (_) {
                            debugPrint('🔧 TextField onSubmitted triggered');
                            _saveChanges();
                          },
                          onChanged: (_) {
                            debugPrint('🔧 TextField onChanged - Current text: "${_textController.text}"');
                            setState(() {});
                          },
                        )
                      : GestureDetector(
                          onTap: () {
                            debugPrint('🔧 Text tapped, starting edit mode');
                            _startEditing();
                          },
                          child: Text(
                            widget.actionItem.description,
                            style: TextStyle(
                              color: widget.actionItem.completed ? ResponsiveHelper.textTertiary : ResponsiveHelper.textPrimary,
                              decoration: widget.actionItem.completed ? TextDecoration.lineThrough : null,
                              decorationColor: ResponsiveHelper.textTertiary,
                              fontSize: 15,
                              height: 1.4,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      const SizedBox(width: 6),
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
                ],
              ),
            ),
            const SizedBox(width: 12),
            _isEditing
                ? GestureDetector(
                    onTap: () {
                      debugPrint('🔧 Save/Cancel button tapped - Has changes: $_hasChanges');
                      _hasChanges ? _saveChanges() : _cancelEditing();
                    },
                    child: Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: _hasChanges ? Colors.green.shade600 : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(
                        _hasChanges ? FontAwesomeIcons.check : FontAwesomeIcons.xmark,
                        color: _hasChanges ? Colors.white : ResponsiveHelper.textSecondary,
                        size: 14,
                      ),
                    ),
                  )
                : _buildQuickActions(context),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    return PopupMenuButton<String>(
      color: ResponsiveHelper.backgroundSecondary,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
      ),
      child: Container(
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Icon(
          FontAwesomeIcons.ellipsisVertical,
          color: ResponsiveHelper.textSecondary,
          size: 14,
        ),
      ),
      itemBuilder: (context) => [
        PopupMenuItem<String>(
          value: 'toggle',
          child: Row(
            children: [
              Icon(
                widget.actionItem.completed ? FontAwesomeIcons.xmark : FontAwesomeIcons.check,
                color: ResponsiveHelper.textSecondary,
                size: 14,
              ),
              const SizedBox(width: 8),
              Text(
                widget.actionItem.completed ? 'Mark Incomplete' : 'Mark Complete',
                style: TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 14,
                ),
              ),
            ],
          ),
        ),
        PopupMenuItem<String>(
          value: 'delete',
          child: Row(
            children: [
              Icon(
                FontAwesomeIcons.trash,
                color: Colors.red.shade400,
                size: 14,
              ),
              const SizedBox(width: 8),
              Text(
                'Delete',
                style: TextStyle(
                  color: Colors.red.shade400,
                  fontSize: 14,
                ),
              ),
            ],
          ),
        ),
      ],
      onSelected: (value) => _handleMenuSelection(value, context),
    );
  }

  void _handleMenuSelection(String value, BuildContext context) {
    debugPrint('🔧 Menu selection: $value');
    switch (value) {
      case 'toggle':
        _toggleCompletion(context);
        break;
      case 'delete':
        _showDeleteConfirmation(context);
        break;
    }
  }

  void _toggleCompletion(BuildContext context) {
    debugPrint('🔧 Toggling completion for: "${widget.actionItem.description}"');
    HapticFeedback.lightImpact();
    final newValue = !widget.actionItem.completed;
    debugPrint('🔧 New completion value: $newValue');
    MixpanelManager().actionItemToggledCompletionOnActionItemsPage(
      conversationId: widget.conversation.id,
      actionItemDescription: widget.actionItem.description,
      isCompleted: newValue,
    );
    context.read<ConversationProvider>().updateGlobalActionItemState(
          widget.conversation,
          widget.itemIndex,
          newValue,
        );
  }

  void _showDeleteConfirmation(BuildContext context) {
    debugPrint('🔧 Showing delete confirmation for: "${widget.actionItem.description}"');
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
              debugPrint('🔧 Deleting action item: "${widget.actionItem.description}"');
              context.read<ConversationProvider>().deleteActionItemAndUpdateLocally(
                    widget.conversation.id,
                    widget.itemIndex,
                    widget.actionItem,
                  );
              Navigator.pop(context);
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
