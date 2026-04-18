import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/calendar_meeting_context.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Response from storing a meeting
class StoreMeetingResponse {
  final String meetingId;
  final String calendarEventId;
  final String message;

  StoreMeetingResponse({required this.meetingId, required this.calendarEventId, required this.message});

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

    Logger.debug('storeMeeting: Storing meeting $calendarEventId');

    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/calendar/meetings',
      headers: {},
      method: 'POST',
      body: requestBody,
    );

    if (response == null) {
      Logger.debug('storeMeeting: No response from API');
      return null;
    }

    if (response.statusCode == 200) {
      final result = StoreMeetingResponse.fromJson(jsonDecode(response.body));
      Logger.debug('storeMeeting: Success - meeting_id: ${result.meetingId}');
      return result;
    } else {
      Logger.debug('storeMeeting: Failed with status ${response.statusCode}: ${response.body}');
      return null;
    }
  } catch (e, stackTrace) {
    Logger.debug('storeMeeting: Exception: $e');
    Logger.debug('storeMeeting: Stack trace: $stackTrace');
    return null;
  }
}
