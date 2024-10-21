import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:manage_calendar_events/manage_calendar_events.dart';
import 'package:permission_handler/permission_handler.dart';

// TODO: handle this cases
// - Process reminders during the transcription? if they include smth like "Hey Friend..."
// - If there's a event to be created that was in 10 minutes, but the conversation was 20 minutes
//    - we shouldn't create the event, but that edge cases still happens.

class CalendarUtil {
  static final CalendarUtil _instance = CalendarUtil._internal();
  static CalendarPlugin? _calendarPlugin;

  factory CalendarUtil() {
    return _instance;
  }

  CalendarUtil._internal();

  static void init() {
    _calendarPlugin = CalendarPlugin();
  }

  Future<bool> checkCalendarPermission() async {
    try {
      var status = await Permission.calendarFullAccess.status;
      if (status.isGranted) {
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
    final calendarsResult = await _calendarPlugin!.getCalendars();
    Logger.log('calendarsResult: $calendarsResult');
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
    // utcOffset is not needed. Previously sometimes OpenAI was returning in UTC and sometimes in local time.
    // Duration utcOffset = DateTime.now().timeZoneOffset;
    // startDate = startDate.subtract(utcOffset);
    // endDate = endDate.subtract(utcOffset);
    CalendarEvent newEvent = CalendarEvent(
      title: title,
      description: description,
      startDate: startDate,
      endDate: endDate,
    );
    var res = await _calendarPlugin!.createEvent(calendarId: calendarId, event: newEvent);

    if (res != null && res.isNotEmpty) {
      print('Event created successfully');
      return true;
    } else {
      print('Failed to create event: $res');
    }
    return false;
  }
}
