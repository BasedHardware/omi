class ChatSession {
  final String id;
  String name;
  final DateTime createdAt;
  final DateTime lastMessageDate;
  final int messageCount;
  final String? pluginId;

  ChatSession({
    required this.id,
    required this.name,
    required this.createdAt,
    required this.lastMessageDate,
    required this.messageCount,
    this.pluginId, 
  });

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': name, 
    'created_at': createdAt.toIso8601String(),
    'updated_at': lastMessageDate.toIso8601String(), 
    'message_count': messageCount,
    'plugin_id': pluginId,
  };

  factory ChatSession.fromJson(Map<String, dynamic> json) {
    try {
      return ChatSession(
        id: json['id'] as String,
        name: json['title'] as String? ?? 'New Chat',  
        createdAt: DateTime.parse(json['created_at'] as String),
        lastMessageDate: DateTime.parse(json['updated_at'] as String), 
        messageCount: json['message_count'] as int? ?? 0,
        pluginId: json['plugin_id'] as String?, 
      );
    } catch (e) {
      return ChatSession(
        id: json['id'] as String,
        name: 'New Chat',
        createdAt: DateTime.now(),
        lastMessageDate: DateTime.now(),
        messageCount: 0,
      );
    }
  }

  @override
  String toString() {
    return 'ChatSession{id: $id, name: $name, createdAt: $createdAt, lastMessageDate: $lastMessageDate, messageCount: $messageCount, pluginId: $pluginId}';
  }
}