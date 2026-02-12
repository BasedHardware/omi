class ActionItemWithMetadata {
  final String id;
  final String description;
  final bool completed;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? dueAt;
  final DateTime? completedAt;
  final String? conversationId;
  final bool isLocked;
  final bool exported;
  final DateTime? exportDate;
  final String? exportPlatform;
  final int sortOrder;
  final int indentLevel;

  ActionItemWithMetadata({
    required this.id,
    required this.description,
    required this.completed,
    this.createdAt,
    this.updatedAt,
    this.dueAt,
    this.completedAt,
    this.conversationId,
    this.isLocked = false,
    this.exported = false,
    this.exportDate,
    this.exportPlatform,
    this.sortOrder = 0,
    this.indentLevel = 0,
  });

  factory ActionItemWithMetadata.fromJson(Map<String, dynamic> json) {
    return ActionItemWithMetadata(
      id: json['id'],
      description: json['description'],
      completed: json['completed'] ?? false,
      createdAt: json['created_at'] != null ? DateTime.parse(json['created_at']).toLocal() : null,
      updatedAt: json['updated_at'] != null ? DateTime.parse(json['updated_at']).toLocal() : null,
      dueAt: json['due_at'] != null ? DateTime.parse(json['due_at']).toLocal() : null,
      completedAt: json['completed_at'] != null ? DateTime.parse(json['completed_at']).toLocal() : null,
      conversationId: json['conversation_id'],
      isLocked: json['is_locked'] ?? false,
      exported: json['exported'] ?? false,
      exportDate: json['export_date'] != null ? DateTime.parse(json['export_date']).toLocal() : null,
      exportPlatform: json['export_platform'],
      sortOrder: json['sort_order'] as int? ?? 0,
      indentLevel: json['indent_level'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'description': description,
      'completed': completed,
      'created_at': createdAt?.toUtc().toIso8601String(),
      'updated_at': updatedAt?.toUtc().toIso8601String(),
      'due_at': dueAt?.toUtc().toIso8601String(),
      'completed_at': completedAt?.toUtc().toIso8601String(),
      'conversation_id': conversationId,
      'is_locked': isLocked,
      'exported': exported,
      'export_date': exportDate?.toUtc().toIso8601String(),
      'export_platform': exportPlatform,
      'sort_order': sortOrder,
      'indent_level': indentLevel,
    };
  }

  ActionItemWithMetadata copyWith({
    String? id,
    String? description,
    bool? completed,
    DateTime? createdAt,
    DateTime? updatedAt,
    DateTime? dueAt,
    DateTime? completedAt,
    String? conversationId,
    bool? isLocked,
    bool? exported,
    DateTime? exportDate,
    String? exportPlatform,
    int? sortOrder,
    int? indentLevel,
  }) {
    return ActionItemWithMetadata(
      id: id ?? this.id,
      description: description ?? this.description,
      completed: completed ?? this.completed,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      dueAt: dueAt ?? this.dueAt,
      completedAt: completedAt ?? this.completedAt,
      conversationId: conversationId ?? this.conversationId,
      isLocked: isLocked ?? this.isLocked,
      exported: exported ?? this.exported,
      exportDate: exportDate ?? this.exportDate,
      exportPlatform: exportPlatform ?? this.exportPlatform,
      sortOrder: sortOrder ?? this.sortOrder,
      indentLevel: indentLevel ?? this.indentLevel,
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
      actionItems:
          (json['action_items'] as List<dynamic>).map((item) => ActionItemWithMetadata.fromJson(item)).toList(),
      hasMore: json['has_more'],
    );
  }
}
