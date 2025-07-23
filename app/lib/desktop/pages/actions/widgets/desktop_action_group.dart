import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/atoms/omi_checkbox.dart';
import 'package:omi/ui/atoms/omi_icon_badge.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';

class DesktopActionGroup extends StatefulWidget {
  final ServerConversation conversation;
  final List<ActionItem> actionItems;

  const DesktopActionGroup({
    super.key,
    required this.conversation,
    required this.actionItems,
  });

  @override
  State<DesktopActionGroup> createState() => _DesktopActionGroupState();
}

class _DesktopActionGroupState extends State<DesktopActionGroup> {
  final Map<int, bool> _editingStates = {};
  final Map<int, TextEditingController> _textControllers = {};
  final Map<int, FocusNode> _focusNodes = {};

  @override
  void initState() {
    super.initState();
    _initializeControllers();
  }

  @override
  void dispose() {
    _disposeControllers();
    super.dispose();
  }

  void _initializeControllers() {
    for (int i = 0; i < widget.actionItems.length; i++) {
      final itemIndex = widget.conversation.structured.actionItems.indexOf(widget.actionItems[i]);
      _editingStates[itemIndex] = false;
      _textControllers[itemIndex] = TextEditingController();
      _focusNodes[itemIndex] = FocusNode();

      // Listen for focus changes to save when user clicks outside
      _focusNodes[itemIndex]!.addListener(() {
        if (!_focusNodes[itemIndex]!.hasFocus && _editingStates[itemIndex] == true) {
          _saveChanges(itemIndex);
        }
      });
    }
  }

  void _disposeControllers() {
    for (final controller in _textControllers.values) {
      controller.dispose();
    }
    for (final focusNode in _focusNodes.values) {
      focusNode.dispose();
    }
  }

  void _startEditing(int itemIndex) {
    final item =
        widget.actionItems.firstWhere((item) => widget.conversation.structured.actionItems.indexOf(item) == itemIndex);
    setState(() {
      _editingStates[itemIndex] = true;
      _textControllers[itemIndex]!.text = item.description;
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNodes[itemIndex]!.requestFocus();
      _textControllers[itemIndex]!.selection =
          TextSelection(baseOffset: 0, extentOffset: _textControllers[itemIndex]!.text.length);
    });
  }

  void _cancelEditing(int itemIndex) {
    setState(() {
      _editingStates[itemIndex] = false;
    });
  }

  void _saveChanges(int itemIndex) async {
    if (_editingStates[itemIndex] != true) return;

    final item =
        widget.actionItems.firstWhere((item) => widget.conversation.structured.actionItems.indexOf(item) == itemIndex);
    final newText = _textControllers[itemIndex]!.text.trim();
    final originalText = item.description;

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
      _cancelEditing(itemIndex);
      return;
    }

    updateActionItemDescription(widget.conversation.id, originalText, newText, itemIndex)
        .catchError((e) => debugPrint('$e'));

    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);
    convoProvider.updateActionItemDescriptionInConversation(widget.conversation.id, itemIndex, newText);

    setState(() {
      _editingStates[itemIndex] = false;
    });
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

  @override
  Widget build(BuildContext context) {
    final sortedItems = [...widget.actionItems]..sort((a, b) {
        if (a.completed == b.completed) return 0;
        return a.completed ? 1 : -1;
      });

    final incompleteCount = sortedItems.where((item) => !item.completed).length;

    return Container(
      margin: const EdgeInsets.only(left: 20, right: 20, bottom: 16),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Group header
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => _navigateToConversationDetail(context),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
              ),
              child: Container(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    // Conversation icon
                    OmiIconBadge(
                      icon: FontAwesomeIcons.message,
                      bgColor: ResponsiveHelper.purplePrimary.withValues(alpha: 0.2),
                      iconColor: ResponsiveHelper.purplePrimary,
                      radius: 8,
                    ),

                    const SizedBox(width: 12),

                    // Conversation details
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            widget.conversation.structured.title.isNotEmpty
                                ? widget.conversation.structured.title
                                : 'Untitled Conversation',
                            style: const TextStyle(
                              color: ResponsiveHelper.textPrimary,
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '$incompleteCount remaining',
                            style: const TextStyle(
                              color: ResponsiveHelper.textSecondary,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),

                    // Navigate icon
                    const Icon(
                      FontAwesomeIcons.chevronRight,
                      color: ResponsiveHelper.textTertiary,
                      size: 12,
                    ),
                  ],
                ),
              ),
            ),
          ),

          // Divider
          Container(
            height: 1,
            margin: const EdgeInsets.symmetric(horizontal: 16),
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          ),

          // Action items list
          ...sortedItems.asMap().entries.map((entry) {
            final index = entry.key;
            final item = entry.value;

            return Container(
              margin: EdgeInsets.only(
                left: 16,
                right: 16,
                top: 12,
                bottom: index == sortedItems.length - 1 ? 16 : 0,
              ),
              child: _buildGroupedActionItem(context, item),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildGroupedActionItem(BuildContext context, ActionItem item) {
    final itemIndex = widget.conversation.structured.actionItems.indexOf(item);
    final isEditing = _editingStates[itemIndex] == true;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isEditing
              ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.5)
              : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Checkbox
          OmiCheckbox(
            value: item.completed,
            onChanged: (v) {
              if (isEditing) return;
              _toggleCompletion(context, item, itemIndex);
            },
          ),

          const SizedBox(width: 10),

          // Content
          Expanded(
            child: isEditing
                ? KeyboardListener(
                    focusNode: FocusNode(),
                    onKeyEvent: (KeyEvent event) {
                      if (event is KeyDownEvent) {
                        if (event.logicalKey == LogicalKeyboardKey.enter) {
                          if (!HardwareKeyboard.instance.isShiftPressed) {
                            // Enter without Shift: save changes
                            _saveChanges(itemIndex);
                          }
                          // Enter with Shift: allow new line (default behavior)
                        }
                      }
                    },
                    child: TextField(
                      controller: _textControllers[itemIndex],
                      focusNode: _focusNodes[itemIndex],
                      style: const TextStyle(
                          color: ResponsiveHelper.textPrimary, fontSize: 14, height: 1.3, fontWeight: FontWeight.w500),
                      decoration: const InputDecoration(
                          border: InputBorder.none, contentPadding: EdgeInsets.zero, isDense: true),
                      maxLines: null,
                      onChanged: (_) => setState(() {}),
                    ),
                  )
                : GestureDetector(
                    onTap: () => _startEditing(itemIndex),
                    child: Text(
                      item.description,
                      style: TextStyle(
                        color: item.completed ? ResponsiveHelper.textTertiary : ResponsiveHelper.textPrimary,
                        decoration: item.completed ? TextDecoration.lineThrough : null,
                        decorationColor: ResponsiveHelper.textTertiary,
                        fontSize: 14,
                        height: 1.3,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
          ),

          const SizedBox(width: 8),

          // Quick action button
          if (isEditing)
            OmiIconButton(
              icon: (_textControllers[itemIndex]?.text.trim() != item.description)
                  ? FontAwesomeIcons.check
                  : FontAwesomeIcons.xmark,
              onPressed: (_textControllers[itemIndex]?.text.trim() != item.description)
                  ? () => _saveChanges(itemIndex)
                  : () => _cancelEditing(itemIndex),
              style: OmiIconButtonStyle.outline,
              color: (_textControllers[itemIndex]?.text.trim() != item.description)
                  ? Colors.green.shade600
                  : ResponsiveHelper.textSecondary,
              size: 24,
            )
          else
            OmiIconButton(
              icon: FontAwesomeIcons.pen,
              onPressed: () => _startEditing(itemIndex),
              style: OmiIconButtonStyle.outline,
              size: 24,
              color: ResponsiveHelper.textSecondary,
            ),
        ],
      ),
    );
  }

  void _toggleCompletion(BuildContext context, ActionItem item, int itemIndex) {
    final newValue = !item.completed;
    context.read<ConversationProvider>().updateGlobalActionItemState(
          widget.conversation,
          itemIndex,
          newValue,
        );
  }

  void _navigateToConversationDetail(BuildContext context) async {
    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);

    DateTime? date;
    int? index;

    for (final entry in convoProvider.groupedConversations.entries) {
      final foundIndex = entry.value.indexWhere((c) => c.id == widget.conversation.id);
      if (foundIndex != -1) {
        date = entry.key;
        index = foundIndex;
        break;
      }
    }

    if (date != null && index != null) {
      final detailProvider = Provider.of<ConversationDetailProvider>(context, listen: false);
      detailProvider.updateConversation(index, date);

      convoProvider.onConversationTap(index);

      await routeToPage(
        context,
        ConversationDetailPage(conversation: widget.conversation),
      );
    }
  }
}
