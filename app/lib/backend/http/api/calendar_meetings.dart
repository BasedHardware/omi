import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/calendar_meeting_context.dart';
import 'package:omi/env/env.dart';

/// Response from storing a meeting
class StoreMeetingResponse {
  final String meetingId;
  final String calendarEventId;
  final String message;

  StoreMeetingResponse({
    required this.meetingId,
    required this.calendarEventId,
    required this.message,
  });

  factory StoreMeetingResponse.fromJson(Map<String, dynamic> json) {
    return StoreMeetingResponse(
      meetingId: json['meeting_id'] ?? '',
      calendarEventId: json['calendar_event_id'] ?? '',
      message: json['message'] ?? 'Meeting stored successfully',
    );
  }
}

/// Store or update a calendar meeting in Firestore via backend API
Future<StoreMeetingResponse?> storeMeeting({
  required String calendarEventId,
  required String calendarSource,
  required String title,
  required DateTime startTime,
  required DateTime endTime,
  String? platform,
  String? meetingLink,
  List<MeetingParticipant>? participants,
  String? notes,
}) async {
  try {
    final requestBody = jsonEncode({
      'calendar_event_id': calendarEventId,
      'calendar_source': calendarSource,
      'title': title,
      'start_time': startTime.toUtc().toIso8601String(),
      'end_time': endTime.toUtc().toIso8601String(),
      'platform': platform,
      'meeting_link': meetingLink,
      'participants': participants?.map((p) => p.toJson()).toList() ?? [],
      'notes': notes,
    });

    debugPrint('storeMeeting: Storing meeting $calendarEventId');

    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/calendar/meetings',
      headers: {},
      method: 'POST',
      body: requestBody,
    );

    if (response == null) {
      debugPrint('storeMeeting: No response from API');
      return null;
    }

    if (response.statusCode == 200) {
      final result = StoreMeetingResponse.fromJson(jsonDecode(response.body));
      debugPrint('storeMeeting: Success - meeting_id: ${result.meetingId}');
      return result;
    } else {
      debugPrint('storeMeeting: Failed with status ${response.statusCode}: ${response.body}');
      return null;
    }
  } catch (e, stackTrace) {
    debugPrint('storeMeeting: Exception: $e');
    debugPrint('storeMeeting: Stack trace: $stackTrace');
    return null;
  }
}

/// Get a calendar meeting by its Firestore document ID
Future<CalendarMeetingContext?> getMeeting(String meetingId) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/calendar/meetings/$meetingId',
      headers: {},
      method: 'GET',
      body: '',
    );

    if (response == null) return null;

    if (response.statusCode == 200) {
      return CalendarMeetingContext.fromJson(jsonDecode(response.body));
    } else {
      debugPrint('getMeeting: Failed with status ${response.statusCode}');
      return null;
    }
  } catch (e) {
    debugPrint('getMeeting: Exception: $e');
    return null;
  }
}

/// List calendar meetings within a date range
Future<List<CalendarMeetingContext>> listMeetings({
  DateTime? startDate,
  DateTime? endDate,
  int limit = 50,
}) async {
  try {
    String url = '${Env.apiBaseUrl}v1/calendar/meetings?limit=$limit';

    if (startDate != null) {
      url += '&start_date=${startDate.toUtc().toIso8601String()}';
    }

    if (endDate != null) {
      url += '&end_date=${endDate.toUtc().toIso8601String()}';
    }

    var response = await makeApiCall(
      url: url,
      headers: {},
      method: 'GET',
      body: '',
    );

    if (response == null) return [];

    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((json) => CalendarMeetingContext.fromJson(json)).toList();
    } else {
      debugPrint('listMeetings: Failed with status ${response.statusCode}');
      return [];
    }
  } catch (e) {
    debugPrint('listMeetings: Exception: $e');
    return [];
  }
}
