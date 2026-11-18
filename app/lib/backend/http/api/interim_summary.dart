// Client for the Quick Summary stream, POST /v1/conversations/{id}/interim-summary (SSE).
// Owns the request and the frame parsing (events: backend/schema/interim_summary_event.dart): nothing
// here is persisted, and failures reach the caller as an error event or a stream error, never silence.
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/interim_summary_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';

export 'package:omi/backend/schema/interim_summary_event.dart';

/// Splits an SSE byte stream into events. Exposed for tests.
///
/// A malformed `data:` payload is a decode failure: it ends the stream with an error, which the
/// caller shows as its fallback state (API_RESULTS.md: never turn a failure into silence).
Stream<InterimSummaryEvent> parseInterimSummaryStream(Stream<List<int>> bytes) async* {
  await for (final line in bytes.transform(utf8.decoder).transform(const LineSplitter())) {
    if (!line.startsWith('data: ')) continue;
    final decoded = jsonDecode(line.substring(6));
    if (decoded is! Map<String, dynamic>) continue;
    final event = InterimSummaryEvent.fromFrame(decoded);
    if (event != null) yield event;
  }
}

/// Streams a short preview summary of [segments] (the transcript this phone already holds).
///
/// A non-200 answer is an [InterimSummaryError] event; transport and decode failures propagate as
/// stream errors.
Stream<InterimSummaryEvent> streamInterimSummary({
  required String conversationId,
  required List<TranscriptSegment> segments,
  DateTime? startedAt,
  String? timezone,
  http.Client? client,
}) async* {
  final owned = client == null;
  final httpClient = client ?? http.Client();
  try {
    final url = Uri.parse('${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}/interim-summary');
    final request = http.Request('POST', url)
      ..headers.addAll(await buildHeaders(requireAuthCheck: true, url: url.toString(), method: 'POST'))
      ..headers['Content-Type'] = 'application/json'
      ..headers['Accept'] = 'text/event-stream'
      ..body = jsonEncode({
        'segments': [
          for (final segment in segments)
            {
              'text': segment.text,
              'speaker': segment.speaker,
              'is_user': segment.isUser,
              'start': segment.start,
              'end': segment.end,
            },
        ],
        if (startedAt != null) 'started_at': startedAt.toIso8601String(),
        if (timezone != null) 'timezone': timezone,
      });
    final response = await httpClient.send(request);
    if (response.statusCode != 200) {
      yield InterimSummaryError('HTTP ${response.statusCode}');
      return;
    }
    yield* parseInterimSummaryStream(response.stream);
  } finally {
    if (owned) httpClient.close();
  }
}
