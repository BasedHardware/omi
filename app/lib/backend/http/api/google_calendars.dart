import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/integrations/google_calendar_service.dart';

class ReadableGoogleCalendar {
  final String id;
  final String name;
  final bool primary;
  final bool available;

  const ReadableGoogleCalendar(
    this.id,
    this.name,
    this.primary,
    this.available,
  );

  factory ReadableGoogleCalendar.fromJson(Map<String, dynamic> json) => ReadableGoogleCalendar(
        json['id'] as String,
        json['name'] as String,
        json['primary'] as bool,
        json['available'] as bool,
      );
}

class GoogleCalendarSelection {
  final String accountId;
  final List<ReadableGoogleCalendar> calendars;
  final Set<String> selectedIds;

  const GoogleCalendarSelection(
    this.accountId,
    this.calendars,
    this.selectedIds,
  );

  factory GoogleCalendarSelection.fromJson(Map<String, dynamic> json) => GoogleCalendarSelection(
        json['account_id'] as String,
        (json['calendars'] as List)
            .map(
              (row) => ReadableGoogleCalendar.fromJson(row as Map<String, dynamic>),
            )
            .toList(),
        (json['selected_ids'] as List).cast<String>().toSet(),
      );
}

Future<GoogleCalendarSelection> googleCalendarSelection(
  String owner, {
  GoogleCalendarSelection? selection,
}) async {
  bool current() => owner.isNotEmpty && owner == GoogleCalendarService.meetingCacheOwner;
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/calendar/google/calendars',
    headers: {},
    method: selection == null ? 'GET' : 'PUT',
    body: selection == null
        ? ''
        : jsonEncode({
            'account_id': selection.accountId,
            'selected_ids': selection.selectedIds.toList(),
          }),
    canSend: current,
  );
  if (!current() || response?.statusCode != 200) {
    throw StateError('calendar_selection_unavailable');
  }
  final result = GoogleCalendarSelection.fromJson(
    jsonDecode(utf8.decode(response!.bodyBytes)) as Map<String, dynamic>,
  );
  if (selection != null) GoogleCalendarService.invalidateMeetings();
  return result;
}
