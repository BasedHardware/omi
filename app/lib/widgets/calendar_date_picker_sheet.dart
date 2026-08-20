import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

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
    selectedDayHighlightColor: ResponsiveHelper.purplePrimary,
    dayTextStyle: const TextStyle(color: ResponsiveHelper.textPrimary),
    selectedDayTextStyle: const TextStyle(color: ResponsiveHelper.textPrimary, fontWeight: FontWeight.bold),
    todayTextStyle: const TextStyle(color: ResponsiveHelper.purplePrimary, fontWeight: FontWeight.bold),
    weekdayLabelTextStyle: const TextStyle(color: ResponsiveHelper.textTertiary, fontWeight: FontWeight.w500),
    controlsTextStyle: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
    disabledDayTextStyle: const TextStyle(color: ResponsiveHelper.textQuaternary),
  );
}

/// Shared date-range picker sheet for filtering the conversation list.
///
/// Extracted from two near-identical inline copies (search widget + home
/// page shortcut button) so the range-picker behavior only needs to be
/// correct in one place. The "Done" action intentionally uses a neutral
/// (white) color per INV-UI-1 (see docs/product/invariants/brand-ui.md)
/// rather than the off-brand accent the two originals used, since this file
/// already references that accent color for calendar highlighting.
Future<void> showConversationDateRangePicker(BuildContext context) async {
  final provider = Provider.of<ConversationProvider>(context, listen: false);
  final hasExistingFilter = provider.selectedStartDate != null;
  List<DateTime?> range = [
    provider.selectedStartDate ?? DateTime.now(),
    provider.selectedEndDate ?? provider.selectedStartDate ?? DateTime.now(),
  ];

  await showCupertinoModalPopup<void>(
    context: context,
    builder: (BuildContext context) {
      return Container(
        height: 420,
        padding: const EdgeInsets.only(top: 6.0),
        margin: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        color: const Color(0xFF1F1F25),
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              // Header with Cancel/Remove Filter and Done buttons
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                decoration: const BoxDecoration(
                  color: Color(0xFF1F1F25),
                  border: Border(bottom: BorderSide(color: Color(0xFF35343B), width: 0.5)),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: () async {
                        if (hasExistingFilter) {
                          Navigator.of(context).pop();
                          await provider.clearDateFilter();
                          PlatformManager.instance.analytics.calendarFilterCleared();
                        } else {
                          Navigator.of(context).pop();
                        }
                      },
                      child: Text(
                        hasExistingFilter ? context.l10n.removeFilter : context.l10n.cancel,
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                      ),
                    ),
                    const Spacer(),
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: () async {
                        final start = range.isNotEmpty ? range[0] : null;
                        if (start == null) {
                          Navigator.of(context).pop();
                          return;
                        }
                        final end = range.length > 1 ? (range[1] ?? start) : start;
                        Navigator.of(context).pop();
                        await provider.filterConversationsByDateRange(start, end);
                        PlatformManager.instance.analytics.calendarFilterApplied(start, end);
                      },
                      child: Text(
                        context.l10n.done,
                        style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ],
                ),
              ),
              // Date range picker
              Expanded(
                child: Material(
                  color: ResponsiveHelper.backgroundSecondary,
                  child: CalendarDatePicker2(
                    config: getDefaultCalendarConfig(
                      firstDate: DateTime(2020),
                      lastDate: DateTime.now(),
                      currentDate: DateTime.now(),
                      calendarType: CalendarDatePicker2Type.range,
                    ),
                    value: range,
                    onValueChanged: (dates) {
                      range = dates;
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    },
  );
}

/// Inclusive end of a calendar range. A single selected day has no second
/// date, so fall back to [start] instead of leaving the upper bound open.
DateTime closedCalendarRangeEnd(DateTime start, DateTime? end) => end ?? start;

/// Date-range picker for conversation *search* (#4457 / #7977).
///
/// Sibling of [showConversationDateRangePicker]: that sheet filters the
/// in-memory list via [ConversationProvider.selectedStartDate], while this
/// one sets [ConversationProvider.searchStartDate] / [searchEndDate] and
/// re-runs the active search. Apply is a no-op when there is no search query
/// so an empty search bar cannot show a misleading active-filter state.
Future<void> showConversationSearchDateRangePicker(BuildContext context) async {
  final provider = Provider.of<ConversationProvider>(context, listen: false);
  final hasExistingFilter = provider.searchStartDate != null;
  DateTime? startDate = provider.searchStartDate;
  DateTime? endDate = provider.searchEndDate;
  List<DateTime?> range = [startDate, endDate];

  await showCupertinoModalPopup<void>(
    context: context,
    builder: (BuildContext context) {
      return Container(
        height: 420,
        padding: const EdgeInsets.only(top: 6.0),
        margin: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        color: const Color(0xFF1F1F25),
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                decoration: const BoxDecoration(
                  color: Color(0xFF1F1F25),
                  border: Border(bottom: BorderSide(color: Color(0xFF35343B), width: 0.5)),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    CupertinoButton(
                      key: const Key('search_date_range_cancel'),
                      padding: EdgeInsets.zero,
                      onPressed: () async {
                        if (hasExistingFilter) {
                          Navigator.of(context).pop();
                          provider.clearSearchDateRange();
                          if (provider.previousQuery.isNotEmpty) {
                            await provider.searchConversations(provider.previousQuery);
                          }
                          PlatformManager.instance.analytics.calendarFilterCleared();
                        } else {
                          Navigator.of(context).pop();
                        }
                      },
                      child: Text(
                        hasExistingFilter ? context.l10n.removeFilter : context.l10n.cancel,
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                      ),
                    ),
                    const Spacer(),
                    CupertinoButton(
                      key: const Key('search_date_range_done'),
                      padding: EdgeInsets.zero,
                      onPressed: () async {
                        final start = range.isNotEmpty ? range[0] : startDate;
                        if (start == null) {
                          Navigator.of(context).pop();
                          return;
                        }
                        final end = closedCalendarRangeEnd(start, range.length > 1 ? range[1] : null);
                        Navigator.of(context).pop();
                        if (provider.previousQuery.isNotEmpty) {
                          provider.setSearchDateRange(start, end);
                          await provider.searchConversations(provider.previousQuery);
                          PlatformManager.instance.analytics.calendarFilterApplied(start, end);
                        }
                      },
                      child: Text(
                        context.l10n.done,
                        style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Material(
                  color: ResponsiveHelper.backgroundSecondary,
                  child: CalendarDatePicker2(
                    config: getDefaultCalendarConfig(
                      firstDate: DateTime(2020),
                      lastDate: DateTime.now(),
                      currentDate: DateTime.now(),
                      calendarType: CalendarDatePicker2Type.range,
                    ),
                    value: range,
                    onValueChanged: (dates) {
                      range = dates;
                      if (dates.isNotEmpty) {
                        startDate = dates[0];
                        endDate = dates.length > 1 ? dates[1] : null;
                      }
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    },
  );
}
