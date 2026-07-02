import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;

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
  final String? appleReminderId;
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
    this.appleReminderId,
    this.sortOrder = 0,
    this.indentLevel = 0,
  });

  factory ActionItemWithMetadata.fromJson(Map<String, dynamic> json) {
    return ActionItemWithMetadata.fromGenerated(wire.GeneratedActionItemResponse.fromJson(json));
  }

  factory ActionItemWithMetadata.fromGenerated(wire.GeneratedActionItemResponse generated) {
    return ActionItemWithMetadata(
      id: generated.id,
      description: generated.description,
      completed: generated.completed,
      createdAt: generated.createdAt,
      updatedAt: generated.updatedAt,
      dueAt: generated.dueAt,
      completedAt: generated.completedAt,
      conversationId: generated.conversationId,
      isLocked: generated.isLocked ?? false,
      exported: generated.exported ?? false,
      exportDate: generated.exportDate,
      exportPlatform: generated.exportPlatform,
      appleReminderId: generated.appleReminderId,
      sortOrder: generated.sortOrder ?? 0,
      indentLevel: generated.indentLevel ?? 0,
    );
  }

  wire.GeneratedActionItemResponse toGenerated() {
    return wire.GeneratedActionItemResponse(
      id: id,
      description: description,
      completed: completed,
      createdAt: createdAt,
      updatedAt: updatedAt,
      dueAt: dueAt,
      completedAt: completedAt,
      conversationId: conversationId,
      isLocked: isLocked,
      exported: exported,
      exportDate: exportDate,
      exportPlatform: exportPlatform,
      appleReminderId: appleReminderId,
      sortOrder: sortOrder,
      indentLevel: indentLevel,
    );
  }

  Map<String, dynamic> toJson() {
    return toGenerated().toJson();
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
    String? appleReminderId,
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
      appleReminderId: appleReminderId ?? this.appleReminderId,
      sortOrder: sortOrder ?? this.sortOrder,
      indentLevel: indentLevel ?? this.indentLevel,
    );
  }
}

class ActionItemsResponse {
  final List<ActionItemWithMetadata> actionItems;
  final bool hasMore;

  ActionItemsResponse({required this.actionItems, required this.hasMore});

  factory ActionItemsResponse.fromJson(Map<String, dynamic> json) {
    return ActionItemsResponse.fromGenerated(wire.GeneratedActionItemsResponse.fromJson(json));
  }

  factory ActionItemsResponse.fromGenerated(wire.GeneratedActionItemsResponse generated) {
    return ActionItemsResponse(
      actionItems: generated.actionItems.map(ActionItemWithMetadata.fromGenerated).toList(),
      hasMore: generated.hasMore,
    );
  }
}

class PendingSyncResponse {
  final List<ActionItemWithMetadata> pendingExport;
  final List<ActionItemWithMetadata> syncedItems;

  PendingSyncResponse({required this.pendingExport, required this.syncedItems});

  factory PendingSyncResponse.fromJson(Map<String, dynamic> json) {
    return PendingSyncResponse.fromGenerated(wire.GeneratedPendingSyncResponse.fromJson(json));
  }

  factory PendingSyncResponse.fromGenerated(wire.GeneratedPendingSyncResponse generated) {
    return PendingSyncResponse(
      pendingExport: generated.pendingExport.map(ActionItemWithMetadata.fromGenerated).toList(),
      syncedItems: generated.syncedItems.map(ActionItemWithMetadata.fromGenerated).toList(),
    );
  }
}
