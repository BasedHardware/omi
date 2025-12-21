import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

class ActionItemFormSheet extends StatefulWidget {
  final ActionItemWithMetadata?
  actionItem; // null for create, non-null for edit
  final VoidCallback? onRefresh;

  const ActionItemFormSheet({super.key, this.actionItem, this.onRefresh});

  bool get isEditing => actionItem != null;

  @override
  State<ActionItemFormSheet> createState() => _ActionItemFormSheetState();
}

class _ActionItemFormSheetState extends State<ActionItemFormSheet> {
  late TextEditingController _textController;
  late bool _isCompleted;
  DateTime? _selectedDueDate;

  @override
  void initState() {
    super.initState();
    if (widget.isEditing) {
      _textController = TextEditingController(
        text: widget.actionItem!.description,
      );
      _textController.selection = TextSelection.fromPosition(
        TextPosition(offset: _textController.text.length),
      );
      _isCompleted = widget.actionItem!.completed;
      _selectedDueDate = widget.actionItem!.dueAt;
    } else {
      _textController = TextEditingController();
      _isCompleted = false;
      _selectedDueDate = null;
    }
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  void _saveActionItem() async {
    if (_textController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Action item description cannot be empty.'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    final provider = Provider.of<ActionItemsProvider>(context, listen: false);

    Navigator.pop(context);

    if (widget.isEditing) {
      // Editing existing item
      String newDescription = _textController.text.trim();
      bool descriptionChanged =
          newDescription != widget.actionItem!.description;
      bool dueDateChanged = _selectedDueDate != widget.actionItem!.dueAt;
      bool completionChanged = _isCompleted != widget.actionItem!.completed;

      if (!descriptionChanged && !dueDateChanged && !completionChanged) {
        return;
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Action item updated'),
            backgroundColor: Colors.green,
            duration: Duration(seconds: 2),
          ),
        );
      }

      try {
        if (descriptionChanged) {
          await provider.updateActionItemDescription(
            widget.actionItem!,
            newDescription,
          );
        }

        if (dueDateChanged) {
          await provider.updateActionItemDueDate(
            widget.actionItem!,
            _selectedDueDate,
          );
        }

        if (completionChanged) {
          await provider.updateActionItemState(
            widget.actionItem!,
            _isCompleted,
          );
        }

        // Track action item edit
        if (descriptionChanged || dueDateChanged) {
          MixpanelManager().actionItemEdited(
            actionItemId: widget.actionItem!.id,
            titleChanged: descriptionChanged,
            dateChanged: dueDateChanged,
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Failed to update action item'),
              backgroundColor: Colors.red,
              duration: Duration(seconds: 3),
            ),
          );
        }
      }
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Action item created'),
            backgroundColor: Colors.green,
            duration: Duration(seconds: 2),
          ),
        );
      }

      try {
        final createdItem = await provider.createActionItem(
          description: _textController.text.trim(),
          dueAt: _selectedDueDate,
          completed: _isCompleted,
        );

        if (createdItem != null) {
          // Track manually added action item
          MixpanelManager().actionItemManuallyAdded(
            actionItemId: createdItem.id,
            timestamp: DateTime.now(),
          );
        } else if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Failed to create action item'),
              backgroundColor: Colors.red,
              duration: Duration(seconds: 3),
            ),
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Failed to create action item'),
              backgroundColor: Colors.red,
              duration: Duration(seconds: 3),
            ),
          );
        }
      }
    }
  }

  void _deleteActionItem() async {
    if (!widget.isEditing) return;

    Navigator.pop(context);

    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final success = await provider.deleteActionItem(widget.actionItem!);

    if (mounted) {
      if (success) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Action item deleted'),
            backgroundColor: Colors.green,
            duration: Duration(seconds: 2),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to delete action item'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _openDateTimePicker() async {
    final DateTime? result = await showCupertinoModalPopup<DateTime>(
      context: context,
      builder: (context) => DateTimePickerSheet(
        initialDateTime: _selectedDueDate,
        minimumDate: widget.isEditing
            ? widget.actionItem!.createdAt
            : DateTime.now(),
      ),
    );

    if (result != null) {
      setState(() {
        _selectedDueDate = result;
      });
    }
  }

  void _clearDueDate() {
    setState(() {
      _selectedDueDate = null;
    });
  }

  String _formatDueDateWithTime(DateTime date) {
    final weekdays = [
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ];
    final months = [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];

    // Format date as "Wednesday, June 25"
    final dayName = weekdays[date.weekday - 1];
    final monthName = months[date.month - 1];

    // Format time as "8:12am"
    final hour = date.hour;
    final minute = date.minute.toString().padLeft(2, '0');
    final period = hour >= 12 ? 'pm' : 'am';
    final displayHour = hour == 0 ? 12 : (hour > 12 ? hour - 12 : hour);

    int? year;
    if (date.year != DateTime.now().year) {
      year = date.year;
    }

    return '$dayName, $monthName ${date.day} ${year ?? ""} - $displayHour:$minute$period';
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        decoration: const BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
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
                        onChanged: (bool? value) async {
                          if (value == null) return;

                          HapticFeedback.lightImpact();

                          setState(() {
                            _isCompleted = value;
                          });

                          // Only update immediately if editing
                          if (widget.isEditing) {
                            final provider = Provider.of<ActionItemsProvider>(
                              context,
                              listen: false,
                            );
                            await provider.updateActionItemState(
                              widget.actionItem!,
                              value,
                            );
                          }
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
                // Delete button (only for edit mode)
                if (widget.isEditing)
                  IconButton(
                    icon: const Icon(Icons.delete_outline, color: Colors.red),
                    onPressed: () {
                      // Show delete confirmation dialog
                      showDialog(
                        context: context,
                        builder: (context) => AlertDialog(
                          backgroundColor: ResponsiveHelper.backgroundSecondary,
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
                                _deleteActionItem();
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
            // Text field for editing/creating the action item
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
              decoration: InputDecoration(
                border: InputBorder.none,
                contentPadding: EdgeInsets.zero,
                isDense: true,
                hintText: widget.isEditing ? null : 'What needs to be done?',
                hintStyle: TextStyle(color: Colors.grey[500], fontSize: 16),
              ),
              onSubmitted: (value) {
                FocusScope.of(context).unfocus();
                if (value.trim().isNotEmpty) {
                  _saveActionItem();
                }
              },
            ),
            const SizedBox(height: 20),
            GestureDetector(
              onTap: _openDateTimePicker,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Row(
                  children: [
                    Icon(
                      Icons.schedule_outlined,
                      size: 20,
                      color: Colors.grey.shade400,
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Text(
                        _selectedDueDate != null
                            ? _formatDueDateWithTime(_selectedDueDate!)
                            : 'Add due date',
                        style: TextStyle(
                          color: _selectedDueDate != null
                              ? Colors.white
                              : Colors.grey.shade500,
                          fontSize: 16,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ),
                    if (_selectedDueDate != null)
                      GestureDetector(
                        onTap: () {
                          _clearDueDate();
                        },
                        child: Padding(
                          padding: const EdgeInsets.all(4),
                          child: Icon(
                            Icons.close,
                            size: 18,
                            color: Colors.grey.shade500,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 18),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 4,
                  ),
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
                        'Press done to ${widget.isEditing ? 'save' : 'create'}',
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
                  style: TextStyle(color: Colors.grey.shade500, fontSize: 11),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class DateTimePickerSheet extends StatefulWidget {
  final DateTime? initialDateTime;
  final DateTime? minimumDate;

  const DateTimePickerSheet({
    super.key,
    this.initialDateTime,
    this.minimumDate,
  });

  @override
  State<DateTimePickerSheet> createState() => _DateTimePickerSheetState();
}

class _DateTimePickerSheetState extends State<DateTimePickerSheet> {
  late DateTime _selectedDateTime;
  late TimeOfDay _selectedTimeOfDay;

  Widget yearBuilder({
    required int year,
    TextStyle? textStyle,
    BoxDecoration? decoration,
    bool? isSelected,
    bool? isDisabled,
    bool? isCurrentYear,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: isSelected == true
            ? ResponsiveHelper.purplePrimary
            : isCurrentYear == true
            ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.3)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Center(
        child: Text(
          year.toString(),
          style: TextStyle(
            fontSize: 14,
            fontWeight: isSelected == true
                ? FontWeight.bold
                : FontWeight.normal,
            color: isDisabled == true
                ? ResponsiveHelper.textQuaternary
                : ResponsiveHelper.textPrimary,
          ),
        ),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    final minimumDate = widget.minimumDate ?? now;

    if (widget.initialDateTime != null) {
      _selectedDateTime = widget.initialDateTime!.isBefore(minimumDate)
          ? minimumDate
          : widget.initialDateTime!;
    } else {
      _selectedDateTime = now.isBefore(minimumDate) ? minimumDate : now;
    }
    _selectedTimeOfDay = TimeOfDay.fromDateTime(_selectedDateTime);
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();

    return Material(
      color: Colors.transparent,
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

            // Header
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
                        color: ResponsiveHelper.textTertiary,
                        fontSize: 17,
                      ),
                    ),
                  ),
                  Text(
                    DateFormat.yMMMd(
                      Localizations.localeOf(context).toString(),
                    ).format(_selectedDateTime),
                    style: const TextStyle(
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
            const SizedBox(height: 20),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.start,
                children: [
                  CalendarDatePicker2(
                    config: CalendarDatePicker2Config(
                      calendarType: CalendarDatePicker2Type.single,
                      firstDate: now,
                      currentDate: now,
                      lastDate: (widget.initialDateTime ?? now).add(
                        const Duration(days: 365 * 5),
                      ),
                      disableMonthPicker: true,
                      yearBuilder: yearBuilder,
                      selectedDayHighlightColor: ResponsiveHelper.purplePrimary,
                      // todayHighlightColor: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                      dayTextStyle: const TextStyle(
                        color: ResponsiveHelper.textPrimary,
                      ),
                      selectedDayTextStyle: const TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontWeight: FontWeight.bold,
                      ),
                      todayTextStyle: const TextStyle(
                        color: ResponsiveHelper.purplePrimary,
                        fontWeight: FontWeight.bold,
                      ),
                      weekdayLabelTextStyle: const TextStyle(
                        color: ResponsiveHelper.textTertiary,
                        fontWeight: FontWeight.w500,
                      ),
                      controlsTextStyle: const TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                      disabledDayTextStyle: const TextStyle(
                        color: ResponsiveHelper.textQuaternary,
                      ),
                    ),
                    value: [_selectedDateTime],
                    onValueChanged: (dates) => setState(() {
                      _selectedDateTime = DateTime(
                        dates[0].year,
                        dates[0].month,
                        dates[0].day,
                        _selectedDateTime.hour,
                        _selectedDateTime.minute,
                      );
                    }),
                  ),
                  Container(
                    margin: const EdgeInsets.symmetric(horizontal: 20),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 16,
                    ),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.access_time,
                          color: ResponsiveHelper.purplePrimary,
                          size: 20,
                        ),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Text(
                            "Time",
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w500,
                              color: ResponsiveHelper.textPrimary,
                            ),
                          ),
                        ),
                        GestureDetector(
                          onTap: () async {
                            final TimeOfDay? pickedTime = await showTimePicker(
                              context: context,
                              initialTime: _selectedTimeOfDay,
                              builder: (context, child) {
                                return Theme(
                                  data: Theme.of(context).copyWith(
                                    colorScheme: const ColorScheme.dark(
                                      primary: ResponsiveHelper.purplePrimary,
                                      onPrimary: ResponsiveHelper.textPrimary,
                                      surface:
                                          ResponsiveHelper.backgroundSecondary,
                                      onSurface: ResponsiveHelper.textPrimary,
                                    ),
                                    timePickerTheme: TimePickerThemeData(
                                      backgroundColor:
                                          ResponsiveHelper.backgroundSecondary,
                                      hourMinuteColor:
                                          WidgetStateColor.resolveWith(
                                            (states) =>
                                                states.contains(
                                                  WidgetState.selected,
                                                )
                                                ? ResponsiveHelper.purplePrimary
                                                : ResponsiveHelper
                                                      .backgroundTertiary,
                                          ),
                                      hourMinuteTextColor:
                                          ResponsiveHelper.textPrimary,
                                      dialHandColor:
                                          ResponsiveHelper.purplePrimary,
                                      dialBackgroundColor:
                                          ResponsiveHelper.backgroundTertiary,
                                      dialTextColor:
                                          WidgetStateColor.resolveWith(
                                            (states) =>
                                                states.contains(
                                                  WidgetState.selected,
                                                )
                                                ? ResponsiveHelper.textPrimary
                                                : ResponsiveHelper
                                                      .textSecondary,
                                          ),
                                      entryModeIconColor:
                                          ResponsiveHelper.textTertiary,
                                      dayPeriodColor:
                                          WidgetStateColor.resolveWith(
                                            (states) =>
                                                states.contains(
                                                  WidgetState.selected,
                                                )
                                                ? ResponsiveHelper.purplePrimary
                                                : Colors.transparent,
                                          ),
                                      dayPeriodTextColor:
                                          WidgetStateColor.resolveWith(
                                            (states) =>
                                                states.contains(
                                                  WidgetState.selected,
                                                )
                                                ? ResponsiveHelper.textPrimary
                                                : ResponsiveHelper.textTertiary,
                                          ),
                                      dayPeriodBorderSide: const BorderSide(
                                        color: ResponsiveHelper.textTertiary,
                                      ),
                                    ),
                                  ),
                                  child: child!,
                                );
                              },
                            );

                            if (pickedTime != null) {
                              setState(() {
                                _selectedTimeOfDay = pickedTime;
                                _selectedDateTime = DateTime(
                                  _selectedDateTime.year,
                                  _selectedDateTime.month,
                                  _selectedDateTime.day,
                                  pickedTime.hour,
                                  pickedTime.minute,
                                );
                              });
                            }
                          },
                          child: Row(
                            children: [
                              Text(
                                DateFormat.jm().format(_selectedDateTime),
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w500,
                                  color: ResponsiveHelper.purplePrimary,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
