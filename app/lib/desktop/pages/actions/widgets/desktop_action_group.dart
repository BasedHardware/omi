import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/atoms/omi_checkbox.dart';
import 'package:omi/ui/atoms/omi_icon_badge.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';

class DesktopActionGroup extends StatefulWidget {
  final String conversationTitle;
  final List<ActionItemWithMetadata> actionItems;

  const DesktopActionGroup({
    super.key,
    required this.conversationTitle,
    required this.actionItems,
  });

  @override
  State<DesktopActionGroup> createState() => _DesktopActionGroupState();
}

class _DesktopActionGroupState extends State<DesktopActionGroup> {
  final Map<String, bool> _editingStates = {};
  final Map<String, TextEditingController> _textControllers = {};
  final Map<String, FocusNode> _focusNodes = {};

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
    for (final item in widget.actionItems) {
      _editingStates[item.id] = false;
      _textControllers[item.id] = TextEditingController();
      _focusNodes[item.id] = FocusNode();

      // Listen for focus changes to save when user clicks outside
      _focusNodes[item.id]!.addListener(() {
        if (!_focusNodes[item.id]!.hasFocus && _editingStates[item.id] == true) {
          _saveChanges(item.id);
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

  void _startEditing(String itemId) {
    final item = widget.actionItems.firstWhere((item) => item.id == itemId);
    setState(() {
      _editingStates[itemId] = true;
      _textControllers[itemId]!.text = item.description;
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNodes[itemId]!.requestFocus();
      _textControllers[itemId]!.selection =
          TextSelection(baseOffset: 0, extentOffset: _textControllers[itemId]!.text.length);
    });
  }

  void _cancelEditing(String itemId) {
    setState(() {
      _editingStates[itemId] = false;
    });
  }

  void _saveChanges(String itemId) async {
    if (_editingStates[itemId] != true) return;

    final item = widget.actionItems.firstWhere((item) => item.id == itemId);
    final newText = _textControllers[itemId]!.text.trim();
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
      _cancelEditing(itemId);
      return;
    }

    try {
      
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      await provider.updateActionItemDescription(item, newText);
      
      setState(() {
        _editingStates[itemId] = false;
      });
      _showSavedMessage();
    } catch (e) {
      debugPrint('Error updating action item description: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Failed to update action item'),
          backgroundColor: Colors.red.shade400,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          duration: const Duration(seconds: 2),
        ),
      );
    }
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
          Container(
            padding: const EdgeInsets.all(16),
            decoration: const BoxDecoration(
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
              ),
            ),
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
                            widget.conversationTitle.isNotEmpty
                                ? widget.conversationTitle
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
                  ],
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

  Widget _buildGroupedActionItem(BuildContext context, ActionItemWithMetadata item) {
    final isEditing = _editingStates[item.id] == true;

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
              _toggleCompletion(context, item);
            },
          ),

          const SizedBox(width: 10),

          // Content
          Expanded(
            child: isEditing
                ? TextField(
                      controller: _textControllers[item.id],
                      focusNode: _focusNodes[item.id],
                      style: const TextStyle(
                          color: ResponsiveHelper.textPrimary, fontSize: 14, height: 1.3, fontWeight: FontWeight.w500),
                      decoration: const InputDecoration(
                          border: InputBorder.none, contentPadding: EdgeInsets.zero, isDense: true),
                      maxLines: null,
                      textInputAction: TextInputAction.done,
                      onSubmitted: (_) => _saveChanges(item.id),
                      onChanged: (_) => setState(() {}),
                    )
                : GestureDetector(
                    onTap: () => _startEditing(item.id),
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
              icon: (_textControllers[item.id]?.text.trim() != item.description)
                  ? FontAwesomeIcons.check
                  : FontAwesomeIcons.xmark,
              onPressed: (_textControllers[item.id]?.text.trim() != item.description)
                  ? () => _saveChanges(item.id)
                  : () => _cancelEditing(item.id),
              style: OmiIconButtonStyle.neutral,
              color: (_textControllers[item.id]?.text.trim() != item.description)
                  ? Colors.green.shade600
                  : ResponsiveHelper.textSecondary,
              size: 24,
              iconSize: 14,
            )
          else
            OmiIconButton(
              icon: FontAwesomeIcons.pen,
              onPressed: () => _startEditing(item.id),
              style: OmiIconButtonStyle.neutral,
              size: 18,
              iconSize: 14,
              color: ResponsiveHelper.textSecondary,
            ),
        ],
      ),
    );
  }

  void _toggleCompletion(BuildContext context, ActionItemWithMetadata item) {
    final newValue = !item.completed;
    context.read<ActionItemsProvider>().updateActionItemState(item, newValue);
  }


}
