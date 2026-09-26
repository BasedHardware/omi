import 'package:omi/backend/schema/conversation.dart';

/// Which device, or which import, a conversation came from (Rev 3 Conversations chips: All ·
/// Starred · Pendant · Glasses · Phone · Imported). The server filters by the stored `source`.
enum ConversationSourceFilter {
  all([]),
  pendant(['omi', 'friend', 'friend_com', 'sdcard']),
  glasses(['openglass', 'rayban_meta', 'frame']),
  phone(['phone', 'phone_call']),
  imported(['plaud', 'limitless', 'bee', 'fieldy', 'external_integration']);

  const ConversationSourceFilter(this.apiSources);

  /// The `sources` the list endpoint filters by; empty for [all].
  final List<String> apiSources;

  /// Whether [conversation] belongs here. A source this app version does not name (null) is kept:
  /// the server already chose it for this filter.
  bool matches(ServerConversation conversation) {
    if (this == all) return true;
    final source = conversation.source?.name;
    return source == null || apiSources.contains(source);
  }
}
