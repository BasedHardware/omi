import 'package:flutter/material.dart';

import 'package:calendar_date_picker2/calendar_date_picker2.dart';

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
  );
}
