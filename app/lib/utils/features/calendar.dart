import 'package:device_calendar/device_calendar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:friend_private/backend/preferences.dart';

// TODO: handle this cases
// - Process reminders during the transcription? if they include smth like "Hey Friend..."
// - If there's a event to be created that was in 10 minutes, but the conversation was 20 minutes
//    - we shouldn't create the event, but that edge cases still happens.
class CalendarUtil {
  static final CalendarUtil _instance = CalendarUtil._internal();
  static DeviceCalendarPlugin? _calendarPlugin;

  factory CalendarUtil() {
    return _instance;
  }

  CalendarUtil._internal();

  static void init() {
    _calendarPlugin = DeviceCalendarPlugin();
  }

  enableCalendarAccess() async {
    var permissionsGranted = await _calendarPlugin!.hasPermissions();
    if (permissionsGranted.isSuccess && (permissionsGranted.data == null || permissionsGranted.data == false)) {
      permissionsGranted = await _calendarPlugin!.requestPermissions();
      if (!permissionsGranted.isSuccess || permissionsGranted.data == null || permissionsGranted.data == false) {
        return false;
      }
    }
    return true;
  }

  Future<bool> hasCalendarAccess() async {
    final permissionsGranted = await _calendarPlugin!.hasPermissions();
    return permissionsGranted.isSuccess && permissionsGranted.data == true;
  }

  Future<bool> calendarPermissionAsked() async {
    final permissionsGranted = await _calendarPlugin!.hasPermissions();
    return permissionsGranted.isSuccess;
  }

  Future<List<Calendar>> getCalendars() async {
    bool hasAccess = await enableCalendarAccess();
    if (!hasAccess) return [];

    try {
      final calendarsResult = await _calendarPlugin!.retrieveCalendars();
      if (calendarsResult.isSuccess && calendarsResult.data != null) {
        return calendarsResult.data!;
      }
    } catch (e) {
      print('Failed to get calendars: $e');
    }
    return [];
  }

  Future<bool> createEvent(String title, DateTime startsAt, int durationMinutes, {String? description}) async {
    bool hasAccess = await enableCalendarAccess();
    if (!hasAccess) return false;
    final String currentTimeZone = await FlutterTimezone.getLocalTimezone();
    final currentLocation = timeZoneDatabase.locations[currentTimeZone];
    String calendarId = SharedPreferencesUtil().calendarId;
    var event = Event(
      calendarId,
      title: title,
      description: description,
      start: TZDateTime.from(startsAt, currentLocation!),
      end: TZDateTime.from(startsAt.add(Duration(minutes: durationMinutes)), currentLocation),
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
