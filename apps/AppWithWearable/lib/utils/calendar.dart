import 'package:device_calendar/device_calendar.dart';
import 'package:flutter_native_timezone/flutter_native_timezone.dart';
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

  _getTimezone() => FlutterNativeTimezone.getLocalTimezone();

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

  Future createEvent(String title, String startsAt, {String? description}) async {
    bool hasAccess = await enableCalendarAccess();
    if (!hasAccess) return;
    final currentLocation = timeZoneDatabase.locations[_getTimezone()];
    String calendarId = SharedPreferencesUtil().calendarId;
    var event = Event(
      calendarId,
      title: title,
      description: description,
      start: TZDateTime.from(DateTime.parse(startsAt), currentLocation!),
      end: TZDateTime.from(DateTime.parse(startsAt).add(const Duration(minutes: 30)), currentLocation),
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
