import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:provider/provider.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/task_delete_undo.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';
import 'package:omi/utils/share_sheet.dart';

/// Opens the task sheet: a new task (optionally due on [defaultDueDate]) or, with [actionItem], that
/// task for editing. The sheet guards unsaved edits (docs/ux-contract.md §2). Use this rather than
/// presenting [ActionItemFormSheet] yourself so swipe-down asks before discarding a draft.
Future<void> showActionItemFormSheet(
  BuildContext context, {
  ActionItemWithMetadata? actionItem,
  DateTime? defaultDueDate,
  VoidCallback? onRefresh,
}) {
  return showOmiEditSheet<void>(
    context: context,
    builder: (_) => ActionItemFormSheet(actionItem: actionItem, defaultDueDate: defaultDueDate, onRefresh: onRefresh),
  );
}

/// Creates or edits one task. Explicit Cancel and Save; completion (edit mode) applies the moment
/// it is ticked, like the list's checkbox. Delete is immediate with an Undo toast.
///
/// Paints its own sheet surface ([OmiEditSheet]), so it also works under a transparent
/// `showModalBottomSheet`; prefer [showActionItemFormSheet].
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
  late final String _initialDescription;
  late final DateTime? _initialDueDate;
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
    _initialDescription = _textController.text;
    _initialDueDate = _selectedDueDate;
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  /// Unsaved text or date. Completion is not part of it: it saves the moment it is ticked.
  bool get _isDirty => _textController.text.trim() != _initialDescription.trim() || _selectedDueDate != _initialDueDate;

  Future<void> _saveActionItem() async {
    if (_isSaving || _textController.text.trim().isEmpty) return;
    final provider = context.read<ActionItemsProvider>();
    final hostContext = Navigator.of(context).context;
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
        saved = true;
        if (descriptionChanged) {
          saved = await provider.updateActionItemDescription(item, _textController.text.trim()) && saved;
        }
        if (dateChanged) {
          saved = await provider.updateActionItemDueDate(item, _selectedDueDate) && saved;
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
      OmiHaptics.light();
      Navigator.pop(context);
      widget.onRefresh?.call();
      if (hostContext.mounted) {
        OmiFeedback.confirm(hostContext, widget.isEditing ? l10n.actionItemUpdated : l10n.actionItemCreated);
      }
    }
  }

  /// Completion is instant everywhere (the list, Home, here): no Save needed.
  Future<void> _toggleCompleted(bool value) async {
    final item = widget.actionItem;
    if (item == null) return;
    OmiHaptics.light();
    setState(() => _isCompleted = value);
    final ok = await context.read<ActionItemsProvider>().updateActionItemState(item, value);
    if (!mounted) return;
    if (!ok) {
      setState(() => _isCompleted = !value);
      OmiFeedback.error(context, context.l10n.failedToUpdateActionItem);
    } else if (value) {
      PlatformManager.instance.analytics.actionItemCompleted(fromTab: 'Task Sheet');
    }
  }

  void _selectQuickDate(int days) {
    final now = DateTime.now();
    final date = DateTime(now.year, now.month, now.day + days, 18);
    OmiHaptics.selection();
    setState(() => _selectedDueDate = date.isBefore(now) ? DateTime(now.year, now.month, now.day, 23, 59, 59) : date);
  }

  void _deleteActionItem() {
    if (!widget.isEditing) return;
    final provider = context.read<ActionItemsProvider>();
    unawaited(deleteTaskWithUndo(context, provider, widget.actionItem!));
    Navigator.pop(context);
  }

  Future<void> _shareActionItem() async {
    if (!widget.isEditing) return;

    final result = await action_items_api.shareActionItems([widget.actionItem!.id]);

    if (!mounted) return;

    if (result != null && result['url'] != null) {
      final url = result['url'] as String;
      OmiHaptics.light();
      await Share.share(url, sharePositionOrigin: shareSheetOrigin());
      PlatformManager.instance.analytics.track(
        'Action Item Shared',
        properties: {'actionItemId': widget.actionItem!.id},
      );
    } else {
      OmiFeedback.error(context, context.l10n.failedToCreateShareLink);
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
    final dates = OmiDateFormat.of(context);
    final now = DateTime.now();
    final tomorrow = DateTime(now.year, now.month, now.day + 1);
    final day = DateTime(date.year, date.month, date.day) == tomorrow ? context.l10n.tomorrow : dates.dayHeader(date);
    return '$day · ${dates.time(date)}';
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return OmiEditSheet(
      title: widget.isEditing ? l10n.editActionItem : l10n.newTask,
      isDirty: _isDirty,
      enabled: !_isSaving,
      actions: [
        if (widget.isEditing) ...[
          OmiIconButton(
            icon: const FaIcon(FontAwesomeIcons.share, size: 16),
            label: l10n.share,
            color: OmiColors.textSecondary,
            onPressed: _isSaving ? null : _shareActionItem,
          ),
          OmiIconButton(
            icon: const Icon(Icons.delete_outline),
            label: l10n.deleteActionItem,
            isDestructive: true,
            onPressed: _isSaving ? null : _deleteActionItem,
          ),
        ],
      ],
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.isEditing)
              OmiCheckboxRow(
                key: const Key('task_completed_toggle'),
                label: _isCompleted ? l10n.completed : l10n.markComplete,
                value: _isCompleted,
                onChanged: (value) => _toggleCompleted(value),
              ),
            const SizedBox(height: OmiSpacing.xs),
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
              style: OmiType.callout.copyWith(height: 1.4),
              cursorColor: OmiColors.accent,
              decoration: InputDecoration(
                counterText: '',
                border: InputBorder.none,
                contentPadding: EdgeInsets.zero,
                isDense: true,
                hintText: widget.isEditing ? null : l10n.actionItemDescriptionHint,
                hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary),
              ),
              onSubmitted: (value) {
                FocusScope.of(context).unfocus();
                if (value.trim().isNotEmpty) {
                  _saveActionItem();
                }
              },
            ),
            const SizedBox(height: OmiSpacing.md),
            InkWell(
              onTap: _isSaving ? null : _openDateTimePicker,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
                child: Row(
                  children: [
                    const Icon(Icons.schedule_outlined, size: 20, color: OmiColors.textSecondary),
                    const SizedBox(width: OmiSpacing.md),
                    Expanded(
                      child: Text(
                        _selectedDueDate != null ? _formatDueDateWithTime(_selectedDueDate!) : l10n.addDueDate,
                        style: OmiType.callout.copyWith(
                          color: _selectedDueDate != null ? OmiColors.textPrimary : OmiColors.textTertiary,
                        ),
                      ),
                    ),
                    if (_selectedDueDate != null)
                      OmiIconButton(
                        icon: const Icon(Icons.close, size: 18),
                        label: l10n.clearDueDate,
                        color: OmiColors.textSecondary,
                        onPressed: _isSaving ? null : _clearDueDate,
                      ),
                  ],
                ),
              ),
            ),
            Wrap(spacing: OmiSpacing.xs, children: [
              for (final days in [0, 1, 7])
                ActionChip(
                  key: ValueKey('task_quick_date_$days'),
                  label: Text(days == 0
                      ? l10n.today
                      : days == 1
                          ? l10n.tomorrow
                          : l10n.nextWeek),
                  onPressed: _isSaving ? null : () => _selectQuickDate(days),
                  backgroundColor: OmiColors.surface2,
                  labelStyle: OmiType.footnote,
                  side: const BorderSide(color: OmiColors.border),
                ),
            ]),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: Text(
                '${_textController.text.characters.length}/4096',
                key: const Key('task_character_count'),
                style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
              ),
            ),
            const SizedBox(height: OmiSpacing.sm),
            if (_saveFailed) ...[
              Semantics(
                liveRegion: true,
                child: Text(
                  widget.isEditing ? l10n.failedToUpdateActionItem : l10n.failedToCreateActionItem,
                  style: OmiType.footnote.copyWith(color: OmiColors.danger),
                ),
              ),
              const SizedBox(height: OmiSpacing.sm),
            ],
            Row(
              children: [
                Expanded(
                  child: OmiButton.secondary(
                    label: l10n.cancel,
                    expand: true,
                    onPressed: _isSaving ? null : () => Navigator.pop(context),
                  ),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: OmiButton(
                    key: const Key('task_save_button'),
                    expand: true,
                    isLoading: _isSaving,
                    onPressed: _textController.text.trim().isEmpty ? null : _saveActionItem,
                    label: _saveFailed
                        ? l10n.tryAgain
                        : widget.isEditing
                            ? l10n.save
                            : l10n.addTask,
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

/// Date and time picker for a task's due date (Cancel / Done). Returns the chosen moment.
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
            ? OmiColors.accent
            : isCurrentYear == true
                ? OmiColors.surface3
                : Colors.transparent,
        borderRadius: OmiRadius.smAll,
      ),
      child: Center(
        child: Text(
          year.toString(),
          style: OmiType.subhead.copyWith(
            fontWeight: isSelected == true ? FontWeight.w600 : FontWeight.w400,
            color: isSelected == true
                ? OmiColors.onAccent
                : isDisabled == true
                    ? OmiColors.textDisabled
                    : OmiColors.textPrimary,
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

  Future<void> _pickTime() async {
    final TimeOfDay? pickedTime = await showTimePicker(
      context: context,
      initialTime: _selectedTimeOfDay,
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.dark(
              primary: OmiColors.accent,
              onPrimary: OmiColors.onAccent,
              surface: OmiColors.surface1,
              onSurface: OmiColors.textPrimary,
            ),
            timePickerTheme: TimePickerThemeData(
              backgroundColor: OmiColors.surface1,
              hourMinuteColor: WidgetStateColor.resolveWith(
                (states) => states.contains(WidgetState.selected) ? OmiColors.accent : OmiColors.surface2,
              ),
              hourMinuteTextColor: WidgetStateColor.resolveWith(
                (states) => states.contains(WidgetState.selected) ? OmiColors.onAccent : OmiColors.textPrimary,
              ),
              dialHandColor: OmiColors.accent,
              dialBackgroundColor: OmiColors.surface2,
              dialTextColor: WidgetStateColor.resolveWith(
                (states) => states.contains(WidgetState.selected) ? OmiColors.onAccent : OmiColors.textSecondary,
              ),
              entryModeIconColor: OmiColors.textTertiary,
              dayPeriodColor: WidgetStateColor.resolveWith(
                (states) => states.contains(WidgetState.selected) ? OmiColors.accent : Colors.transparent,
              ),
              dayPeriodTextColor: WidgetStateColor.resolveWith(
                (states) => states.contains(WidgetState.selected) ? OmiColors.onAccent : OmiColors.textTertiary,
              ),
              dayPeriodBorderSide: const BorderSide(color: OmiColors.textTertiary),
            ),
          ),
          child: child!,
        );
      },
    );

    if (pickedTime != null && mounted) {
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
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final dates = OmiDateFormat.of(context);

    return Material(
      color: Colors.transparent,
      child: Container(
        height: MediaQuery.of(context).size.height * 0.65,
        decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.sheetTop),
        child: Column(
          children: [
            const SizedBox(height: OmiSpacing.sm),
            // Header
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  OmiButton.tertiary(
                    label: context.l10n.cancel,
                    size: OmiButtonSize.compact,
                    onPressed: () => Navigator.pop(context),
                  ),
                  Flexible(
                    child: Text(
                      dates.date(_selectedDateTime),
                      style: OmiType.headline,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  OmiButton.tertiary(
                    label: context.l10n.done,
                    size: OmiButtonSize.compact,
                    onPressed: () => Navigator.pop(context, _selectedDateTime),
                  ),
                ],
              ),
            ),
            const SizedBox(height: OmiSpacing.md),
            Expanded(
              child: SingleChildScrollView(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.start,
                  children: [
                    CalendarDatePicker2(
                      config: getDefaultCalendarConfig(
                        firstDate: now,
                        currentDate: now,
                        lastDate: (widget.initialDateTime ?? now).add(const Duration(days: 365 * 5)),
                        yearBuilder: yearBuilder,
                      ).copyWith(
                        // Neutral selection (INV-UI-1): white day, black numeral.
                        selectedDayHighlightColor: OmiColors.accent,
                        selectedDayTextStyle: OmiType.subhead.copyWith(
                          color: OmiColors.onAccent,
                          fontWeight: FontWeight.w600,
                        ),
                        todayTextStyle: OmiType.subhead.copyWith(fontWeight: FontWeight.w700),
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
                    InkWell(
                      onTap: _pickTime,
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 40, vertical: OmiSpacing.sm),
                          child: Row(
                            children: [
                              const Icon(Icons.access_time, color: OmiColors.textSecondary, size: 20),
                              const SizedBox(width: OmiSpacing.sm),
                              Expanded(child: Text(context.l10n.time, style: OmiType.callout)),
                              Text(
                                dates.time(_selectedDateTime),
                                style: OmiType.callout.copyWith(fontWeight: FontWeight.w600),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
