import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/calendar_capture_telemetry.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/services/capture/calendar_capture_gap_monitor.dart';

void main() {
  final start = DateTime.utc(2026, 10, 7, 10);
  final end = start.add(const Duration(hours: 1));
  Map<String, Object> row() => {
        'event_id': 'accepted',
        'coverage': 'not_captured',
        'status': 'confirmed',
        'start_time': start.toIso8601String(),
        'end_time': end.toIso8601String()
      };
  Future<ApiResult<List<CalendarCaptureWindow>>> fetch(String body,
          {int status = 200, void Function(ApiFallbackEvent)? fallback}) =>
      fetchCalendarCaptureWindows(start, end, baseUrl: 'https://calendar.invalid/', send: (request) async {
        expect(request.method, 'GET');
        final uri = Uri.parse(request.url);
        expect(uri.path, '/v1/calendar/capture-gaps');
        expect(uri.queryParameters['start'], start.toIso8601String());
        expect(uri.queryParameters['end'], end.toIso8601String());
        return http.Response(body, status);
      }, fallback: fallback);
  test('accepted active event decodes without requiring its title', () async {
    final result = await fetch(jsonEncode([row()]));
    expect(result, isA<ApiSuccess<List<CalendarCaptureWindow>>>());
    final window = (result as ApiSuccess<List<CalendarCaptureWindow>>).data.single;
    expect(window.start, start);
    expect(window.end, end);
  });
  test('empty success is distinct from unavailable evidence', () async {
    expect((await fetch('[]') as ApiSuccess<List<CalendarCaptureWindow>>).data, isEmpty);
    expect(
        await fetch('', status: 500),
        isA<ApiFailure<List<CalendarCaptureWindow>>>()
            .having((result) => result.problem.kind, 'kind', ApiProblemKind.server));
  });
  test('missing integration remains an explicit HTTP failure', () async {
    expect(
        await fetch('', status: 404),
        isA<ApiFailure<List<CalendarCaptureWindow>>>()
            .having((result) => result.problem.kind, 'kind', ApiProblemKind.notFound));
  });
  test('partial decode preserves valid evidence and reports a bounded fallback', () async {
    final events = <ApiFallbackEvent>[];
    final result = await fetch(
        jsonEncode([
          row(),
          {'title': 'private meeting content'}
        ]),
        fallback: events.add) as ApiSuccess<List<CalendarCaptureWindow>>;
    expect(result.data, hasLength(1));
    expect(result.rejectedRows, 1);
    expect(events, hasLength(1));
    expect(events.single.toFields().keys, isNot(contains('title')));
  });
  test('malformed calendar bounds never imply an active meeting', () async {
    final bad = row()..['end_time'] = start.toIso8601String();
    expect(
        await fetch(jsonEncode([bad])),
        isA<ApiFailure<List<CalendarCaptureWindow>>>()
            .having((result) => result.problem.kind, 'kind', ApiProblemKind.decode));
  });
}
