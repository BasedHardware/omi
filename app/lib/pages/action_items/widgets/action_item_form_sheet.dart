import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';
import 'package:omi/utils/share_sheet.dart';

class ActionItemFormSheet extends StatefulWidget {
  final ActionItemWithMetadata? actionItem; // null for create, non-null for edit
  final VoidCallback? onRefresh;
  final DateTime? defaultDueDate; // Default due date for new items

  const ActionItemFormSheet({super.key, this.actionItem, this.onRefresh, this.defaultDueDate});

  bool get isEditing => actionItem != null;

  @override
  State<ActionItemFormSheet> createState() => _ActionItemFormSheetState();
}

class _ActionItemFormSheetState extends State<ActionItemFormSheet> {
  late TextEditingController _textController;
  late bool _isCompleted;
  DateTime? _selectedDueDate;
  bool _isSaving = false;
  bool _saveFailed = false;

  @override
  void initState() {
    super.initState();
    if (widget.isEditing) {
      _textController = TextEditingController(text: widget.actionItem!.description);
      _textController.selection = TextSelection.fromPosition(TextPosition(offset: _textController.text.length));
      _isCompleted = widget.actionItem!.completed;
      _selectedDueDate = widget.actionItem!.dueAt;
    } else {
      _textController = TextEditingController();
      _isCompleted = false;
      _selectedDueDate = widget.defaultDueDate;
    }
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  Future<void> _saveActionItem() async {
    if (_isSaving || _textController.text.trim().isEmpty) return;
    final provider = context.read<ActionItemsProvider>();
    final messenger = ScaffoldMessenger.of(context);
    final l10n = context.l10n;
    setState(() {
      _isSaving = true;
      _saveFailed = false;
    });
    var saved = false;
    try {
      if (widget.isEditing) {
        final item = widget.actionItem!;
        final descriptionChanged = _textController.text.trim() != item.description;
        final dateChanged = _selectedDueDate != item.dueAt;
        final completionChanged = _isCompleted != item.completed;
        saved = true;
        if (descriptionChanged) {
          saved = await provider.updateActionItemDescription(item, _textController.text.trim()) && saved;
        }
        if (dateChanged) {
          saved = await provider.updateActionItemDueDate(item, _selectedDueDate) && saved;
        }
        if (completionChanged) {
          saved = await provider.updateActionItemState(item, _isCompleted) && saved;
        }
        if (saved && (descriptionChanged || dateChanged)) {
          PlatformManager.instance.analytics.actionItemEdited(
            actionItemId: item.id,
            titleChanged: descriptionChanged,
            dateChanged: dateChanged,
          );
        }
      } else {
        final item = await provider.createActionItem(
          description: _textController.text.trim(),
          dueAt: _selectedDueDate,
          completed: _isCompleted,
        );
        saved = item != null;
        if (item != null) {
          PlatformManager.instance.analytics.actionItemManuallyAdded(actionItemId: item.id, timestamp: DateTime.now());
        }
      }
    } catch (_) {
      saved = false;
    }
    if (!mounted) return;
    setState(() {
      _isSaving = false;
      _saveFailed = !saved;
    });
    if (saved) {
      HapticFeedback.lightImpact();
      Navigator.pop(context);
      widget.onRefresh?.call();
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(SnackBar(
        content: Text(widget.isEditing ? l10n.actionItemUpdated : l10n.actionItemCreated),
      ));
    }
  }

  void _selectQuickDate(int days) {
    final now = DateTime.now();
    final date = DateTime(now.year, now.month, now.day + days, 18);
    HapticFeedback.selectionClick();
    setState(() => _selectedDueDate = date.isBefore(now) ? DateTime(now.year, now.month, now.day, 23, 59, 59) : date);
  }

  void _deleteActionItem() async {
    if (!widget.isEditing) return;

    Navigator.pop(context);

    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final success = await provider.deleteActionItem(widget.actionItem!);

    if (mounted) {
      if (success) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(context.l10n.actionItemDeleted),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 2),
          ),
        );
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(context.l10n.failedToDeleteActionItem), backgroundColor: Colors.red));
      }
    }
  }

  void _shareActionItem() async {
    if (!widget.isEditing) return;

    final result = await action_items_api.shareActionItems([widget.actionItem!.id]);

    if (!mounted) return;

    if (result != null && result['url'] != null) {
      final url = result['url'] as String;
      HapticFeedback.lightImpact();
      await Share.share(url, sharePositionOrigin: shareSheetOrigin());
      PlatformManager.instance.analytics.track(
        'Action Item Shared',
        properties: {'actionItemId': widget.actionItem!.id},
      );
    } else {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(context.l10n.failedToCreateShareLink), backgroundColor: Colors.red));
    }
  }

  Future<void> _openDateTimePicker() async {
    final DateTime? result = await showCupertinoModalPopup<DateTime>(
      context: context,
      builder: (context) => DateTimePickerSheet(
        initialDateTime: _selectedDueDate,
        minimumDate: widget.isEditing ? widget.actionItem!.createdAt : DateTime.now(),
      ),
    );

    if (result != null && mounted) {
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
    final locale = Localizations.localeOf(context).toString();
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final tomorrow = today.add(const Duration(days: 1));
    final dateOnly = DateTime(date.year, date.month, date.day);
    final timeStr = DateFormat.jm(locale).format(date);

    String dateStr;
    if (dateOnly == today) {
      dateStr = context.l10n.today;
    } else if (dateOnly == tomorrow) {
      dateStr = context.l10n.tomorrow;
    } else {
      // Show short form: "Sat, Jan 31" or "Sat, Jan 31, 2027" if different year
      if (date.year == now.year) {
        dateStr = DateFormat.E(locale).format(date) + ', ' + DateFormat.MMMd(locale).format(date);
      } else {
        dateStr = DateFormat.E(locale).format(date) + ', ' + DateFormat.yMMMd(locale).format(date);
      }
    }

    return '$dateStr - $timeStr';
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        decoration: const BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        child: SingleChildScrollView(
            child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                if (!widget.isEditing)
                  Expanded(
                      child: Text(context.l10n.newTask,
                          style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600)))
                else
                  // Stage completion along with the other edits.
                  Row(
                    children: [
                      SizedBox(
                        height: 24,
                        width: 24,
                        child: Checkbox(
                          value: _isCompleted,
                          activeColor: Colors.white,
                          checkColor: Colors.black,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
                          onChanged: _isSaving
                              ? null
                              : (bool? value) {
                                  if (value == null) return;

                                  HapticFeedback.lightImpact();

                                  setState(() {
                                    _isCompleted = value;
                                  });
                                },
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        _isCompleted ? context.l10n.completed : context.l10n.markComplete,
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 14),
                      ),
                    ],
                  ),
                if (!widget.isEditing)
                  IconButton(
                      tooltip: context.l10n.close,
                      onPressed: _isSaving ? null : () => Navigator.pop(context),
                      icon: const Icon(Icons.close, color: Colors.white70)),
                // Share + Delete buttons (only for edit mode)
                if (widget.isEditing)
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: FaIcon(FontAwesomeIcons.share, color: Colors.grey.shade400, size: 16),
                        onPressed: _isSaving ? null : _shareActionItem,
                        tooltip: context.l10n.share,
                      ),
                      IconButton(
                        icon: const Icon(Icons.delete_outline, color: Colors.red),
                        tooltip: context.l10n.delete,
                        onPressed: _isSaving
                            ? null
                            : () {
                                // Show delete confirmation dialog
                                showDialog(
                                  context: context,
                                  builder: (context) => AlertDialog(
                                    backgroundColor: ResponsiveHelper.backgroundSecondary,
                                    title: Text(
                                      context.l10n.deleteActionItemConfirmTitle,
                                      style: const TextStyle(color: Colors.white),
                                    ),
                                    content: Text(
                                      context.l10n.deleteActionItemConfirmMessage,
                                      style: TextStyle(color: Colors.grey.shade300),
                                    ),
                                    actions: [
                                      TextButton(
                                        onPressed: () => Navigator.pop(context, false),
                                        child: Text(context.l10n.cancel, style: TextStyle(color: Colors.grey.shade400)),
                                      ),
                                      TextButton(
                                        onPressed: () {
                                          Navigator.pop(context, true); // Close dialog
                                          _deleteActionItem();
                                        },
                                        child: Text(context.l10n.delete, style: const TextStyle(color: Colors.red)),
                                      ),
                                    ],
                                  ),
                                );
                              },
                      ),
                    ],
                  ),
              ],
            ),
            const SizedBox(height: 12),
            // Text field for editing/creating the action item
            TextField(
              key: const Key('task_description'),
              controller: _textController,
              enabled: !_isSaving,
              onChanged: (_) => setState(() {}),
              autofocus: true,
              maxLines: 5,
              minLines: 2,
              maxLength: 4096,
              textInputAction: TextInputAction.done,
              style: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
              decoration: InputDecoration(
                counterText: '',
                border: InputBorder.none,
                contentPadding: EdgeInsets.zero,
                isDense: true,
                hintText: widget.isEditing ? null : context.l10n.actionItemDescriptionHint,
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
            InkWell(
              onTap: _isSaving ? null : _openDateTimePicker,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Row(
                  children: [
                    Icon(Icons.schedule_outlined, size: 20, color: Colors.grey.shade400),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Text(
                        _selectedDueDate != null ? _formatDueDateWithTime(_selectedDueDate!) : context.l10n.addDueDate,
                        style: TextStyle(
                          color: _selectedDueDate != null ? Colors.white : Colors.grey.shade500,
                          fontSize: 16,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ),
                    if (_selectedDueDate != null)
                      IconButton(
                        tooltip: context.l10n.clearDueDate,
                        onPressed: _isSaving ? null : _clearDueDate,
                        icon: const Icon(Icons.close, size: 18, color: Colors.white70),
                      ),
                  ],
                ),
              ),
            ),
            Wrap(spacing: 8, children: [
              for (final days in [0, 1, 7])
                ActionChip(
                  key: ValueKey('task_quick_date_$days'),
                  label: Text(days == 0
                      ? context.l10n.today
                      : days == 1
                          ? context.l10n.tomorrow
                          : context.l10n.nextWeek),
                  onPressed: _isSaving ? null : () => _selectQuickDate(days),
                  backgroundColor: Colors.white.withValues(alpha: 0.06),
                  labelStyle: const TextStyle(color: Colors.white),
                  side: const BorderSide(color: Colors.white24),
                ),
            ]),
            Align(
                alignment: Alignment.centerRight,
                child: Text(
                  '${_textController.text.characters.length}/4096',
                  key: const Key('task_character_count'),
                  style: const TextStyle(color: Colors.white54, fontSize: 12),
                )),
            const SizedBox(height: 12),
            if (_saveFailed) ...[
              Semantics(
                  liveRegion: true,
                  child: Text(
                    widget.isEditing ? context.l10n.failedToUpdateActionItem : context.l10n.failedToCreateActionItem,
                    style: const TextStyle(color: Colors.redAccent),
                  )),
              const SizedBox(height: 12),
            ],
            SizedBox(
                width: double.infinity,
                child: FilledButton(
                  key: const Key('task_save_button'),
                  onPressed: _isSaving || _textController.text.trim().isEmpty ? null : _saveActionItem,
                  style: FilledButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      minimumSize: const Size.fromHeight(48),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
                  child: _isSaving
                      ? const SizedBox(
                          width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black))
                      : Text(_saveFailed
                          ? context.l10n.retry
                          : widget.isEditing
                              ? context.l10n.saveChanges
                              : context.l10n.addTask),
                )),
            SizedBox(height: MediaQuery.paddingOf(context).bottom),
          ],
        )),
      ),
    );
  }
}

class DateTimePickerSheet extends StatefulWidget {
  final DateTime? initialDateTime;
  final DateTime? minimumDate;

  const DateTimePickerSheet({super.key, this.initialDateTime, this.minimumDate});

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
            fontWeight: isSelected == true ? FontWeight.bold : FontWeight.normal,
            color: isDisabled == true ? ResponsiveHelper.textQuaternary : ResponsiveHelper.textPrimary,
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
      _selectedDateTime = widget.initialDateTime!.isBefore(minimumDate) ? minimumDate : widget.initialDateTime!;
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
              decoration: BoxDecoration(color: ResponsiveHelper.textTertiary, borderRadius: BorderRadius.circular(2)),
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
                    child: Text(
                      context.l10n.cancel,
                      style: const TextStyle(color: ResponsiveHelper.textTertiary, fontSize: 17),
                    ),
                  ),
                  Text(
                    DateFormat.yMMMd(Localizations.localeOf(context).toString()).format(_selectedDateTime),
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: ResponsiveHelper.textPrimary,
                    ),
                  ),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () => Navigator.pop(context, _selectedDateTime),
                    child: Text(
                      context.l10n.done,
                      style: const TextStyle(
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
                    config: getDefaultCalendarConfig(
                      firstDate: now,
                      currentDate: now,
                      lastDate: (widget.initialDateTime ?? now).add(const Duration(days: 365 * 5)),
                      yearBuilder: yearBuilder,
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
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                    child: Row(
                      children: [
                        const Icon(Icons.access_time, color: ResponsiveHelper.purplePrimary, size: 20),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            context.l10n.time,
                            style: const TextStyle(
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
                                      surface: ResponsiveHelper.backgroundSecondary,
                                      onSurface: ResponsiveHelper.textPrimary,
                                    ),
                                    timePickerTheme: TimePickerThemeData(
                                      backgroundColor: ResponsiveHelper.backgroundSecondary,
                                      hourMinuteColor: WidgetStateColor.resolveWith(
                                        (states) => states.contains(WidgetState.selected)
                                            ? ResponsiveHelper.purplePrimary
                                            : ResponsiveHelper.backgroundTertiary,
                                      ),
                                      hourMinuteTextColor: ResponsiveHelper.textPrimary,
                                      dialHandColor: ResponsiveHelper.purplePrimary,
                                      dialBackgroundColor: ResponsiveHelper.backgroundTertiary,
                                      dialTextColor: WidgetStateColor.resolveWith(
                                        (states) => states.contains(WidgetState.selected)
                                            ? ResponsiveHelper.textPrimary
                                            : ResponsiveHelper.textSecondary,
                                      ),
                                      entryModeIconColor: ResponsiveHelper.textTertiary,
                                      dayPeriodColor: WidgetStateColor.resolveWith(
                                        (states) => states.contains(WidgetState.selected)
                                            ? ResponsiveHelper.purplePrimary
                                            : Colors.transparent,
                                      ),
                                      dayPeriodTextColor: WidgetStateColor.resolveWith(
                                        (states) => states.contains(WidgetState.selected)
                                            ? ResponsiveHelper.textPrimary
                                            : ResponsiveHelper.textTertiary,
                                      ),
                                      dayPeriodBorderSide: const BorderSide(color: ResponsiveHelper.textTertiary),
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
