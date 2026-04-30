import 'package:hive/hive.dart';

/// Hive box names for the Chat tab.
///
/// Single box keyed by message id, holding the ordered conversation. v0 is
/// one global thread; multi-session support lands when `sessions.v1` shows up
/// next to this.
class ChatBoxes {
  ChatBoxes._();

  /// Persisted ChatMessage rows by id. Bounded to ~200 messages — provider
  /// trims older rows on write to keep cold-start hydrate fast.
  static const String messages = 'chat.messages.v1';

  /// Soft cap on message count. Older rows past this are dropped on write.
  static const int retentionLimit = 200;

  /// Wipes the chat thread. Called by the debug "Reset onboarding" flow so
  /// dev resets are total.
  static Future<void> clearAll() => Hive.box<Map>(messages).clear();
}
