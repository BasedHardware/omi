// Reliability experiment `fast_end_feedback`: after a conversation is ended, waiting requests bring the
// outline, then the summary.

import 'dart:async';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/utils/reliability_experiments.dart';

/// After a conversation is ended (End Conversation, Finish, Wrap Up, the record button's stop or a
/// pendant double-tap), asks the server for it twice, each time with a request the server holds until
/// that step is reached: first "when it is committed with its outline" (title, emoji and one-liner,
/// summary still being written), then "when its summary is stored". Each answer is handed to [apply],
/// instead of leaving the app to find it on a later poll.
///
/// The server applies some Ends late: with a listening session open and audio travelling as uploads,
/// the conversation stays live until the session's own recording is transcribed (about a minute in a
/// local run). So the outline request is repeated while the answer is still live, up to
/// [outlineAttempts] held requests, and the summary request up to [summaryAttempts].
///
/// It owns no polling and changes nothing on screen by itself. One run per conversation at a time.
/// Only an answer that carries news is applied: the conversation left live, or its summary is stored.
/// A request that fails, or a server that does not hold the request, ends the run; the app's existing
/// polls carry on as before, so the baseline behaviour is the fallback. Off, [start] does nothing.
class SummaryWaitAfterEnd {
  SummaryWaitAfterEnd({
    required this.apply,
    required this.active,
    this.wait = waitForConversationSummary,
    this.outlineAttempts = 6,
    this.summaryAttempts = 3,
    this.heldAtLeast = const Duration(seconds: 2),
    bool Function()? enabled,
  }) : _enabled = enabled ?? (() => ReliabilityExperiments.enabled(experiment));

  static const experiment = 'fast_end_feedback';

  /// Held requests (about 20 s each) spent waiting for the conversation to leave live.
  final int outlineAttempts;

  /// Held requests spent waiting for the summary once the conversation left live.
  final int summaryAttempts;

  /// A "still live" answer that came back sooner than this was not held by the server (an older
  /// server, or the experiment off there): asking again would only spin.
  final Duration heldAtLeast;

  final Future<({ConversationByIdResult result, bool settled})> Function(String conversationId, {bool untilOutline})
      wait;

  /// Takes a returned conversation; [settled] is true only when its summary is stored (or failed).
  final Future<void> Function(String conversationId, ConversationByIdResult result, {required bool settled}) apply;

  /// Whether an answer for [conversationId] can still be used.
  final bool Function(String conversationId) active;
  final bool Function() _enabled;

  final Set<String> _waiting = {};

  bool isWaiting(String conversationId) => _waiting.contains(conversationId);

  /// Returns whether a request was started.
  bool start(String? conversationId) {
    if (conversationId == null || !_enabled() || !_waiting.add(conversationId)) return false;
    unawaited(_run(conversationId));
    return true;
  }

  static bool _stillLive(ConversationByIdResult result) => result.item?.v3?.tileState == ConversationTileState.live;

  Future<void> _run(String conversationId) async {
    try {
      // The outline step: until the conversation leaves live.
      ({ConversationByIdResult result, bool settled})? outline;
      for (var attempt = 0; attempt < outlineAttempts; attempt++) {
        final asked = Stopwatch()..start();
        final answer = await wait(conversationId, untilOutline: true);
        if (!active(conversationId) || answer.result.item == null) return;
        if (!_stillLive(answer.result)) {
          outline = answer;
          break;
        }
        if (asked.elapsed < heldAtLeast) return;
      }
      if (outline == null) return;
      await apply(conversationId, outline.result, settled: outline.settled);
      // The outline step already found the summary stored: nothing left to wait for.
      if (outline.settled) return;
      // The summary step.
      for (var attempt = 0; attempt < summaryAttempts; attempt++) {
        final answer = await wait(conversationId, untilOutline: false);
        if (!active(conversationId) || answer.result.item == null) return;
        if (answer.settled) return apply(conversationId, answer.result, settled: true);
      }
    } catch (_) {
      // The app's own polls are the fallback.
    } finally {
      _waiting.remove(conversationId);
    }
  }
}
