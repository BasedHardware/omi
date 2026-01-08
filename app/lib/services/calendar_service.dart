import 'dart:async';
import 'package:flutter/services.dart';

class CalendarService {
  static const MethodChannel _methodChannel = MethodChannel('com.omi/calendar');
  static const EventChannel _eventChannel = EventChannel('com.omi/calendar/events');

  Stream<CalendarMeetingEvent>? _calendarStream;
  StreamSubscription? _streamSubscription;

  /// Request calendar access permission
  Future<CalendarPermissionStatus> requestPermission() async {
    try {
      final String? result = await _methodChannel.invokeMethod('requestPermission');
      return _parsePermissionStatus(result);
    } catch (e) {
      print('CalendarService: Error requesting permission: $e');
      return CalendarPermissionStatus.denied;
    }
  }

  /// Check current permission status
  Future<CalendarPermissionStatus> checkPermissionStatus() async {
    try {
      final String? result = await _methodChannel.invokeMethod('checkPermissionStatus');
      return _parsePermissionStatus(result);
    } catch (e) {
      print('CalendarService: Error checking permission status: $e');
      return CalendarPermissionStatus.notDetermined;
    }
  }

  /// Start monitoring calendar events
  Future<void> startMonitoring() async {
    try {
      await _methodChannel.invokeMethod('startMonitoring');
      print('CalendarService: Started monitoring');
    } catch (e) {
      print('CalendarService: Error starting monitoring: $e');
    }
  }

  /// Stop monitoring calendar events
  Future<void> stopMonitoring() async {
    try {
      await _methodChannel.invokeMethod('stopMonitoring');
      print('CalendarService: Stopped monitoring');
    } catch (e) {
      print('CalendarService: Error stopping monitoring: $e');
    }
  }

  /// Get list of upcoming meetings
  Future<List<CalendarMeeting>> getUpcomingMeetings() async {
    try {
      final List<dynamic>? result = await _methodChannel.invokeMethod('getUpcomingMeetings');
      if (result == null) return [];

      return result.map((item) => CalendarMeeting.fromMap(item as Map<dynamic, dynamic>)).toList();
    } catch (e) {
      print('CalendarService: Error getting upcoming meetings: $e');
      return [];
    }
  }

  /// Get all available calendars from the system
  Future<List<SystemCalendar>> getAvailableCalendars() async {
    try {
      final result = await _methodChannel.invokeMethod('getAvailableCalendars');
      final calendars = (result as List).map((calendar) {
        return SystemCalendar.fromMap(calendar as Map<dynamic, dynamic>);
      }).toList();
      return calendars;
    } catch (e) {
      print('CalendarService: Error getting available calendars: $e');
      return [];
    }
  }

  /// Update calendar settings
  Future<void> updateSettings({
    bool? showEventsWithNoParticipants,
    bool? showMeetingsInMenuBar,
  }) async {
    try {
      final args = <String, dynamic>{};
      if (showEventsWithNoParticipants != null) {
        args['showEventsWithNoParticipants'] = showEventsWithNoParticipants;
      }
      if (showMeetingsInMenuBar != null) {
        args['showMeetingsInMenuBar'] = showMeetingsInMenuBar;
      }

      await _methodChannel.invokeMethod('updateCalendarSettings', args);
    } catch (e) {
      print('CalendarService: Error updating settings: $e');
    }
  }

  /// Snooze a meeting notification
  Future<void> snoozeMeeting(String eventId, int minutes) async {
    try {
      await _methodChannel.invokeMethod('snoozeMeeting', {
        'eventId': eventId,
        'minutes': minutes,
      });
      print('CalendarService: Snoozed meeting $eventId for $minutes minutes');
    } catch (e) {
      print('CalendarService: Error snoozing meeting: $e');
    }
  }

  /// Stream of calendar meeting events
  Stream<CalendarMeetingEvent> get meetingStream {
    _calendarStream ??= _eventChannel.receiveBroadcastStream().map((event) {
      return CalendarMeetingEvent.fromMap(event as Map<dynamic, dynamic>);
    });
    return _calendarStream!;
  }

  /// Initialize and listen to calendar events
  void initialize({
    Function(CalendarMeetingEvent)? onMeetingEvent,
  }) {
    _streamSubscription = meetingStream.listen(
      (event) {
        print('CalendarService: Received event: ${event.type} - ${event.title}');
        onMeetingEvent?.call(event);
      },
      onError: (error) {
        print('CalendarService: Stream error: $error');
      },
    );
  }

  /// Cleanup
  void dispose() {
    _streamSubscription?.cancel();
    _streamSubscription = null;
  }

  CalendarPermissionStatus _parsePermissionStatus(String? status) {
    switch (status) {
      case 'authorized':
        return CalendarPermissionStatus.authorized;
      case 'denied':
        return CalendarPermissionStatus.denied;
      case 'restricted':
        return CalendarPermissionStatus.restricted;
      default:
        return CalendarPermissionStatus.notDetermined;
    }
  }
}

/// Participant in a calendar meeting
class CalendarParticipant {
  final String? name;
  final String? email;

  CalendarParticipant({this.name, this.email});

  factory CalendarParticipant.fromMap(Map<dynamic, dynamic> map) {
    return CalendarParticipant(
      name: map['name'] as String?,
      email: map['email'] as String?,
    );
  }

  String get displayName {
    if (name != null && name!.isNotEmpty) return name!;
    if (email != null && email!.isNotEmpty) return email!;
    return 'Unknown';
  }
}

/// Calendar meeting model
class CalendarMeeting {
  final String id; // Calendar event ID from system (macOS)
  final String title;
  final DateTime startTime;
  final DateTime endTime;
  final String platform;
  final String? meetingUrl;
  final int attendeeCount;
  final List<CalendarParticipant> participants;
  final String? notes;
  final String? meetingId; // Backend meeting ID (synced to backend)

  CalendarMeeting({
    required this.id,
    required this.title,
    required this.startTime,
    required this.endTime,
    required this.platform,
    this.meetingUrl,
    required this.attendeeCount,
    this.participants = const [],
    this.notes,
    this.meetingId,
  });

  factory CalendarMeeting.fromMap(Map<dynamic, dynamic> map) {
    final participantsList = (map['participants'] as List<dynamic>?)
            ?.map((p) => CalendarParticipant.fromMap(p as Map<dynamic, dynamic>))
            .toList() ??
        [];

    return CalendarMeeting(
      id: map['id'] as String,
      title: map['title'] as String,
      startTime: DateTime.parse(map['startTime'] as String).toLocal(),
      endTime: DateTime.parse(map['endTime'] as String).toLocal(),
      platform: map['platform'] as String,
      meetingUrl: map['meetingUrl'] as String?,
      attendeeCount: map['attendeeCount'] as int,
      participants: participantsList,
      notes: map['notes'] as String?,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'title': title,
      'startTime': startTime.toUtc().toIso8601String(),
      'endTime': endTime.toUtc().toIso8601String(),
      'platform': platform,
      'meetingUrl': meetingUrl,
      'attendeeCount': attendeeCount,
      'participants': participants
          .map((p) => {
                if (p.name != null) 'name': p.name,
                if (p.email != null) 'email': p.email,
              })
          .toList(),
      if (notes != null) 'notes': notes,
      if (meetingId != null) 'meetingId': meetingId,
    };
  }

  CalendarMeeting copyWith({
    String? id,
    String? title,
    DateTime? startTime,
    DateTime? endTime,
    String? platform,
    String? meetingUrl,
    int? attendeeCount,
    List<CalendarParticipant>? participants,
    String? notes,
    String? meetingId,
  }) {
    return CalendarMeeting(
      id: id ?? this.id,
      title: title ?? this.title,
      startTime: startTime ?? this.startTime,
      endTime: endTime ?? this.endTime,
      platform: platform ?? this.platform,
      meetingUrl: meetingUrl ?? this.meetingUrl,
      attendeeCount: attendeeCount ?? this.attendeeCount,
      participants: participants ?? this.participants,
      notes: notes ?? this.notes,
      meetingId: meetingId ?? this.meetingId,
    );
  }

  /// Time until meeting starts (negative if already started)
  Duration get timeUntilStart => startTime.difference(DateTime.now());

  /// Minutes until meeting starts
  int get minutesUntilStart => timeUntilStart.inMinutes;

  /// Whether meeting has started
  bool get hasStarted => DateTime.now().isAfter(startTime);

  /// Whether meeting has ended
  bool get hasEnded => DateTime.now().isAfter(endTime);

  /// Whether meeting is currently active
  bool get isActive => hasStarted && !hasEnded;

  @override
  String toString() {
    return 'CalendarMeeting(title: $title, platform: $platform, starts: $startTime)';
  }
}

/// Calendar meeting event from event stream
class CalendarMeetingEvent {
  final CalendarMeetingEventType type;
  final String eventId;
  final String title;
  final String platform;
  final DateTime? startTime;
  final int? minutesUntilStart;

  CalendarMeetingEvent({
    required this.type,
    required this.eventId,
    required this.title,
    required this.platform,
    this.startTime,
    this.minutesUntilStart,
  });

  factory CalendarMeetingEvent.fromMap(Map<dynamic, dynamic> map) {
    return CalendarMeetingEvent(
      type: _parseEventType(map['type'] as String),
      eventId: map['eventId'] as String? ?? '',
      title: map['title'] as String? ?? '',
      platform: map['platform'] as String? ?? '',
      startTime: map['startTime'] != null ? DateTime.parse(map['startTime'] as String).toLocal() : null,
      minutesUntilStart: map['minutesUntilStart'] as int?,
    );
  }

  static CalendarMeetingEventType _parseEventType(String type) {
    switch (type) {
      case 'upcomingSoon':
        return CalendarMeetingEventType.upcomingSoon;
      case 'started':
        return CalendarMeetingEventType.started;
      case 'ended':
        return CalendarMeetingEventType.ended;
      case 'meetingsUpdated':
        return CalendarMeetingEventType.meetingsUpdated;
      default:
        return CalendarMeetingEventType.upcomingSoon;
    }
  }

  @override
  String toString() {
    return 'CalendarMeetingEvent(type: $type, title: $title, platform: $platform, minutesUntilStart: $minutesUntilStart)';
  }
}

/// System calendar from macOS Calendar
class SystemCalendar {
  final String id;
  final String title;
  final int type;
  final bool isSubscribed;
  final Color? color;

  SystemCalendar({
    required this.id,
    required this.title,
    required this.type,
    required this.isSubscribed,
    this.color,
  });

  factory SystemCalendar.fromMap(Map<dynamic, dynamic> map) {
    Color? calendarColor;
    if (map['colorRed'] != null && map['colorGreen'] != null && map['colorBlue'] != null) {
      calendarColor = Color.fromRGBO(
        map['colorRed'] as int,
        map['colorGreen'] as int,
        map['colorBlue'] as int,
        1.0,
      );
    }

    return SystemCalendar(
      id: map['id'] as String,
      title: map['title'] as String,
      type: map['type'] as int,
      isSubscribed: map['isSubscribed'] as bool,
      color: calendarColor,
    );
  }

  @override
  String toString() {
    return 'SystemCalendar(title: $title, id: $id)';
  }
}

/// Types of calendar meeting events
enum CalendarMeetingEventType {
  upcomingSoon, // Meeting starting in 2-5 minutes
  started, // Meeting just started
  ended, // Meeting ended
  meetingsUpdated, // Meetings list was refreshed/updated
}

/// Calendar permission status
enum CalendarPermissionStatus {
  authorized, // User granted permission
  denied, // User denied permission
  notDetermined, // Permission not yet requested
  restricted, // Permission restricted (parental controls, etc.)
}

/// Extension for user-friendly status messages
extension CalendarPermissionStatusExtension on CalendarPermissionStatus {
  String get displayName {
    switch (this) {
      case CalendarPermissionStatus.authorized:
        return 'Authorized';
      case CalendarPermissionStatus.denied:
        return 'Denied';
      case CalendarPermissionStatus.notDetermined:
        return 'Not Determined';
      case CalendarPermissionStatus.restricted:
        return 'Restricted';
    }
  }

  bool get isGranted => this == CalendarPermissionStatus.authorized;
}
