// The streamed summary of a conversation (v3): `GET /v1/conversations/{id}/summary/stream` mapped to
// [SummaryStreamEvent]s. A 409 means another writer holds the summary; the caller polls instead.
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/streaming_error.dart';
import 'package:omi/backend/schema/conversation_v3_wire.dart';
import 'package:omi/env/env.dart';

enum LiveRecapTrigger {
  firstOpen('first_open'),
  retry('retry'),
  timedRefresh('timed_refresh');

  const LiveRecapTrigger(this.wire);
  final String wire;
}

typedef LiveRecapRequest = ({LiveRecapTrigger trigger, String requestId, String intervalId});

/// Streams final notes, or a live catch-up after an explicit tap. Ends after [SummaryDone], [SummaryInProgress] or
/// [SummaryFailed]; never throws.
Stream<SummaryStreamEvent> streamConversationSummary(
  String conversationId, {
  ApiStreamingSeams? seams,
  LiveRecapRequest? recap,
  Future<void>? cancelSignal,
  bool Function()? canDispatch,
}) async* {
  final liveCatchup = recap != null;
  if (liveCatchup && canDispatch == null) {
    yield const SummaryFailed('missing_live_dispatch_guard');
    return;
  }
  try {
    await for (final frame in makeStreamingApiCall(
      url: '${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}'
          '/summary/${liveCatchup ? 'live-catchup/' : ''}stream',
      method: 'GET',
      headers: recap != null
          ? {
              'X-Omi-Recap-Trigger': recap.trigger.wire,
              'X-Omi-Recap-Request': recap.requestId,
              'X-Omi-Recap-Interval': recap.intervalId,
              // The caller revalidates both facts immediately before a send or auth replay.
              'X-Omi-Recap-Foreground': 'true',
              'X-Omi-Recap-Speech-Eligible': 'true',
            }
          : const {'X-Omi-Recording-Detail': '1'},
      seams: seams,
      cancelSignal: cancelSignal,
      canDispatch: canDispatch,
    )) {
      final event = parseSummaryFrame(frame);
      if (event == null) continue;
      yield event;
      if (event is! SummarySection) return;
    }
    yield const SummaryFailed('stream_ended');
  } on ChatStreamException catch (e) {
    yield switch (e) {
      ChatStreamException(statusCode: 409) => const SummaryInProgress(),
      ChatStreamException(statusCode: 404, detail: 'live_recap_unavailable') when liveCatchup =>
        const SummaryFailed('live_recap_unavailable'),
      _ => SummaryFailed(e.kind.name),
    };
  }
}
