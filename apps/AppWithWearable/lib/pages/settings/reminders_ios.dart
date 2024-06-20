import 'package:device_calendar/device_calendar.dart';
import 'reminders_interface.dart';
import 'package:collection/collection.dart';
import 'package:timezone/timezone.dart' as tz;
import 'package:flutter/material.dart';

// TODO: This writes to calendar not to Reminders
class RemindersIOS implements RemindersInterface {
  @override
  void addReminder(String title, DateTime dueDate) async {
    var deviceCalendarPlugin = DeviceCalendarPlugin();
    var permissionsResult = await deviceCalendarPlugin.hasPermissions();
    if (!permissionsResult.isSuccess || !(permissionsResult.data ?? false)) {
      permissionsResult = await deviceCalendarPlugin.requestPermissions();
      if (!permissionsResult.isSuccess || !(permissionsResult.data ?? false)) {
        // TODO: Handle permissions not granted
        return;
      }
    }
    var calendarsResult = await deviceCalendarPlugin.retrieveCalendars();
    if (!calendarsResult.isSuccess || calendarsResult.data == null) {
      debugPrint(
          'Failed to retrieve calendars: Success=${calendarsResult.isSuccess}, Data=${calendarsResult.data}');
      return;
    }
    var calendar =
        calendarsResult.data!.firstWhereOrNull((cal) => cal.isDefault ?? false);

    if (calendar != null) {
      final tz.TZDateTime startTZ = tz.TZDateTime.from(dueDate, tz.local);
      final tz.TZDateTime endTZ =
          tz.TZDateTime.from(dueDate.add(Duration(hours: 1)), tz.local);
      final event =
          Event(calendar.id, title: title, start: startTZ, end: endTZ);
      var result = await deviceCalendarPlugin.createOrUpdateEvent(event);
      if (result != null) {
        if (!result.isSuccess) {
          debugPrint('Failed to create event: ${result.errors}');
        }
      } else {
        debugPrint('Result is null');
      }
    }
  }
}
