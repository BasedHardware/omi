import 'package:omi/backend/schema/gen/chat_sessions_wire.g.dart' as wire;

/// A server-owned chat thread. This is a list projection, not a second transcript store.
class ChatSessionSummary {
  const ChatSessionSummary(
      {required this.id,
      required this.title,
      required this.updatedAt,
      this.preview = '',
      this.messageCount = 0,
      this.channel,
      this.channelLinkId});

  final String id;
  final String title;
  final String preview;
  final DateTime updatedAt;
  final int messageCount;

  /// The chat app this session lives in (`telegram`, `imessage`), or null for an Omi app chat.
  /// Channel sessions are read-only here: their replies go back to that app.
  final String? channel;

  /// The chat-app link that owns this session; set together with [channel].
  final String? channelLinkId;

  bool get isChannelSession => channelLinkId != null;

  bool get hasTitle => title.trim().isNotEmpty && title.trim() != 'New Chat';
  bool get hasContent => messageCount > 0 || hasTitle || preview.trim().isNotEmpty;

  /// The app's view of a generated `ChatSessionResponse`. Times are shown in the reader's zone.
  factory ChatSessionSummary.fromGenerated(wire.GeneratedChatSessionResponse generated,
      {String? channel, String? channelLinkId}) {
    return ChatSessionSummary(
      id: generated.id,
      title: generated.title,
      preview: generated.preview ?? '',
      updatedAt: generated.updatedAt.toLocal(),
      messageCount: generated.messageCount,
      channel: channelLinkId == null ? null : channel,
      channelLinkId: channelLinkId,
    );
  }

  /// Decodes one `ChatSessionResponse` row through the generated wire type.
  ///
  /// The contract makes every timestamp, count and flag required, but rows written before the
  /// session store settled (and the create route's first answer) can omit them. Those rows were
  /// always shown, so they still are: `updated_at` falls back to `created_at`, a missing or
  /// mistyped title/preview reads as empty, a missing count as 0 and a missing star as unstarred.
  /// An id and one parseable timestamp remain required — without them the row cannot be listed.
  ///
  /// `channel` and `channel_link_id` are read when present: the session list includes a chat
  /// app's sessions only after the person turns on "Show these chats in the Omi app".
  factory ChatSessionSummary.fromJson(Map<String, dynamic> json) {
    final channel = json['channel'];
    final linkId = json['channel_link_id'];
    return ChatSessionSummary.fromGenerated(
      wire.GeneratedChatSessionResponse.fromJson(legacyTolerantRow(json)),
      channel: channel is String && channel.isNotEmpty ? channel : null,
      channelLinkId: linkId is String && linkId.isNotEmpty ? linkId : null,
    );
  }

  /// [json] with the contract's required fields filled the way this client always read them.
  /// Throws [FormatException] for a row that has no id or no parseable timestamp.
  static Map<String, dynamic> legacyTolerantRow(Map<String, dynamic> json) {
    final id = json['id'];
    final date = json['updated_at'] ?? json['created_at'];
    if (id is! String || id.isEmpty || date is! String || DateTime.tryParse(date) == null) {
      throw const FormatException('Invalid chat session');
    }
    final created = json['created_at'];
    final count = json['message_count'];
    final appId = json['app_id'];
    final pluginId = json['plugin_id'];
    return {
      'id': id,
      'updated_at': date,
      'created_at': created is String && DateTime.tryParse(created) != null ? created : date,
      'title': json['title'] is String ? json['title'] : '',
      'preview': json['preview'] is String ? json['preview'] : null,
      'message_count': count is num ? count.toInt() : 0,
      'starred': json['starred'] is bool ? json['starred'] : false,
      'app_id': appId is String ? appId : null,
      'plugin_id': pluginId is String ? pluginId : null,
    };
  }
}
