import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/capture/calendar_capture_gap_monitor.dart';

/// Read-only input to capture health telemetry; no synthetic conversations.
/// Empty success and unavailable calendar evidence remain distinct at HTTP.
Future<ApiResult<List<CalendarCaptureWindow>>> fetchCalendarCaptureWindows(
  DateTime start,
  DateTime end, {
  ApiSend? send,
  String? baseUrl,
  void Function(ApiFallbackEvent)? fallback,
}) async {
  final uri = Uri.parse('${baseUrl ?? Env.apiBaseUrl}v1/calendar/capture-gaps').replace(queryParameters: {
    'start': start.toUtc().toIso8601String(),
    'end': end.toUtc().toIso8601String(),
  });
  final result = await executeApi<String>(
    request: ApiRequest(url: uri.toString(), method: 'GET'),
    send: send,
    decode: (body) => body,
  );
  return switch (result) {
    ApiFailure(:final problem) => ApiFailure(problem),
    ApiSuccess(:final data) => decodeApiRows<CalendarCaptureWindow>(data, (row) {
        if (row['coverage'] != 'not_captured' || row['status'] != 'confirmed') {
          throw const FormatException('unexpected calendar capture evidence');
        }
        final id = row['event_id'] as String;
        final start = DateTime.parse(row['start_time'] as String);
        final end = DateTime.parse(row['end_time'] as String);
        if (id.isEmpty || !end.isAfter(start)) throw const FormatException('invalid calendar capture bounds');
        return CalendarCaptureWindow(id, start, end);
      }, fallback: fallback ?? recordFallback),
  };
}
