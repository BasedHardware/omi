import 'package:device_calendar/device_calendar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:manage_calendar_events/manage_calendar_events.dart' as c;
import 'package:permission_handler/permission_handler.dart';

// TODO: handle this cases
// - Process reminders during the transcription? if they include smth like "Hey Friend..."
// - If there's a event to be created that was in 10 minutes, but the conversation was 20 minutes
//    - we shouldn't create the event, but that edge cases still happens.

class CalendarUtil {
  static final CalendarUtil _instance = CalendarUtil._internal();
  static c.CalendarPlugin? _calendarPlugin;

  factory CalendarUtil() {
    return _instance;
  }

  CalendarUtil._internal();

  static void init() {
    _calendarPlugin = c.CalendarPlugin();
  }

  Future<bool> checkCalendarPermission() async {
    try {
      var status = await Permission.calendarFullAccess.status;
      if (status.isGranted) {
        print('Permission granted');
        return true;
      } else if (status.isDenied || status.isPermanentlyDenied) {
        return false;
      }
      return false;
    } catch (e) {
      Logger.error('Error in checkCalendarPermission: $e');
      return false;
    }
  }

  Future<List<c.Calendar>> fetchCalendars() async {
    final calendarsResult = await _calendarPlugin!.getCalendars();
    Logger.log('calendarsResult: ${calendarsResult}');
    if (calendarsResult != null) {
      return calendarsResult;
    } else {
      return [];
    }
  }

  Future<bool> createEvent(String title, DateTime startsAt, int durationMinutes, {String? description}) async {
    bool hasAccess = await checkCalendarPermission();
    if (!hasAccess) return false;
    DateTime startDate = startsAt.toLocal();
    DateTime endDate = startDate.add(Duration(minutes: durationMinutes));
    String calendarId = SharedPreferencesUtil().calendarId;
    Duration utcOffset = DateTime.now().timeZoneOffset;
    startDate = startDate.subtract(utcOffset);
    endDate = endDate.subtract(utcOffset);
    c.CalendarEvent _newEvent = c.CalendarEvent(
      title: title,
      description: description,
      startDate: startDate,
      endDate: endDate,
    );
    var res = await _calendarPlugin!.createEvent(calendarId: calendarId, event: _newEvent);

    if (res != null && res.isNotEmpty) {
      print('Event created successfully');
      return true;
    } else {
      print('Failed to create event: ${res}');
    }
    return false;
  }
}

class CalendarUtilOld {
  static final CalendarUtilOld _instance = CalendarUtilOld._internal();
  static DeviceCalendarPlugin? _calendarPlugin;

  factory CalendarUtilOld() {
    return _instance;
  }

  CalendarUtilOld._internal();

  static void init() {
    _calendarPlugin = DeviceCalendarPlugin();
  }

  Future<bool> checkCalendarPermission() async {
    try {
      var status = await Permission.calendarFullAccess.status;
      if (status.isGranted) {
        print('Permission granted');
        return true;
      } else if (status.isDenied || status.isPermanentlyDenied) {
        return false;
      }
      return false;
    } catch (e) {
      Logger.error('Error in checkCalendarPermission: $e');
      return false;
    }
  }

  Future<List<Calendar>> fetchCalendars() async {
    await _calendarPlugin!.requestPermissions();
    final calendarsResult = await _calendarPlugin!.retrieveCalendars();
    Logger.log('calendarsResult: ${calendarsResult.data}');
    if (calendarsResult.isSuccess && calendarsResult.data != null) {
      return calendarsResult.data!;
    } else {
      return [];
    }
  }

  Future<bool> createEvent(String title, DateTime startsAt, int durationMinutes, {String? description}) async {
    bool hasAccess = await checkCalendarPermission();
    if (!hasAccess) return false;
    final String currentTimeZone = await FlutterTimezone.getLocalTimezone();
    var currentLocation = timeZoneDatabase.locations[currentTimeZone];
    String calendarId = SharedPreferencesUtil().calendarId;

    TZDateTime eventStart = currentLocation == null
        ? TZDateTime.utc(startsAt.year, startsAt.month, startsAt.day, startsAt.hour, startsAt.minute).toLocal()
        : TZDateTime.from(startsAt, currentLocation).toLocal();

    TZDateTime eventEnd = eventStart.add(Duration(minutes: durationMinutes));

    Duration utcOffset = DateTime.now().timeZoneOffset;
    eventStart = eventStart.subtract(utcOffset);
    eventEnd = eventEnd.subtract(utcOffset);

    var event = Event(
      calendarId,
      title: title,
      description: description,
      start: eventStart,
      end: eventEnd,
      availability: Availability.Tentative,
    );
    final createResult = await _calendarPlugin!.createOrUpdateEvent(event);
    if (createResult?.isSuccess == true) {
      debugPrint('Event created successfully ${createResult!.data}');
      return true;
    } else {
      debugPrint('Failed to create event: ${createResult!.errors}');
    }
    return false;
  }
}
