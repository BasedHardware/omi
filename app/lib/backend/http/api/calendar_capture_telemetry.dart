import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/capture/calendar_capture_gap_monitor.dart';

/// Read-only input to capture health telemetry; no synthetic conversations.
Future<List<CalendarCaptureWindow>?> fetchCalendarCaptureWindows(DateTime start, DateTime end) async {
  final uri = Uri.parse(
    '${Env.apiBaseUrl}v1/calendar/capture-gaps',
  ).replace(queryParameters: {'start': start.toUtc().toIso8601String(), 'end': end.toUtc().toIso8601String()});
  final response = await makeApiCall(url: uri.toString(), headers: {}, method: 'GET', body: '');
  if (response?.statusCode != 200) return null;
  final rows = jsonDecode(utf8.decode(response!.bodyBytes)) as List;
  return [
    for (final row in rows)
      if (row is Map<String, dynamic> && row['coverage'] == 'not_captured' && row['status'] == 'confirmed')
        CalendarCaptureWindow(
          row['event_id'] as String,
          DateTime.parse(row['start_time'] as String),
          DateTime.parse(row['end_time'] as String),
        ),
  ];
}
