import 'package:clock/clock.dart';
import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/conversation.dart';

/// A short-lived memory of the one server answer the conversation copy itself cannot carry: a
/// reprocess answered 409 `transcription_pending` (audio past its transcription deadline and never
/// transcribed). Surfaces that would offer a summary "Retry" for such a row show a plain status
/// instead, because a summary retry cannot transcribe audio.
///
/// Everything else comes from the server copy: a reprocess that answers 200 with Home step
/// `transcribing` is applied as that copy, and a row whose copy shows the transcript exists (or a
/// settled Home step, or a retryable summary) is cleared here. The memory also expires after
/// [ttl], so a stale answer can never hide a retry for long; a later 409 simply records it again.
class TranscriptionPendingConversations {
  TranscriptionPendingConversations._();

  static const Duration ttl = Duration(minutes: 10);

  /// Conversation id -> when the server last said its audio is not transcribed.
  static final ValueNotifier<Map<String, DateTime>> ids = ValueNotifier<Map<String, DateTime>>(const {});

  static bool contains(String id) {
    final at = ids.value[id];
    return at != null && clock.now().difference(at) < ttl;
  }

  static void mark(String id) => ids.value = {...ids.value, id: clock.now()};

  static void unmark(String id) {
    if (!ids.value.containsKey(id)) return;
    ids.value = {...ids.value}..remove(id);
  }

  /// Clears the status when an applied copy proves transcription is no longer pending. A copy with
  /// no Home step and no transcript (the list omits transcripts; the detail copy omits the Home
  /// step) proves nothing, so the status stays.
  static void observe(ServerConversation conversation) {
    final step = conversation.homeStep;
    if ((step != null && step != 'failed') ||
        conversation.transcriptSegments.isNotEmpty ||
        conversation.summaryRetryable) {
      unmark(conversation.id);
    }
  }

  @visibleForTesting
  static void reset() => ids.value = const {};
}
