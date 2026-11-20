// Owner-fenced calendar catalog and selection requests using the typed HTTP client.
// Saved choices invalidate cached meeting hints only after a confirmed server write.
import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/imports_integrations_wire.g.dart' as wire;
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

  factory ReadableGoogleCalendar.fromGenerated(wire.GeneratedReadableCalendar generated) => ReadableGoogleCalendar(
        generated.id,
        generated.name,
        generated.primary,
        generated.available,
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

  factory GoogleCalendarSelection.fromGenerated(wire.GeneratedCalendarSelection generated) => GoogleCalendarSelection(
        generated.accountId,
        generated.calendars.map(ReadableGoogleCalendar.fromGenerated).toList(),
        generated.selectedIds.toSet(),
      );
}

class GoogleCalendarSelectionFailure implements Exception {
  const GoogleCalendarSelectionFailure(this.problem);
  final ApiProblem problem;
}

Future<GoogleCalendarSelection> googleCalendarSelection(
  String owner, {
  GoogleCalendarSelection? selection,
}) async {
  bool current() => owner.isNotEmpty && owner == GoogleCalendarService.meetingCacheOwner;
  final result = await executeApi<GoogleCalendarSelection>(
    request: ApiRequest(
      url: '${Env.apiBaseUrl}v1/calendar/google/calendars',
      method: selection == null ? 'GET' : 'PUT',
      body: selection == null
          ? ''
          : jsonEncode(wire.GeneratedCalendarSelectionUpdate(
              accountId: selection.accountId,
              selectedIds: selection.selectedIds.toList(),
            ).toJson()),
    ),
    canSend: current,
    decode: (body) {
      try {
        return GoogleCalendarSelection.fromGenerated(
          wire.GeneratedCalendarSelection.fromJson(jsonDecode(body) as Map<String, dynamic>),
        );
      } on TypeError {
        throw const FormatException('Invalid calendar selection response');
      }
    },
  );
  if (!current()) {
    throw StateError('calendar_selection_unavailable');
  }
  switch (result) {
    case ApiSuccess<GoogleCalendarSelection>(:final data):
      if (selection != null) GoogleCalendarService.invalidateMeetings();
      return data;
    case ApiFailure<GoogleCalendarSelection>(:final problem):
      throw GoogleCalendarSelectionFailure(problem);
  }
}
