import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/cupertino.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/backend/preferences.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/atoms/omi_checkbox.dart';
import 'package:omi/ui/molecules/omi_popup_menu.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/desktop/pages/actions/widgets/desktop_action_item_form_dialog.dart';

class DesktopActionItem extends StatefulWidget {
  final ActionItemWithMetadata actionItem;
  final VoidCallback? onChanged;
  final bool isSelectionMode;
  final bool isSelected;
  final VoidCallback? onLongPress;
  final VoidCallback? onSelectionToggle;
  final bool isSnoozedTab;

  const DesktopActionItem({
    super.key,
    required this.actionItem,
    this.onChanged,
    this.isSelectionMode = false,
    this.isSelected = false,
    this.onLongPress,
    this.onSelectionToggle,
    this.isSnoozedTab = false,
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
    if (widget.actionItem.isLocked) {
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => const UsagePage(showUpgradeDialog: true),
        ),
      );
      return;
    }

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

    try {
      // await updateActionItemDescription(widget.actionItem.conversationId, originalText, newText, widget.actionItem.index);

      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      await provider.updateActionItemDescription(widget.actionItem, newText);

      setState(() => _isEditing = false);
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

  bool get _hasChanges => _textController.text.trim() != widget.actionItem.description;

  Widget _buildDueDateChip() {
    if (widget.actionItem.dueAt == null) return const SizedBox.shrink();

    final now = DateTime.now();
    final dueDate = widget.actionItem.dueAt!;
    final isOverdue = dueDate.isBefore(now) && !widget.actionItem.completed;
    final isToday = _isSameDay(dueDate, now);
    final isTomorrow = _isSameDay(dueDate, now.add(const Duration(days: 1)));
    final isThisWeek = dueDate.isAfter(now) && dueDate.isBefore(now.add(const Duration(days: 7)));

    Color chipColor;
    Color textColor;
    IconData icon;
    String dueDateText;

    // For snoozed tab, always show actual date/time instead of relative labels
    if (widget.isSnoozedTab) {
      chipColor = ResponsiveHelper.backgroundTertiary.withOpacity(0.3);
      textColor = ResponsiveHelper.textTertiary;
      icon = FontAwesomeIcons.calendar;
      dueDateText = _formatDueDate(dueDate, showFullDate: true);
    } else if (widget.actionItem.completed) {
      chipColor = ResponsiveHelper.backgroundTertiary.withOpacity(0.3);
      textColor = ResponsiveHelper.textTertiary;
      icon = FontAwesomeIcons.check;
      dueDateText = _formatDueDate(dueDate);
    } else if (isOverdue) {
      chipColor = Colors.red.withOpacity(0.15);
      textColor = Colors.red.shade300;
      icon = FontAwesomeIcons.triangleExclamation;
      dueDateText = 'Overdue';
    } else if (isToday) {
      chipColor = Colors.orange.withOpacity(0.15);
      textColor = Colors.orange.shade300;
      icon = FontAwesomeIcons.calendarDay;
      dueDateText = 'Today';
    } else if (isTomorrow) {
      chipColor = Colors.blue.withOpacity(0.15);
      textColor = Colors.blue.shade300;
      icon = FontAwesomeIcons.calendar;
      dueDateText = 'Tomorrow';
    } else if (isThisWeek) {
      chipColor = Colors.green.withOpacity(0.15);
      textColor = Colors.green.shade300;
      icon = FontAwesomeIcons.calendarWeek;
      dueDateText = _formatDueDate(dueDate);
    } else {
      chipColor = ResponsiveHelper.purplePrimary.withOpacity(0.15);
      textColor = ResponsiveHelper.purplePrimary;
      icon = FontAwesomeIcons.clock;
      dueDateText = _formatDueDate(dueDate);
    }

    return GestureDetector(
      onTap: _isEditing ? null : () => _openDateTimePicker(),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: chipColor,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: textColor.withOpacity(0.3),
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 12,
              color: textColor,
            ),
            const SizedBox(width: 4),
            Text(
              dueDateText,
              style: TextStyle(
                color: textColor,
                fontSize: 11,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  bool _isSameDay(DateTime date1, DateTime date2) {
    return date1.year == date2.year && date1.month == date2.month && date1.day == date2.day;
  }

  String _formatDueDate(DateTime date, {bool showFullDate = false}) {
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    if (showFullDate) {
      final now = DateTime.now();
      final hour = date.hour;
      final minute = date.minute;
      final hasTime = hour != 0 || minute != 0;

      String dateStr = '${months[date.month - 1]} ${date.day}';

      if (date.year != now.year) {
        dateStr += ', ${date.year}';
      }

      if (hasTime && !(hour == 23 && minute == 59)) {
        final period = hour >= 12 ? 'PM' : 'AM';
        final displayHour = hour == 0 ? 12 : (hour > 12 ? hour - 12 : hour);
        final displayMinute = minute.toString().padLeft(2, '0');
        dateStr += ', $displayHour:$displayMinute $period';
      }

      return dateStr;
    }

    final now = DateTime.now();
    final difference = date.difference(now).inDays;

    if (difference == 0) {
      return 'Today';
    } else if (difference == 1) {
      return 'Tomorrow';
    } else if (difference == -1) {
      return 'Yesterday';
    } else if (difference > 1 && difference <= 7) {
      final weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      return weekdays[date.weekday - 1];
    } else {
      return '${months[date.month - 1]} ${date.day}';
    }
  }

  Future<void> _openDateTimePicker() async {
    final DateTime? result = await showCupertinoModalPopup<DateTime>(
      context: context,
      builder: (context) => _DateTimePickerSheet(
        initialDateTime: widget.actionItem.dueAt,
        minimumDate: widget.actionItem.createdAt ?? DateTime.now(),
      ),
    );

    if (result != null) {
      try {
        final provider = Provider.of<ActionItemsProvider>(context, listen: false);
        await provider.updateActionItemDueDate(widget.actionItem, result);
        _showSavedMessage();
      } catch (e) {
        debugPrint('Error updating action item due date: $e');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Failed to update due date'),
            backgroundColor: Colors.red.shade400,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            duration: const Duration(seconds: 2),
          ),
        );
      }
    }
  }

  Widget _buildLockedOverlay(BuildContext context) {
    return Positioned.fill(
      child: ClipRRect(
        borderRadius: const BorderRadius.all(Radius.circular(8)),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 2.0, sigmaY: 2.0),
          child: Container(
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.black.withOpacity(0.01),
            ),
            child: const Text(
              'Upgrade to unlimited',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Container(
      margin: const EdgeInsets.only(left: 20, right: 20, bottom: 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: widget.isSelected
              ? ResponsiveHelper.purplePrimary.withOpacity(0.1)
              : ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: widget.isSelected
                ? ResponsiveHelper.purplePrimary.withOpacity(0.5)
                : (_isEditing
                    ? ResponsiveHelper.purplePrimary.withOpacity(0.5)
                    : ResponsiveHelper.backgroundTertiary.withOpacity(0.3)),
            width: widget.isSelected ? 2 : 1,
          ),
          boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 8, offset: const Offset(0, 2))],
        ),
        child: GestureDetector(
          onLongPress: widget.onLongPress,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Lock indicator or checkbox
              if (widget.actionItem.isLocked)
                // Show lock icon if locked
                Container(
                  width: 20,
                  height: 20,
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(
                    Icons.lock,
                    color: ResponsiveHelper.purplePrimary,
                    size: 12,
                  ),
                )
              // Selection checkbox when in selection mode
              else if (widget.isSelectionMode)
                GestureDetector(
                  onTap: widget.onSelectionToggle,
                  child: Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: widget.isSelected ? ResponsiveHelper.purplePrimary : Colors.grey.shade600,
                        width: 2,
                      ),
                      color: widget.isSelected ? ResponsiveHelper.purplePrimary : Colors.transparent,
                    ),
                    child: widget.isSelected
                        ? const Icon(
                            Icons.check,
                            color: Colors.white,
                            size: 14,
                          )
                        : null,
                  ),
                )
              // Completion checkbox when not in selection mode
              else
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
                        ? TextField(
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
                            textInputAction: TextInputAction.done,
                            onSubmitted: (_) => _saveChanges(),
                            onChanged: (_) => setState(() {}),
                          )
                        : GestureDetector(
                            onTap: _startEditing,
                            child: Stack(
                              children: [
                                AnimatedDefaultTextStyle(
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
                                if (widget.actionItem.isLocked) _buildLockedOverlay(context),
                              ],
                            ),
                          ),
                    const SizedBox(height: 8),
                    if (widget.actionItem.dueAt != null) _buildDueDateChip(),
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
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    return OmiPopupMenuButton<String>(
      icon: FontAwesomeIcons.ellipsisVertical,
      itemBuilder: (context) => [
        const PopupMenuItem<String>(
          value: 'edit',
          child: Row(
            children: [
              Icon(FontAwesomeIcons.penToSquare, color: ResponsiveHelper.textSecondary, size: 14),
              SizedBox(width: 8),
              Text('Edit', style: TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14))
            ],
          ),
        ),
        PopupMenuItem<String>(
          value: 'toggle',
          child: Row(
            children: [
              Icon(widget.actionItem.completed ? FontAwesomeIcons.xmark : FontAwesomeIcons.check,
                  color: ResponsiveHelper.textSecondary, size: 14),
              const SizedBox(width: 8),
              Text(widget.actionItem.completed ? 'Mark Incomplete' : 'Mark Complete',
                  style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14))
            ],
          ),
        ),
        PopupMenuItem<String>(
          value: 'due_date',
          child: Row(
            children: [
              const Icon(FontAwesomeIcons.calendar, color: ResponsiveHelper.textSecondary, size: 14),
              const SizedBox(width: 8),
              Text(widget.actionItem.dueAt != null ? 'Edit Due Date' : 'Set Due Date',
                  style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14))
            ],
          ),
        ),
        if (widget.actionItem.dueAt != null)
          const PopupMenuItem<String>(
            value: 'clear_due_date',
            child: Row(
              children: [
                Icon(FontAwesomeIcons.xmark, color: ResponsiveHelper.textSecondary, size: 14),
                SizedBox(width: 8),
                Text('Clear Due Date', style: TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14))
              ],
            ),
          ),
        PopupMenuItem<String>(
          value: 'delete',
          child: Row(
            children: [
              Icon(FontAwesomeIcons.trash, color: Colors.red.shade400, size: 14),
              const SizedBox(width: 8),
              Text('Delete', style: TextStyle(color: Colors.red.shade400, fontSize: 14))
            ],
          ),
        ),
      ],
      onSelected: (value) => _handleMenuSelection(value, context),
    );
  }

  void _handleMenuSelection(String value, BuildContext context) {
    switch (value) {
      case 'edit':
        _showEditDialog(context);
        break;
      case 'toggle':
        _toggleCompletion(context);
        break;
      case 'due_date':
        _openDateTimePicker();
        break;
      case 'clear_due_date':
        _clearDueDate();
        break;
      case 'delete':
        _showDeleteConfirmation(context);
        break;
    }
  }

  Future<void> _showEditDialog(BuildContext context) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => DesktopActionItemFormDialog(
        actionItem: widget.actionItem,
      ),
    );
    if (result == true) {
      // Refresh handled by the provider automatically
    }
  }

  void _clearDueDate() async {
    try {
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      await provider.updateActionItemDueDate(widget.actionItem, null);
      _showSavedMessage();

      widget.onChanged?.call();
    } catch (e) {
      debugPrint('Error clearing action item due date: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Failed to clear due date'),
          backgroundColor: Colors.red.shade400,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  void _toggleCompletion(BuildContext context) {
    HapticFeedback.lightImpact();
    final newValue = !widget.actionItem.completed;
    if (widget.actionItem.conversationId != null) {
      MixpanelManager().actionItemToggledCompletionOnActionItemsPage(
        conversationId: widget.actionItem.conversationId!,
        actionItemDescription: widget.actionItem.description,
        isCompleted: newValue,
      );
    }

    MixpanelManager().actionItemChecked(
      actionItemId: widget.actionItem.id,
      completed: newValue,
      timestamp: DateTime.now(),
    );

    context.read<ActionItemsProvider>().updateActionItemState(widget.actionItem, newValue);

    widget.onChanged?.call();
  }

  void _showDeleteConfirmation(BuildContext context) {
    final prefs = SharedPreferencesUtil();

    // Check if user has opted out of delete confirmations
    if (!prefs.showActionItemDeleteConfirmation) {
      // Skip confirmation and proceed with deletion
      context.read<ActionItemsProvider>().deleteActionItem(widget.actionItem);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Action item deleted'),
          backgroundColor: ResponsiveHelper.backgroundTertiary,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          duration: const Duration(seconds: 2),
        ),
      );
      return;
    }

    OmiConfirmDialog.showWithSkipOption(
      context,
      title: 'Delete Action Item',
      message: 'Are you sure you want to delete this action item?',
    ).then((result) {
      if (result?.confirmed == true) {
        // Update preference if user chose to skip future confirmations
        if (result!.skipFutureConfirmations) {
          prefs.showActionItemDeleteConfirmation = false;
        }

        context.read<ActionItemsProvider>().deleteActionItem(widget.actionItem);
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

class _DateTimePickerSheet extends StatefulWidget {
  final DateTime? initialDateTime;
  final DateTime? minimumDate;

  const _DateTimePickerSheet({
    this.initialDateTime,
    this.minimumDate,
  });

  @override
  State<_DateTimePickerSheet> createState() => _DateTimePickerSheetState();
}

class _DateTimePickerSheetState extends State<_DateTimePickerSheet> {
  late DateTime _selectedDateTime;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    final minimumDate = widget.minimumDate ?? now;

    if (widget.initialDateTime != null) {
      _selectedDateTime = widget.initialDateTime!.isBefore(minimumDate) ? minimumDate : widget.initialDateTime!;
    } else {
      _selectedDateTime = now.isBefore(minimumDate) ? minimumDate : now;
    }
  }

  @override
  Widget build(BuildContext context) {
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    final currentMonth = months[_selectedDateTime.month - 1];
    final currentYear = _selectedDateTime.year;
    final minimumDate = widget.minimumDate ?? DateTime.now();

    // Check if we can go to previous month
    final canGoPrevious = _selectedDateTime.year > minimumDate.year ||
        (_selectedDateTime.year == minimumDate.year && _selectedDateTime.month > minimumDate.month);

    return Material(
      child: Container(
        height: MediaQuery.of(context).size.height * 0.65,
        decoration: const BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: Column(
          children: [
            // Handle bar
            Container(
              width: 40,
              height: 4,
              margin: const EdgeInsets.only(top: 12, bottom: 20),
              decoration: BoxDecoration(
                color: ResponsiveHelper.textTertiary,
                borderRadius: BorderRadius.circular(2),
              ),
            ),

            // Header with navigation
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () => Navigator.pop(context),
                    child: const Text(
                      'Cancel',
                      style: TextStyle(
                        color: ResponsiveHelper.textSecondary,
                        fontSize: 17,
                      ),
                    ),
                  ),

                  // Month/Year navigation
                  Row(
                    children: [
                      CupertinoButton(
                        padding: const EdgeInsets.all(8),
                        onPressed: canGoPrevious
                            ? () {
                                final newMonth = _selectedDateTime.month == 1 ? 12 : _selectedDateTime.month - 1;
                                final newYear =
                                    _selectedDateTime.month == 1 ? _selectedDateTime.year - 1 : _selectedDateTime.year;

                                setState(() {
                                  _selectedDateTime = DateTime(
                                    newYear,
                                    newMonth,
                                    _selectedDateTime.day,
                                    _selectedDateTime.hour,
                                    _selectedDateTime.minute,
                                  );
                                });
                              }
                            : null,
                        child: Icon(
                          Icons.chevron_left,
                          color: canGoPrevious ? ResponsiveHelper.textSecondary : ResponsiveHelper.textTertiary,
                          size: 24,
                        ),
                      ),
                      Text(
                        '$currentMonth $currentYear',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                          color: ResponsiveHelper.textPrimary,
                        ),
                      ),
                      CupertinoButton(
                        padding: const EdgeInsets.all(8),
                        onPressed: () {
                          setState(() {
                            _selectedDateTime = DateTime(
                              _selectedDateTime.month == 12 ? _selectedDateTime.year + 1 : _selectedDateTime.year,
                              _selectedDateTime.month == 12 ? 1 : _selectedDateTime.month + 1,
                              _selectedDateTime.day,
                              _selectedDateTime.hour,
                              _selectedDateTime.minute,
                            );
                          });
                        },
                        child: const Icon(
                          Icons.chevron_right,
                          color: ResponsiveHelper.textSecondary,
                          size: 24,
                        ),
                      ),
                    ],
                  ),

                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () => Navigator.pop(context, _selectedDateTime),
                    child: const Text(
                      'Done',
                      style: TextStyle(
                        color: ResponsiveHelper.purplePrimary,
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 10),

            // Selected date and time display
            Container(
              margin: const EdgeInsets.symmetric(horizontal: 20),
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              decoration: BoxDecoration(
                color: ResponsiveHelper.purplePrimary.withOpacity(0.1),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                  width: 1,
                ),
              ),
              child: Row(
                children: [
                  const Icon(
                    FontAwesomeIcons.calendar,
                    color: ResponsiveHelper.purplePrimary,
                    size: 16,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      '${months[_selectedDateTime.month - 1]} ${_selectedDateTime.day}, ${_selectedDateTime.year}',
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                        color: ResponsiveHelper.textPrimary,
                      ),
                    ),
                  ),
                  const Icon(
                    FontAwesomeIcons.clock,
                    color: ResponsiveHelper.purplePrimary,
                    size: 16,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '${_selectedDateTime.hour > 12 ? _selectedDateTime.hour - 12 : (_selectedDateTime.hour == 0 ? 12 : _selectedDateTime.hour)}:${_selectedDateTime.minute.toString().padLeft(2, '0')} ${_selectedDateTime.hour >= 12 ? 'PM' : 'AM'}',
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                      color: ResponsiveHelper.purplePrimary,
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 20),

            // Date and Time Picker
            Expanded(
              child: Theme(
                data: ThemeData.dark().copyWith(
                  cupertinoOverrideTheme: const CupertinoThemeData(
                    brightness: Brightness.dark,
                    primaryColor: ResponsiveHelper.purplePrimary,
                    textTheme: CupertinoTextThemeData(
                      dateTimePickerTextStyle: TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontSize: 20,
                      ),
                    ),
                  ),
                ),
                child: CupertinoDatePicker(
                  mode: CupertinoDatePickerMode.dateAndTime,
                  initialDateTime: _selectedDateTime,
                  minimumDate: widget.minimumDate ?? DateTime.now(),
                  maximumDate: DateTime.now().add(const Duration(days: 365 * 5)),
                  use24hFormat: false,
                  backgroundColor: ResponsiveHelper.backgroundSecondary,
                  onDateTimeChanged: (DateTime newDateTime) {
                    setState(() {
                      _selectedDateTime = newDateTime;
                    });
                  },
                ),
              ),
            ),

            // Bottom safe area
            SizedBox(height: MediaQuery.of(context).padding.bottom + 10),
          ],
        ),
      ),
    );
  }
}
