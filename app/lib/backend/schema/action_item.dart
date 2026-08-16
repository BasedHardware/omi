import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;

// Phase 4.1 — pure 1:1 thin wrappers over generated wire types.
//
// Every field (including nullability) matches the generated type exactly, and the
// only extra surface was a fromGenerated/toGenerated/fromJson/toJson passthrough and
// an unused copyWith. They are deleted in favour of typedefs; GeneratedX.fromJson
// already provides JSON decoding and GeneratedX.toJson provides serialization.

typedef ActionItemWithMetadata = wire.GeneratedActionItemResponse;
typedef ActionItemsResponse = wire.GeneratedActionItemsResponse;
typedef PendingSyncResponse = wire.GeneratedPendingSyncResponse;

const Object _actionItemCopyWithUnset = Object();

/// copyWith for [ActionItemWithMetadata]; preserved from the deleted hand-written
/// class because the provider mutates items in place via this method.
extension ActionItemWithMetadataCopyWith on wire.GeneratedActionItemResponse {
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
    double? dueConfidence,
    Object? goalId = _actionItemCopyWithUnset,
    Object? workstreamId = _actionItemCopyWithUnset,
    String? owner,
    String? source,
    String? status,
    String? priority,
    List<wire.GeneratedEvidenceRef>? provenance,
    String? recurrenceRule,
    String? recurrenceParentId,
    String? supersededBy,
    String? taskId,
  }) {
    return wire.GeneratedActionItemResponse(
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
      dueConfidence: dueConfidence ?? this.dueConfidence,
      goalId: identical(goalId, _actionItemCopyWithUnset) ? this.goalId : goalId as String?,
      workstreamId: identical(workstreamId, _actionItemCopyWithUnset) ? this.workstreamId : workstreamId as String?,
      owner: owner ?? this.owner,
      source: source ?? this.source,
      status: status ?? this.status,
      priority: priority ?? this.priority,
      provenance: provenance ?? this.provenance,
      recurrenceRule: recurrenceRule ?? this.recurrenceRule,
      recurrenceParentId: recurrenceParentId ?? this.recurrenceParentId,
      supersededBy: supersededBy ?? this.supersededBy,
      taskId: taskId ?? this.taskId,
    );
  }
}
