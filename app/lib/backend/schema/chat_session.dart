class ChatSession {
  final String id;
  final List<String> messageIds;
  final List<String> fileIds;
  final String? appId;
  final String? pluginId;
  final DateTime createdAt;
  final String? title;

  ChatSession({
    required this.id,
    required this.messageIds,
    required this.fileIds,
    this.appId,
    this.pluginId,
    required this.createdAt,
    this.title,
  });

  factory ChatSession.fromJson(Map<String, dynamic> json) {
    return ChatSession(
      id: json['id'] as String,
      messageIds: List<String>.from(json['message_ids'] ?? []),
      fileIds: List<String>.from(json['file_ids'] ?? []),
      appId: json['app_id'] as String?,
      pluginId: json['plugin_id'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      title: json['title'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'message_ids': messageIds,
      'file_ids': fileIds,
      'app_id': appId,
      'plugin_id': pluginId,
      'created_at': createdAt.toIso8601String(),
      'title': title,
    };
  }

  ChatSession copyWith({
    String? id,
    List<String>? messageIds,
    List<String>? fileIds,
    String? appId,
    String? pluginId,
    DateTime? createdAt,
    String? title,
  }) {
    return ChatSession(
      id: id ?? this.id,
      messageIds: messageIds ?? this.messageIds,
      fileIds: fileIds ?? this.fileIds,
      appId: appId ?? this.appId,
      pluginId: pluginId ?? this.pluginId,
      createdAt: createdAt ?? this.createdAt,
      title: title ?? this.title,
    );
  }

  String get displayTitle {
    if (title == null || title!.isEmpty) {
      return 'New Chat';
    }
    // If title starts with "New Chat", show "New Chat" instead
    if (title!.startsWith('New Chat')) {
      return 'New Chat';
    }
    return title!;
  }
} 