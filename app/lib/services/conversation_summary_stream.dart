// The streamed summary of a conversation (v3): `GET /v1/conversations/{id}/summary/stream` mapped to
// [SummaryStreamEvent]s. A 409 means another writer holds the summary; the caller polls instead.
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/streaming_error.dart';
import 'package:omi/backend/schema/conversation_v3_wire.dart';
import 'package:omi/env/env.dart';

/// `GET /v1/conversations/{id}/summary/stream`. Ends after [SummaryDone], [SummaryInProgress] or
/// [SummaryFailed]; never throws.
Stream<SummaryStreamEvent> streamConversationSummary(
  String conversationId, {
  ApiStreamingSeams? seams,
  Future<void>? cancelSignal,
}) async* {
  try {
    await for (final frame in makeStreamingApiCall(
      url: '${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}/summary/stream',
      method: 'GET',
      seams: seams,
      cancelSignal: cancelSignal,
    )) {
      final event = parseSummaryFrame(frame);
      if (event == null) continue;
      yield event;
      if (event is! SummarySection) return;
    }
    yield const SummaryFailed('stream_ended');
  } on ChatStreamException catch (e) {
    yield e.statusCode == 409 ? const SummaryInProgress() : SummaryFailed(e.kind.name);
  }
}
