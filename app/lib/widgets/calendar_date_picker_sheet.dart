import 'package:flutter/material.dart';

import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/ui/ui.dart';

typedef CalendarYearBuilder = Widget Function({
  required int year,
  TextStyle? textStyle,
  BoxDecoration? decoration,
  bool? isSelected,
  bool? isDisabled,
  bool? isCurrentYear,
});

CalendarDatePicker2Config getDefaultCalendarConfig({
  DateTime? firstDate,
  DateTime? lastDate,
  DateTime? currentDate,
  CalendarDatePicker2Type calendarType = CalendarDatePicker2Type.single,
  bool disableMonthPicker = true,
  CalendarYearBuilder? yearBuilder,
}) {
  final now = DateTime.now();
  return CalendarDatePicker2Config(
    calendarType: calendarType,
    firstDate: firstDate ?? now,
    currentDate: currentDate ?? now,
    lastDate: lastDate ?? now.add(const Duration(days: 365 * 5)),
    disableMonthPicker: disableMonthPicker,
    yearBuilder: yearBuilder,
    // Neutral accent (INV-UI-1): a white selection with black text, today in bold white.
    selectedDayHighlightColor: OmiColors.accent,
    selectedRangeHighlightColor: OmiColors.surface3,
    dayTextStyle: const TextStyle(color: OmiColors.textPrimary),
    selectedDayTextStyle: const TextStyle(color: OmiColors.onAccent, fontWeight: FontWeight.bold),
    todayTextStyle: const TextStyle(color: OmiColors.textPrimary, fontWeight: FontWeight.w800),
    weekdayLabelTextStyle: const TextStyle(color: OmiColors.textTertiary, fontWeight: FontWeight.w500),
    controlsTextStyle: OmiType.callout.copyWith(fontWeight: FontWeight.w600),
    disabledDayTextStyle: const TextStyle(color: OmiColors.textDisabled),
  );
}

/// The one conversation date filter picker (hub audit #23).
///
/// The same filter narrows the list and, while a search is active, the search
/// ([ConversationProvider.filterConversationsByDateRange]), so the calendar
/// button never silently switches what it filters. The active filter is also
/// shown as a removable chip under the search bar (`ConversationDateFilterChip`).
/// Colours are neutral per INV-UI-1 (product/invariants/brand-ui.md).
Future<void> showConversationDateRangePicker(BuildContext context) async {
  final provider = Provider.of<ConversationProvider>(context, listen: false);
  final l10n = context.l10n;
  final hasExistingFilter = provider.selectedStartDate != null;
  final now = DateTime.now();
  List<DateTime?> range = [
    provider.selectedStartDate ?? now,
    provider.selectedEndDate ?? provider.selectedStartDate ?? now,
  ];

  await showOmiSheet<void>(
    context: context,
    title: l10n.filterByDate,
    builder: (sheetContext) {
      return SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: 340,
              child: Material(
                color: Colors.transparent,
                child: CalendarDatePicker2(
                  config: getDefaultCalendarConfig(
                    firstDate: DateTime(2020),
                    lastDate: now,
                    currentDate: now,
                    calendarType: CalendarDatePicker2Type.range,
                  ),
                  value: range,
                  onValueChanged: (dates) => range = dates,
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xs, bottom: OmiSpacing.md),
              child: Row(
                children: [
                  if (hasExistingFilter)
                    Expanded(
                      child: OmiButton.secondary(
                        key: const Key('date_range_remove'),
                        label: l10n.removeFilter,
                        onPressed: () async {
                          Navigator.of(sheetContext).pop();
                          await provider.clearDateFilter();
                          PlatformManager.instance.analytics.calendarFilterCleared();
                        },
                      ),
                    ),
                  if (hasExistingFilter) const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: OmiButton(
                      key: const Key('date_range_done'),
                      label: l10n.done,
                      onPressed: () async {
                        final start = range.isNotEmpty ? range[0] : null;
                        Navigator.of(sheetContext).pop();
                        if (start == null) return;
                        final end = closedCalendarRangeEnd(start, range.length > 1 ? range[1] : null);
                        await provider.filterConversationsByDateRange(start, end);
                        PlatformManager.instance.analytics.calendarFilterApplied(start, end);
                      },
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
    },
  );
}

/// Inclusive end of a calendar range. A single selected day has no second
/// date, so fall back to [start] instead of leaving the upper bound open.
DateTime closedCalendarRangeEnd(DateTime start, DateTime? end) => end ?? start;
