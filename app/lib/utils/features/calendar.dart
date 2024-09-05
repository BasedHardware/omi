import 'package:device_calendar/device_calendar.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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

  Future<bool> enableCalendarAccess() async {
    print('enableCalendarAccess');
    try {
      var permissionsGranted = await _calendarPlugin!.hasPermissions();
      print('permissionsGranted: ${permissionsGranted.data}');

      if (permissionsGranted.isSuccess && (permissionsGranted.data == null || permissionsGranted.data == false)) {
        permissionsGranted = await _calendarPlugin!.requestPermissions();
        print('permissionsGranted after request: ${permissionsGranted.data}');
      }

      bool hasAccess = permissionsGranted.isSuccess && permissionsGranted.data == true;
      print('enableCalendarAccess: $hasAccess');
      return hasAccess;
    } on PlatformException catch (e) {
      print('PlatformException in enableCalendarAccess: ${e.message}');
      return false;
    }
  }

  Future<bool> hasCalendarAccess() async {
    print('hasCalendarAccess');
    try {
      final permissionsGranted = await _calendarPlugin!.hasPermissions();
      return permissionsGranted.isSuccess && permissionsGranted.data == true;
    } on PlatformException catch (e) {
      print('PlatformException in hasCalendarAccess: ${e.message}');
      return false;
    }
  }

  Future<bool> calendarPermissionAsked() async {
    try {
      final permissionsGranted = await _calendarPlugin!.hasPermissions();
      return permissionsGranted.isSuccess;
    } on PlatformException catch (e) {
      print('PlatformException in calendarPermissionAsked: ${e.message}');
      return false;
    }
  }

  Future<List<Calendar>> getCalendars() async {
    print('getCalendars');
    try {
      bool hasAccess = await enableCalendarAccess();
      if (!hasAccess) return [];
      print('getCalendars $hasAccess');

      final calendarsResult = await _calendarPlugin!.retrieveCalendars();
      print('calendarsResult: ${calendarsResult.data}');
      if (calendarsResult.isSuccess && calendarsResult.data != null) {
        return calendarsResult.data!;
      }
    } on PlatformException catch (e) {
      print('PlatformException in getCalendars: ${e.message}');
      if (e.code == '401') {
        // Try to request permissions again
        var permissionsGranted = await _calendarPlugin!.requestPermissions();
        if (permissionsGranted.isSuccess && permissionsGranted.data == true) {
          // If permissions are granted, try to retrieve calendars again
          return await getCalendars();
        } else {
          print('Calendar modification permission denied even after re-requesting');
          return [];
        }
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
