import 'package:omi/backend/schema/gen/memories_wire.g.dart' as wire;

enum MemoryCategory { system, interesting, manual, workflow }

enum MemoryVisibility { private, public, shared }

/// Semantic row kind used by the intent-backed `knowledge_ledger.v1` contract.
enum KnowledgeLedgerKind {
  fact('fact'),
  document('document'),
  trigger('trigger');

  const KnowledgeLedgerKind(this.apiValue);
  final String apiValue;

  static KnowledgeLedgerKind? tryParse(String? raw) {
    if (raw == null) return null;
    for (final kind in KnowledgeLedgerKind.values) {
      if (kind.apiValue == raw) return kind;
    }
    return null;
  }
}

/// Canonical product lifecycle layer (WS-G/Wave 36). Same string values as API `layer` / `memory_tier`.
enum MemoryLayer {
  shortTerm('short_term'),
  longTerm('long_term'),
  archive('archive');

  const MemoryLayer(this.apiValue);
  final String apiValue;

  static MemoryLayer? tryParse(String? raw) {
    if (raw == null) return null;
    for (final layer in MemoryLayer.values) {
      if (layer.apiValue == raw) return layer;
    }
    return null;
  }

  /// Reversible alias during WS-G client rename (Wave 36).
  static MemoryLayer? tierTryParse(String? raw) => tryParse(raw);
}

// Maps legacy category strings to new categories
MemoryCategory _parseMemoryCategory(String? category) {
  if (category == null) return MemoryCategory.system;
  if (category == 'manual') return MemoryCategory.manual;
  if (category == 'interesting') return MemoryCategory.interesting;
  if (category == 'system') return MemoryCategory.system;
  if (category == 'workflow') return MemoryCategory.workflow;
  // Legacy categories map to system (facts about user)
  if (['core', 'hobbies', 'lifestyle', 'interests', 'work', 'skills', 'habits', 'other'].contains(category)) {
    return MemoryCategory.system;
  }
  // 'learnings' and 'auto' map to system as well
  return MemoryCategory.system;
}

// Phase 4.1 — Memory is kept as a deliberate adapter, not a typedef: it exposes Dart
// enums (MemoryCategory/MemoryVisibility/MemoryLayer) absent from GeneratedMemoryDB,
// normalizes layer/tier aliases in fromJson, and emits a bespoke toJson. The enums and
// helpers above are client-only and also stay.

class Memory {
  String id;
  String uid;
  String content;
  MemoryCategory category;
  DateTime createdAt;
  DateTime updatedAt;
  String? conversationId;
  bool reviewed;
  bool? userReview;
  bool manuallyAdded;
  bool edited;
  bool deleted;
  MemoryVisibility visibility;
  bool isLocked;
  bool isBaseline;
  final MemoryLayer? layer;
  final bool layerIsExplicit;
  final String? primaryCaptureDevice;
  final List<String> captureDeviceIds;
  final String? ledgerSchemaVersion;
  final KnowledgeLedgerKind? ledgerKind;
  final String? ledgerBody;
  final String? ledgerSlot;
  final String? subjectScope;
  final String? subjectEntityId;
  final String? supersededBy;
  final DateTime? invalidAt;
  final DateTime? validAt;
  final bool intentBacked;
  final int curationWeight;
  final Map<String, dynamic> triggerCondition;
  final String? writeReason;
  final List<Map<String, dynamic>> evidence;

  Memory({
    required this.id,
    required this.uid,
    required this.content,
    required this.category,
    required this.createdAt,
    required this.updatedAt,
    this.conversationId,
    this.reviewed = false,
    this.userReview,
    this.manuallyAdded = false,
    this.edited = false,
    this.deleted = false,
    required this.visibility,
    this.isLocked = false,
    this.isBaseline = false,
    this.layer,
    this.layerIsExplicit = false,
    this.primaryCaptureDevice,
    this.captureDeviceIds = const [],
    this.ledgerSchemaVersion,
    this.ledgerKind,
    this.ledgerBody,
    this.ledgerSlot,
    this.subjectScope,
    this.subjectEntityId,
    this.supersededBy,
    this.invalidAt,
    this.validAt,
    this.intentBacked = false,
    this.curationWeight = 0,
    this.triggerCondition = const {},
    this.writeReason,
    this.evidence = const [],
  });

  bool get isKnowledgeLedger => ledgerSchemaVersion == 'knowledge_ledger.v1' && ledgerKind != null;

  bool get isCurrentKnowledgeLedgerRow =>
      isKnowledgeLedger &&
      intentBacked &&
      !deleted &&
      invalidAt == null &&
      (supersededBy == null || supersededBy!.trim().isEmpty) &&
      userReview != false;

  bool get isHistoricalKnowledgeLedgerRow => isKnowledgeLedger && !isCurrentKnowledgeLedgerRow;

  bool get isLedgerPlaybook => isKnowledgeLedger && ledgerKind == KnowledgeLedgerKind.document;

  bool get isLedgerTrigger => isKnowledgeLedger && ledgerKind == KnowledgeLedgerKind.trigger;

  factory Memory.fromJson(Map<String, dynamic> json) {
    return Memory.fromGeneratedWireJson(json);
  }

  factory Memory.fromGeneratedWireJson(Map<String, dynamic> json) {
    final normalizedJson = Map<String, dynamic>.from(json);
    final rawLayer = normalizedJson['layer'] as String?;
    final rawTier = normalizedJson['tier'] as String?;
    final rawMemoryTier = normalizedJson['memory_tier'] as String?;
    normalizedJson['layer'] ??= rawTier ?? rawMemoryTier ?? MemoryLayer.longTerm.apiValue;
    normalizedJson['memory_tier'] ??= rawTier ?? rawLayer ?? MemoryLayer.longTerm.apiValue;

    final generated = wire.GeneratedMemoryDB.fromJson(normalizedJson);
    final rawLayerValue = MemoryLayer.tryParse(rawLayer);
    final layerValue = MemoryLayer.tryParse(generated.layer);
    final tierValue = MemoryLayer.tryParse(rawTier);
    final memoryTierValue = MemoryLayer.tryParse(rawMemoryTier);
    final layerIsExplicit = rawLayerValue != null || tierValue != null || memoryTierValue != null;
    final resolvedLayer = layerValue ?? tierValue ?? memoryTierValue ?? MemoryLayer.longTerm;

    return Memory(
      id: generated.id,
      uid: generated.uid,
      content: generated.content,
      category: _parseMemoryCategory(generated.category),
      createdAt: generated.createdAt,
      updatedAt: generated.updatedAt,
      conversationId: generated.conversationId,
      reviewed: generated.reviewed,
      userReview: generated.userReview,
      manuallyAdded: generated.manuallyAdded,
      edited: generated.edited,
      deleted: json['deleted'] as bool? ?? false,
      visibility: generated.visibility != null
          ? (MemoryVisibility.values.asNameMap()[generated.visibility!] ?? MemoryVisibility.public)
          : MemoryVisibility.public,
      isLocked: generated.isLocked,
      isBaseline: json['is_baseline'] as bool? ?? false,
      layer: resolvedLayer,
      layerIsExplicit: layerIsExplicit,
      primaryCaptureDevice: generated.primaryCaptureDevice,
      captureDeviceIds: generated.captureDeviceIds ?? const [],
      ledgerSchemaVersion: generated.ledgerSchemaVersion,
      ledgerKind: KnowledgeLedgerKind.tryParse(generated.kind),
      ledgerBody: generated.body,
      ledgerSlot: generated.slot,
      subjectScope: generated.subjectScope,
      subjectEntityId: generated.subjectEntityId,
      supersededBy: generated.supersededBy,
      invalidAt: generated.invalidAt,
      validAt: generated.validAt,
      intentBacked: generated.intentBacked,
      curationWeight: generated.curationWeight,
      triggerCondition: generated.triggerCondition ?? const {},
      writeReason: generated.writeReason,
      evidence: generated.evidence?.map((item) => item.toJson()).toList(growable: false) ?? const [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'uid': uid,
      'content': content,
      'category': category.toString().split('.').last,
      'created_at': createdAt.toUtc().toIso8601String(),
      'updated_at': updatedAt.toUtc().toIso8601String(),
      'memory_id': conversationId,
      'conversation_id': conversationId,
      'reviewed': reviewed,
      'user_review': userReview,
      'manually_added': manuallyAdded,
      'edited': edited,
      'deleted': deleted,
      'visibility': visibility.name,
      'is_locked': isLocked,
      'is_baseline': isBaseline,
      if (ledgerSchemaVersion != null) 'ledger_schema_version': ledgerSchemaVersion,
      if (ledgerKind != null) 'kind': ledgerKind!.apiValue,
      if (ledgerBody != null) 'body': ledgerBody,
      if (ledgerSlot != null) 'slot': ledgerSlot,
      if (subjectScope != null) 'subject_scope': subjectScope,
      if (subjectEntityId != null) 'subject_entity_id': subjectEntityId,
      if (supersededBy != null) 'superseded_by': supersededBy,
      if (invalidAt != null) 'invalid_at': invalidAt!.toUtc().toIso8601String(),
      if (validAt != null) 'valid_at': validAt!.toUtc().toIso8601String(),
      'intent_backed': intentBacked,
      'curation_weight': curationWeight,
      if (triggerCondition.isNotEmpty) 'trigger_condition': triggerCondition,
      if (writeReason != null) 'write_reason': writeReason,
      if (evidence.isNotEmpty) 'evidence': evidence,
      if (layerIsExplicit && layer != null) 'layer': layer!.apiValue,
    };
  }
}
