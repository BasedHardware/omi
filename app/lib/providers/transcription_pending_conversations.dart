import 'package:flutter/foundation.dart';

/// Conversations the server said are still awaiting transcription: a reprocess answered 409
/// `transcription_pending`. A summary retry cannot transcribe audio, so surfaces that would offer
/// "Retry" for these rows show a waiting status instead for the rest of the session.
class TranscriptionPendingConversations {
  TranscriptionPendingConversations._();

  static final ValueNotifier<Set<String>> ids = ValueNotifier<Set<String>>(const <String>{});

  static bool contains(String id) => ids.value.contains(id);

  static void mark(String id) {
    if (contains(id)) return;
    ids.value = {...ids.value, id};
  }

  @visibleForTesting
  static void reset() => ids.value = const <String>{};
}
