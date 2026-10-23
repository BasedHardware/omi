import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/on_device/on_device_segment_upload.dart';

void main() {
  final segments = List.generate(
      1201,
      (i) => TranscriptSegment(
          id: '$i',
          text: 'synthetic',
          speaker: 'SPEAKER_${i % 2}',
          isUser: i.isEven,
          personId: i.isEven ? null : 'person',
          start: i.toDouble(),
          end: i + .5,
          translations: []));
  test('continuations retain every segment, speaker and timestamp under one stable session', () async {
    final sent = <Map<String, dynamic>>[];
    for (var retry = 0; retry < 2; retry++) {
      expect(
          await uploadOnDeviceSegments(
              baseUrl: 'http://localhost/',
              sessionId: 'session',
              segments: segments,
              metadata: {'started_at': '2026-01-01T00:00:00Z', 'finished_at': '2026-01-01T01:00:00Z'},
              chunked: true,
              canSend: () => true,
              send: (request) async {
                sent.add(jsonDecode(request.body) as Map<String, dynamic>);
                return http.Response('{"id":"conversation"}', 200);
              }),
          'conversation');
    }
    expect(sent.take(3).map((r) => (r['transcript_segments'] as List).length), [500, 500, 201]);
    expect(sent.map((r) => r['client_session_id']).toSet(), {'session'});
    expect(sent.map((r) => r['chunk_index']), [0, 1, 2, 0, 1, 2]);
    final combined = sent.take(3).expand((r) => r['transcript_segments'] as List).toList();
    expect(combined, segments.map((s) => s.toJson()).toList());
  });
  test('flag off keeps refusal, and failure never returns a completion', () async {
    await expectLater(
        uploadOnDeviceSegments(
            baseUrl: '', sessionId: 's', segments: segments, metadata: {}, chunked: false, canSend: () => true),
        throwsStateError);
    var calls = 0;
    await expectLater(
        uploadOnDeviceSegments(
            baseUrl: 'http://localhost/',
            sessionId: 's',
            segments: segments,
            metadata: {},
            chunked: true,
            canSend: () => true,
            send: (_) async {
              calls++;
              return http.Response('{}', 409);
            }),
        throwsStateError);
    expect(calls, 1);
  });
  test('account cancellation stops the next chunk', () async {
    var current = true, calls = 0;
    await expectLater(
        uploadOnDeviceSegments(
            baseUrl: 'http://localhost/',
            sessionId: 's',
            segments: segments,
            metadata: {},
            chunked: true,
            canSend: () => current,
            send: (_) async {
              calls++;
              current = false;
              return http.Response('{"id":"c"}', 200);
            }),
        throwsStateError);
    expect(calls, 1);
  });
}
