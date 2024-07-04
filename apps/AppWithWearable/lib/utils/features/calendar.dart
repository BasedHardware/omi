import 'package:device_calendar/device_calendar.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:friend_private/backend/preferences.dart';

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

  Future<List<Calendar>> getCalendars() async {
    bool hasAccess = await enableCalendarAccess();
    if (!hasAccess) return [];

    final calendarsResult = await _calendarPlugin!.retrieveCalendars();
    if (calendarsResult.isSuccess && calendarsResult.data != null) {
      return calendarsResult.data!;
    }
    return [];
  }

  Future createEvent(String title, DateTime startsAt, int durationMinutes, {String? description}) async {
    bool hasAccess = await enableCalendarAccess();
    if (!hasAccess) return;
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
      print('Event created successfully ${createResult!.data}');
    } else {
      print('Failed to create event: ${createResult!.errors}');
    }
  }
}
