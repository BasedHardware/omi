1 import 'package:device_calendar/device_calendar.dart';
2 import 'package:flutter/material.dart';
3 import 'package:flutter_timezone/flutter_timezone.dart';
4 import 'package:friend_private/backend/preferences.dart';
5 
6 // TODO: handle this cases
7 // - Process reminders during the transcription? if they include smth like "Hey Friend..."
8 // - If there's a event to be created that was in 10 minutes, but the conversation was 20 minutes
9 //    - we shouldn't create the event, but that edge cases still happens.
10 class CalendarUtil {
11   static final CalendarUtil _instance = CalendarUtil._internal();
12   static DeviceCalendarPlugin? _calendarPlugin;
13 
14   factory CalendarUtil() {
15     return _instance;
16   }
17 
18   CalendarUtil._internal();
19 
20   static void init() {
21     _calendarPlugin = DeviceCalendarPlugin();
22   }
23 
24   enableCalendarAccess() async {
25     var permissionsGranted = await _calendarPlugin!.hasPermissions();
26     if (permissionsGranted.isSuccess && (permissionsGranted.data == null || permissionsGranted.data == false)) {
27       permissionsGranted = await _calendarPlugin!.requestPermissions();
28       if (!permissionsGranted.isSuccess || permissionsGranted.data == null || permissionsGranted.data == false) {
29         return false;
30       }
31     }
32     return true;
33   }
34 
35   Future<List<Calendar>> getCalendars() async {
36     bool hasAccess = await enableCalendarAccess();
37     if (!hasAccess) return [];
38 
39     try {
40       final calendarsResult = await _calendarPlugin!.retrieveCalendars();
41       if (calendarsResult.isSuccess && calendarsResult.data != null) {
42         return calendarsResult.data!;
43       }
44     } catch (e) {
45       print('Failed to get calendars: $e');
46     }
47     return [];
48   }
49 
50   Future<bool> createEvent(String title, DateTime startsAt, int durationMinutes, {String? description, String? location}) async {
51     bool hasAccess = await enableCalendarAccess();
52     if (!hasAccess) return false;
53     final String currentTimeZone = await FlutterTimezone.getLocalTimezone();
54     final currentLocation = timeZoneDatabase.locations[currentTimeZone];
55     String calendarId = SharedPreferencesUtil().calendarId;
56     var event = Event(
57       calendarId,
58       title: title,
59       description: description,
60       start: TZDateTime.from(startsAt, currentLocation!),
61       end: TZDateTime.from(startsAt.add(Duration(minutes: durationMinutes)), currentLocation),
62       availability: Availability.Tentative,
63       location: location,
64     );
65     final createResult = await _calendarPlugin!.createOrUpdateEvent(event);
66     if (createResult?.isSuccess == true) {
67       debugPrint('Event created successfully ${createResult!.data}');
68       return true;
69     } else {
70       debugPrint('Failed to create event: ${createResult!.errors}');
71     }
72     return false;
73   }
74 }
