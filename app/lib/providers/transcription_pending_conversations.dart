import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/conversation.dart';

/// Conversations the server said have audio that is not transcribed: a reprocess answered 409
/// `transcription_pending`. A summary retry cannot transcribe audio, so surfaces that would offer
/// "Retry" for these rows listen here and show a plain status instead. An id leaves the set when a
/// reprocess succeeds or an applied copy explicitly carries a non-failed Home step.
class TranscriptionPendingConversations {
  TranscriptionPendingConversations._();

  static final ValueNotifier<Set<String>> ids = ValueNotifier<Set<String>>(const <String>{});

  static bool contains(String id) => ids.value.contains(id);

  static void mark(String id) {
    if (contains(id)) return;
    ids.value = {...ids.value, id};
  }

  static void unmark(String id) {
    if (!contains(id)) return;
    ids.value = {...ids.value}..remove(id);
  }

  /// Clears the status only when an applied copy explicitly carries a non-failed Home step. A copy
  /// without `home_step` (the detail endpoint omits it) is not evidence that the row settled.
  static void observe(ServerConversation conversation) {
    final step = conversation.homeStep;
    if (step != null && step != 'failed') unmark(conversation.id);
  }

  @visibleForTesting
  static void reset() => ids.value = const <String>{};
}
