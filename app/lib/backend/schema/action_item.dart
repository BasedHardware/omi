class ActionItemWithMetadata {
  final String id;
  final String conversationId;
  final String conversationTitle;
  final DateTime conversationCreatedAt;
  final int index;
  final String description;
  final bool completed;
  final bool deleted;

  ActionItemWithMetadata({
    required this.id,
    required this.conversationId,
    required this.conversationTitle,
    required this.conversationCreatedAt,
    required this.index,
    required this.description,
    required this.completed,
    required this.deleted,
  });

  factory ActionItemWithMetadata.fromJson(Map<String, dynamic> json) {
    return ActionItemWithMetadata(
      id: json['id'],
      conversationId: json['conversation_id'],
      conversationTitle: json['conversation_title'],
      conversationCreatedAt: DateTime.parse(json['conversation_created_at']),
      index: json['index'],
      description: json['description'],
      completed: json['completed'] ?? false,
      deleted: json['deleted'] ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'conversation_id': conversationId,
      'conversation_title': conversationTitle,
      'conversation_created_at': conversationCreatedAt.toIso8601String(),
      'index': index,
      'description': description,
      'completed': completed,
      'deleted': deleted,
    };
  }

  ActionItemWithMetadata copyWith({
    String? id,
    String? conversationId,
    String? conversationTitle,
    DateTime? conversationCreatedAt,
    int? index,
    String? description,
    bool? completed,
    bool? deleted,
  }) {
    return ActionItemWithMetadata(
      id: id ?? this.id,
      conversationId: conversationId ?? this.conversationId,
      conversationTitle: conversationTitle ?? this.conversationTitle,
      conversationCreatedAt: conversationCreatedAt ?? this.conversationCreatedAt,
      index: index ?? this.index,
      description: description ?? this.description,
      completed: completed ?? this.completed,
      deleted: deleted ?? this.deleted,
    );
  }
}

class ActionItemsResponse {
  final List<ActionItemWithMetadata> actionItems;
  final bool hasMore;

  ActionItemsResponse({
    required this.actionItems,
    required this.hasMore,
  });

  factory ActionItemsResponse.fromJson(Map<String, dynamic> json) {
    return ActionItemsResponse(
      actionItems: (json['action_items'] as List<dynamic>)
          .map((item) => ActionItemWithMetadata.fromJson(item))
          .toList(),
      hasMore: json['has_more'],
    );
  }
} 