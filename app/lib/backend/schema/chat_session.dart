class ChatSession {
  final String id;
  final List<String> messageIds;
  final List<String> fileIds;
  final String? appId;
  final String? pluginId;
  final DateTime createdAt;
  final String? title;
  final DateTime? updatedAt;

  ChatSession({
    required this.id,
    required this.messageIds,
    required this.fileIds,
    this.appId,
    this.pluginId,
    required this.createdAt,
    this.title,
    this.updatedAt,
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
      updatedAt: json['updated_at'] != null ? DateTime.parse(json['updated_at'] as String) : null,
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
      'updated_at': updatedAt?.toIso8601String(),
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
    DateTime? updatedAt,
  }) {
    return ChatSession(
      id: id ?? this.id,
      messageIds: messageIds ?? this.messageIds,
      fileIds: fileIds ?? this.fileIds,
      appId: appId ?? this.appId,
      pluginId: pluginId ?? this.pluginId,
      createdAt: createdAt ?? this.createdAt,
      title: title ?? this.title,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }

  /// Display title - shows "New Chat" until title is generated (after 3+ messages)
  String get displayTitle {
    if (title == null || title!.isEmpty) {
      return 'New Chat';
    }
    return title!;
  }

  /// Human-readable time ago string
  String get timeAgo {
    final now = DateTime.now();
    final diff = updatedAt != null ? now.difference(updatedAt!) : now.difference(createdAt);

    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    if (diff.inDays < 30) return '${(diff.inDays / 7).floor()}w ago';
    return '${(diff.inDays / 30).floor()}mo ago';
  }

  /// Get effective app ID (prefers plugin_id for backwards compat)
  String? get effectiveAppId => pluginId ?? appId;

  /// Check if this is an Omi session (no app)
  bool get isOmiSession => effectiveAppId == null || effectiveAppId!.isEmpty;
}
