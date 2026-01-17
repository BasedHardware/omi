import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/ui/atoms/omi_checkbox.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopActionItemFormDialog extends StatefulWidget {
  final ActionItemWithMetadata? actionItem;
  final String? conversationId;
  final DateTime? defaultDueDate;

  const DesktopActionItemFormDialog({
    super.key,
    this.actionItem,
    this.conversationId,
    this.defaultDueDate,
  });

  @override
  State<DesktopActionItemFormDialog> createState() => _DesktopActionItemFormDialogState();
}

class _DesktopActionItemFormDialogState extends State<DesktopActionItemFormDialog> {
  late TextEditingController _descriptionController;
  late FocusNode _descriptionFocusNode;
  bool _isCompleted = false;
  DateTime? _dueDate;
  bool _isLoading = false;

  bool get _isEditing => widget.actionItem != null;
  bool get _canSave => _descriptionController.text.trim().isNotEmpty && !_isLoading;

  @override
  void initState() {
    super.initState();
    _descriptionController = TextEditingController();
    _descriptionFocusNode = FocusNode();

    if (_isEditing) {
      _descriptionController.text = widget.actionItem!.description;
      _isCompleted = widget.actionItem!.completed;
      _dueDate = widget.actionItem!.dueAt;
    } else {
      _dueDate = widget.defaultDueDate;
    }

    if (!_isEditing) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _descriptionFocusNode.requestFocus();
      });
    }
  }

  @override
  void dispose() {
    _descriptionController.dispose();
    _descriptionFocusNode.dispose();
    super.dispose();
  }

  void _showSnackBar(String message, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: color,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  Future<void> _openDateTimePicker() async {
    final DateTime? result = await showCupertinoModalPopup<DateTime>(
      context: context,
      builder: (context) => _DateTimePickerSheet(
        initialDateTime: _dueDate,
        minimumDate: DateTime.now(),
      ),
    );

    if (result != null) {
      setState(() {
        _dueDate = result;
      });
    }
  }

  void _clearDueDate() {
    setState(() {
      _dueDate = null;
    });
  }

  String _formatDueDateWithTime(DateTime date) {
    final now = DateTime.now();
    final isToday = _isSameDay(date, now);
    final isTomorrow = _isSameDay(date, now.add(const Duration(days: 1)));

    String dateStr;
    if (isToday) {
      dateStr = 'Today';
    } else if (isTomorrow) {
      dateStr = 'Tomorrow';
    } else {
      final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      dateStr = '${months[date.month - 1]} ${date.day}';
    }

    final hour = date.hour > 12 ? date.hour - 12 : (date.hour == 0 ? 12 : date.hour);
    final minute = date.minute.toString().padLeft(2, '0');
    final period = date.hour >= 12 ? 'PM' : 'AM';

    return '$dateStr at $hour:$minute $period';
  }

  bool _isSameDay(DateTime date1, DateTime date2) {
    return date1.year == date2.year && date1.month == date2.month && date1.day == date2.day;
  }

  Future<void> _saveActionItem() async {
    if (!_canSave) return;

    setState(() {
      _isLoading = true;
    });

    try {
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      final description = _descriptionController.text.trim();

      if (_isEditing) {
        final original = widget.actionItem!;
        final descriptionChanged = original.description != description;
        final dueDateChanged = original.dueAt != _dueDate;
        final completionChanged = original.completed != _isCompleted;

        // Update existing action item
        if (descriptionChanged) {
          await provider.updateActionItemDescription(original, description);
        }
        if (completionChanged) {
          await provider.updateActionItemState(original, _isCompleted);
        }
        if (dueDateChanged) {
          await provider.updateActionItemDueDate(original, _dueDate);
        }

        // Track action item edit
        if (descriptionChanged || dueDateChanged) {
          MixpanelManager().actionItemEdited(
            actionItemId: original.id,
            titleChanged: descriptionChanged,
            dateChanged: dueDateChanged,
          );
        }

        _showSnackBar('Action item updated successfully', Colors.green);
      } else {
        // Create new action item
        final createdItem = await provider.createActionItem(
          description: description,
          conversationId: widget.conversationId,
          completed: _isCompleted,
          dueAt: _dueDate,
        );

        if (createdItem != null) {
          // Track manually added action item
          MixpanelManager().actionItemManuallyAdded(
            actionItemId: createdItem.id,
            timestamp: DateTime.now(),
          );
        }

        _showSnackBar('Action item created successfully', Colors.green);
      }

      if (mounted) {
        Navigator.of(context).pop(true);
      }
    } catch (e) {
      Logger.debug('Error saving action item: $e');
      _showSnackBar(
        _isEditing ? 'Failed to update action item' : 'Failed to create action item',
        Colors.red,
      );
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _deleteActionItem() async {
    if (!_isEditing) return;

    final prefs = SharedPreferencesUtil();

    // Check if user has opted out of delete confirmations
    if (!prefs.showActionItemDeleteConfirmation) {
      // Skip confirmation and proceed with deletion
      setState(() {
        _isLoading = true;
      });

      try {
        final provider = Provider.of<ActionItemsProvider>(context, listen: false);
        await provider.deleteActionItem(widget.actionItem!);
        _showSnackBar('Action item deleted successfully', Colors.green);

        if (mounted) {
          Navigator.of(context).pop(true);
        }
      } catch (e) {
        Logger.debug('Error deleting action item: $e');
        _showSnackBar('Failed to delete action item', Colors.red);
        setState(() {
          _isLoading = false;
        });
      }
      return;
    }

    final result = await OmiConfirmDialog.showWithSkipOption(
      context,
      title: 'Delete Action Item',
      message: 'Are you sure you want to delete this action item? This action cannot be undone.',
    );

    if (result?.confirmed != true) return;

    // Update preference if user chose to skip future confirmations
    if (result!.skipFutureConfirmations) {
      prefs.showActionItemDeleteConfirmation = false;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      await provider.deleteActionItem(widget.actionItem!);
      _showSnackBar('Action item deleted successfully', Colors.green);

      if (mounted) {
        Navigator.of(context).pop(true);
      }
    } catch (e) {
      Logger.debug('Error deleting action item: $e');
      _showSnackBar('Failed to delete action item', Colors.red);
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 500,
        constraints: const BoxConstraints(maxHeight: 600),
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
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildHeader(),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _buildDescriptionField(),
                    const SizedBox(height: 20),
                    _buildCompletionToggle(),
                    const SizedBox(height: 20),
                    _buildDueDateSection(),
                  ],
                ),
              ),
            ),
            _buildActionButtons(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          Icon(
            _isEditing ? FontAwesomeIcons.penToSquare : FontAwesomeIcons.plus,
            color: ResponsiveHelper.purplePrimary,
            size: 18,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              _isEditing ? 'Edit Action Item' : 'Create Action Item',
              style: const TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          OmiIconButton(
            icon: FontAwesomeIcons.xmark,
            onPressed: () => Navigator.of(context).pop(),
            style: OmiIconButtonStyle.outline,
            size: 32,
          ),
        ],
      ),
    );
  }

  Widget _buildDescriptionField() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Description',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: _descriptionController,
          focusNode: _descriptionFocusNode,
          maxLines: 3,
          minLines: 1,
          style: const TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 16,
          ),
          decoration: InputDecoration(
            hintText: 'Enter action item description...',
            hintStyle: TextStyle(
              color: ResponsiveHelper.textTertiary,
              fontSize: 16,
            ),
            filled: true,
            fillColor: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide.none,
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(
                color: ResponsiveHelper.purplePrimary,
                width: 2,
              ),
            ),
            contentPadding: const EdgeInsets.all(16),
          ),
          onChanged: (_) => setState(() {}),
        ),
      ],
    );
  }

  Widget _buildCompletionToggle() {
    return Row(
      children: [
        OmiCheckbox(
          value: _isCompleted,
          onChanged: (value) {
            setState(() {
              _isCompleted = value;
            });
          },
          size: 20,
        ),
        const SizedBox(width: 12),
        const Text(
          'Mark as completed',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 16,
          ),
        ),
      ],
    );
  }

  Widget _buildDueDateSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Due Date',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 8),
        GestureDetector(
          onTap: _openDateTimePicker,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                width: 1,
              ),
            ),
            child: Row(
              children: [
                Icon(
                  FontAwesomeIcons.calendar,
                  color: _dueDate != null ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                  size: 16,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    _dueDate != null ? _formatDueDateWithTime(_dueDate!) : 'Set due date and time',
                    style: TextStyle(
                      color: _dueDate != null ? ResponsiveHelper.textPrimary : ResponsiveHelper.textTertiary,
                      fontSize: 16,
                    ),
                  ),
                ),
                if (_dueDate != null)
                  GestureDetector(
                    onTap: _clearDueDate,
                    child: Container(
                      padding: const EdgeInsets.all(4),
                      child: const Icon(
                        FontAwesomeIcons.xmark,
                        color: ResponsiveHelper.textTertiary,
                        size: 14,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildActionButtons() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          if (_isEditing)
            Expanded(
              child: OmiButton(
                label: 'Delete',
                onPressed: _isLoading ? null : _deleteActionItem,
                type: OmiButtonType.text,
                color: Colors.red,
                icon: FontAwesomeIcons.trash,
              ),
            ),
          if (_isEditing) const SizedBox(width: 12),
          Expanded(
            child: OmiButton(
              label: 'Cancel',
              onPressed: _isLoading ? null : () => Navigator.of(context).pop(),
              type: OmiButtonType.text,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: OmiButton(
              label: _isEditing ? 'Update' : 'Create',
              onPressed: _canSave && !_isLoading ? _saveActionItem : null,
              icon: _isEditing ? FontAwesomeIcons.check : FontAwesomeIcons.plus,
            ),
          ),
        ],
      ),
    );
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

    return Material(
      child: Container(
        height: MediaQuery.of(context).size.height * 0.65,
        decoration: const BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: Column(
          children: [
            Container(
              width: 40,
              height: 4,
              margin: const EdgeInsets.only(top: 12, bottom: 20),
              decoration: BoxDecoration(
                color: ResponsiveHelper.textTertiary,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
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
                  const Text(
                    'Set Due Date',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: ResponsiveHelper.textPrimary,
                    ),
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
            SizedBox(height: MediaQuery.of(context).padding.bottom + 10),
          ],
        ),
      ),
    );
  }
}
