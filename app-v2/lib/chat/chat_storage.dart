import 'package:hive/hive.dart';

/// Hive box names for the Chat tab.
///
/// Two boxes:
///   * [messages] — `ChatMessage` rows by id, partitioned at read time by
///     `sessionId` (provider keeps an in-memory `Map<sessionId, List<msg>>`).
///   * [sessions] — `ChatSession` rows by id (drawer source of truth).
class ChatBoxes {
  ChatBoxes._();

  /// Persisted ChatMessage rows by id. Bounded to ~200 messages — provider
  /// trims older rows on write to keep cold-start hydrate fast.
  static const String messages = 'chat.messages.v1';

  /// Persisted ChatSession rows by id. Drawer renders from this directly.
  static const String sessions = 'chat.sessions.v1';

  /// Soft cap on message count. Older rows past this are dropped on write.
  static const int retentionLimit = 200;

  /// Wipes every chat thread and session. Called by the debug "Reset
  /// onboarding" flow so dev resets are total.
  static Future<void> clearAll() async {
    await Hive.box<Map>(messages).clear();
    await Hive.box<Map>(sessions).clear();
  }
}
