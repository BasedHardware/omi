import 'dart:async';

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

  /// The English title the server synthesizes on reads for an overdue hold:
  /// backend/utils/conversations/transcribing_hold.py `transcription_presentation` (~49), pinned by
  /// backend/tests/unit/test_transcription_pending_retry.py. The hold projection applies only to
  /// rows with no stored or user title, so on such a row this text is never a title someone gave it.
  static const serverHoldTitle = "Couldn't transcribe";

  /// Whether the status stands in for the title: the row is marked and its title is only
  /// [serverHoldTitle].
  static bool replacesTitle(ServerConversation conversation) =>
      contains(conversation.id) && conversation.structured.title.trim() == serverHoldTitle;

  static Timer? _expiry;

  static void mark(String id) => _publish({...ids.value, id: clock.now()});

  static void unmark(String id) {
    if (ids.value.containsKey(id)) _publish({...ids.value}..remove(id));
  }

  /// Publishes [next] and arms one timer for its earliest expiry, so surfaces rebuild when an
  /// answer lapses rather than at their next unrelated rebuild.
  static void _publish(Map<String, DateTime> next) {
    ids.value = next;
    _expiry?.cancel();
    _expiry = null;
    if (next.isEmpty) return;
    final earliest = next.values.reduce((a, b) => a.isBefore(b) ? a : b);
    final wait = earliest.add(ttl).difference(clock.now());
    _expiry = Timer(wait.isNegative ? Duration.zero : wait, () {
      final now = clock.now();
      _publish({...ids.value}..removeWhere((_, at) => now.difference(at) >= ttl));
    });
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
  static void reset() => _publish(const {});
}
