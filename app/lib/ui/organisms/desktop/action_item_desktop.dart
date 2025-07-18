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
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/atoms/omi_checkbox.dart';
import 'package:omi/ui/molecules/omi_popup_menu.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';

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
    _textController = TextEditingController();
    _focusNode = FocusNode();

    // Listen for focus changes to save when user clicks outside
    _focusNode.addListener(() {
      if (!_focusNode.hasFocus && _isEditing) {
        _saveChanges();
      }
    });
  }

  @override
  void didUpdateWidget(DesktopActionItem oldWidget) {
    super.didUpdateWidget(oldWidget);
  }

  @override
  void dispose() {
    _textController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _startEditing() {
    setState(() {
      _isEditing = true;
      _textController.text = widget.actionItem.description;
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNode.requestFocus();
      _textController.selection = TextSelection(baseOffset: 0, extentOffset: _textController.text.length);
    });
  }

  void _cancelEditing() => setState(() => _isEditing = false);

  void _saveChanges() async {
    if (!_isEditing) return;

    final newText = _textController.text.trim();
    final originalText = widget.actionItem.description;

    if (newText.isEmpty) {
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
      _cancelEditing();
      return;
    }

    updateActionItemDescription(widget.conversation.id, originalText, newText, widget.itemIndex)
        .catchError((e) => debugPrint('$e'));

    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);
    convoProvider.updateActionItemDescriptionInConversation(widget.conversation.id, widget.itemIndex, newText);

    setState(() => _isEditing = false);
    _showSavedMessage();
  }

  void _showSavedMessage() {
    final overlay = Overlay.of(context);
    late OverlayEntry entry;
    entry = OverlayEntry(
      builder: (_) => Positioned(
        top: 50,
        right: 20,
        child: Material(
          color: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.green.shade600,
              borderRadius: BorderRadius.circular(8),
              boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.2), blurRadius: 8, offset: const Offset(0, 4))],
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(FontAwesomeIcons.check, color: Colors.white, size: 14),
                SizedBox(width: 8),
                Text('Saved', style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500)),
              ],
            ),
          ),
        ),
      ),
    );
    overlay.insert(entry);
    Future.delayed(const Duration(seconds: 2), () => entry.remove());
  }

  bool get _hasChanges => _textController.text.trim() != widget.actionItem.description;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Container(
      margin: const EdgeInsets.only(left: 20, right: 20, bottom: 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: _isEditing
                ? ResponsiveHelper.purplePrimary.withOpacity(0.5)
                : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
          boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 8, offset: const Offset(0, 2))],
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            OmiCheckbox(
              value: widget.actionItem.completed,
              onChanged: (v) {
                if (_isEditing) return;
                _toggleCompletion(context);
              },
              size: 20,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _isEditing
                      ? KeyboardListener(
                          focusNode: FocusNode(),
                          onKeyEvent: (KeyEvent event) {
                            if (event is KeyDownEvent) {
                              if (event.logicalKey == LogicalKeyboardKey.enter) {
                                if (!HardwareKeyboard.instance.isShiftPressed) {
                                  // Enter without Shift: save changes
                                  _saveChanges();
                                }
                                // Enter with Shift: allow new line (default behavior)
                              }
                            }
                          },
                          child: TextField(
                            controller: _textController,
                            focusNode: _focusNode,
                            style: const TextStyle(
                                color: ResponsiveHelper.textPrimary,
                                fontSize: 15,
                                height: 1.4,
                                fontWeight: FontWeight.w500),
                            decoration: const InputDecoration(
                                border: InputBorder.none, contentPadding: EdgeInsets.zero, isDense: true),
                            maxLines: null,
                            onChanged: (_) => setState(() {}),
                          ),
                        )
                      : GestureDetector(
                          onTap: _startEditing,
                          child: AnimatedDefaultTextStyle(
                            duration: const Duration(milliseconds: 250),
                            curve: Curves.easeInOut,
                            style: TextStyle(
                              color: widget.actionItem.completed
                                  ? ResponsiveHelper.textTertiary
                                  : ResponsiveHelper.textPrimary,
                              decoration:
                                  widget.actionItem.completed ? TextDecoration.lineThrough : TextDecoration.none,
                              decorationColor: ResponsiveHelper.textTertiary,
                              decorationThickness: 1.5,
                              fontSize: 15,
                              height: 1.4,
                              fontWeight: FontWeight.w500,
                            ),
                            child: Text(widget.actionItem.description),
                          ),
                        ),
                  const SizedBox(height: 8),
                  Row(children: [
                    const SizedBox(width: 6),
                    Expanded(
                        child: Text(
                            widget.conversation.structured.title.isNotEmpty
                                ? widget.conversation.structured.title
                                : 'Untitled Conversation',
                            style: const TextStyle(color: ResponsiveHelper.textTertiary, fontSize: 12),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis))
                  ]),
                ],
              ),
            ),
            const SizedBox(width: 12),
            _isEditing
                ? OmiIconButton(
                    icon: _hasChanges ? FontAwesomeIcons.check : FontAwesomeIcons.xmark,
                    onPressed: _hasChanges ? _saveChanges : _cancelEditing,
                    style: OmiIconButtonStyle.outline,
                    color: _hasChanges ? Colors.green.shade600 : ResponsiveHelper.textSecondary,
                    size: 32,
                  )
                : _buildQuickActions(context),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    return OmiPopupMenuButton<String>(
      icon: FontAwesomeIcons.ellipsisVertical,
      itemBuilder: (context) => [
        PopupMenuItem<String>(
            value: 'toggle',
            child: Row(children: [
              Icon(widget.actionItem.completed ? FontAwesomeIcons.xmark : FontAwesomeIcons.check,
                  color: ResponsiveHelper.textSecondary, size: 14),
              const SizedBox(width: 8),
              Text(widget.actionItem.completed ? 'Mark Incomplete' : 'Mark Complete',
                  style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14))
            ])),
        PopupMenuItem<String>(
            value: 'delete',
            child: Row(children: [
              Icon(FontAwesomeIcons.trash, color: Colors.red.shade400, size: 14),
              const SizedBox(width: 8),
              Text('Delete', style: TextStyle(color: Colors.red.shade400, fontSize: 14))
            ])),
      ],
      onSelected: (value) => _handleMenuSelection(value, context),
    );
  }

  void _handleMenuSelection(String value, BuildContext context) {
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
    HapticFeedback.lightImpact();
    final newValue = !widget.actionItem.completed;
    MixpanelManager().actionItemToggledCompletionOnActionItemsPage(
      conversationId: widget.conversation.id,
      actionItemDescription: widget.actionItem.description,
      isCompleted: newValue,
    );
    context.read<ConversationProvider>().updateGlobalActionItemState(widget.conversation, widget.itemIndex, newValue);
  }

  void _showDeleteConfirmation(BuildContext context) {
    OmiConfirmDialog.show(context,
            title: 'Delete Action Item', message: 'Are you sure you want to delete this action item?')
        .then((confirmed) {
      if (confirmed == true) {
        context
            .read<ConversationProvider>()
            .deleteActionItemAndUpdateLocally(widget.conversation.id, widget.itemIndex, widget.actionItem);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Action item deleted'),
            backgroundColor: ResponsiveHelper.backgroundTertiary,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            duration: const Duration(seconds: 2),
          ),
        );
      }
    });
  }
}
