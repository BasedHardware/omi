/// A server-owned chat thread. This is a list projection, not a second transcript store.
class ChatSessionSummary {
  const ChatSessionSummary(
      {required this.id, required this.title, required this.updatedAt, this.preview = '', this.messageCount = 0});

  final String id;
  final String title;
  final String preview;
  final DateTime updatedAt;
  final int messageCount;

  bool get hasTitle => title.trim().isNotEmpty && title.trim() != 'New Chat';
  bool get hasContent => messageCount > 0 || hasTitle || preview.trim().isNotEmpty;

  factory ChatSessionSummary.fromJson(Map<String, dynamic> json) {
    final id = json['id'];
    final date = json['updated_at'] ?? json['created_at'];
    final updated = date is String ? DateTime.tryParse(date) : null;
    if (id is! String || id.isEmpty || updated == null) throw const FormatException('Invalid chat session');
    return ChatSessionSummary(
      id: id,
      title: json['title'] is String ? json['title'] as String : '',
      preview: json['preview'] is String ? json['preview'] as String : '',
      updatedAt: updated.toLocal(),
      messageCount: json['message_count'] is num ? (json['message_count'] as num).toInt() : 0,
    );
  }
}
