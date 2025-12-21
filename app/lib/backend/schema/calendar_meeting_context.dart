class MeetingParticipant {
  final String? name;
  final String? email;

  MeetingParticipant({
    this.name,
    this.email,
  });

  factory MeetingParticipant.fromJson(Map<String, dynamic> json) {
    return MeetingParticipant(
      name: json['name'],
      email: json['email'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'email': email,
    };
  }

  String get displayName {
    if (name != null && name!.isNotEmpty) return name!;
    if (email != null && email!.isNotEmpty) return email!;
    return 'Unknown';
  }

  String get fullDisplay {
    if (name != null && email != null) {
      return '$name <$email>';
    }
    return displayName;
  }
}

class CalendarMeetingContext {
  final String calendarEventId;
  final String title;
  final List<MeetingParticipant> participants;
  final String? platform;
  final String? meetingLink;
  final DateTime startTime;
  final int durationMinutes;
  final String? notes;
  final String? calendarSource;

  CalendarMeetingContext({
    required this.calendarEventId,
    required this.title,
    required this.participants,
    this.platform,
    this.meetingLink,
    required this.startTime,
    required this.durationMinutes,
    this.notes,
    this.calendarSource = 'system_calendar',
  });

  factory CalendarMeetingContext.fromJson(Map<String, dynamic> json) {
    return CalendarMeetingContext(
      calendarEventId: json['calendar_event_id'] ?? '',
      title: json['title'] ?? '',
      participants: ((json['participants'] ?? []) as List<dynamic>).map((p) => MeetingParticipant.fromJson(p)).toList(),
      platform: json['platform'],
      meetingLink: json['meeting_link'],
      startTime: DateTime.parse(json['start_time']),
      durationMinutes: json['duration_minutes'] ?? 30,
      notes: json['notes'],
      calendarSource: json['calendar_source'] ?? 'system_calendar',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'calendar_event_id': calendarEventId,
      'title': title,
      'participants': participants.map((p) => p.toJson()).toList(),
      'platform': platform,
      'meeting_link': meetingLink,
      'start_time': startTime.toUtc().toIso8601String(),
      'duration_minutes': durationMinutes,
      'notes': notes,
      'calendar_source': calendarSource,
    };
  }

  DateTime get endTime => startTime.add(Duration(minutes: durationMinutes));

  String get participantNames {
    if (participants.isEmpty) return 'No participants';
    return participants.map((p) => p.displayName).join(', ');
  }

  List<String> get participantNamesList {
    return participants.map((p) => p.displayName).toList();
  }
}
