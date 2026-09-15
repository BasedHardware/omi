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
  if ([
    'core',
    'hobbies',
    'lifestyle',
    'interests',
    'work',
    'skills',
    'habits',
    'other',
  ].contains(category)) {
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
  final String? ledgerStatus;
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

  /// Server-owned auxiliary state.  In particular, `memory_use.suppressed`
  /// records an owner's explicit use decision.  Keep the bag intact so an
  /// owner can inspect history and a retry can converge on the server state.
  Map<String, dynamic>? arguments;
  final Map<String, dynamic> triggerCondition;
  final String? writeReason;
  final List<Map<String, dynamic>> evidence;

  /// Server-assessed temporal evidence. These fields are optional so an older
  /// response remains decodable, but absence must never be treated as a
  /// currentness assertion.
  final DateTime? asOf;
  final String? beliefClass;
  final double? currency;
  final String? currencyBand;
  final double? halfLifeDays;
  final DateTime? beliefComputedAt;

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
    this.ledgerStatus,
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
    this.arguments,
    this.triggerCondition = const {},
    this.writeReason,
    this.evidence = const [],
    this.asOf,
    this.beliefClass,
    this.currency,
    this.currencyBand,
    this.halfLifeDays,
    this.beliefComputedAt,
  });

  /// True when the response carries an assessment made at a known time.
  /// Older clients/backends may omit this marker; those rows remain usable as
  /// legacy records but are never presented as freshly assessed current facts.
  bool get hasCurrencyAssessment => beliefComputedAt != null;

  /// Unknown assessment is distinct from a deliberately non-decaying record.
  /// The backend represents it with an assessment timestamp but no currency
  /// value/band, so clients do not reimplement the decay formula.
  bool get hasUnknownCurrency =>
      hasCurrencyAssessment && currency == null && (currencyBand == null || currencyBand == 'unknown');

  /// A client must only use the server's band. Missing assessment metadata is
  /// intentionally false; it is a compatibility/legacy state, not currentness.
  bool get isCurrentForUse {
    if (!hasCurrencyAssessment || deleted || isHistoricalKnowledgeLedgerRow) {
      return false;
    }
    return hasUnknownCurrency || currencyBand == 'current' || currencyBand == 'fading';
  }

  /// Rows without a server assessment stay visible in the useful-now list so
  /// an older response cannot make memories disappear. They are rendered as
  /// unassessed and are not eligible for current claims or proactive use.
  /// A deleted row never re-enters the list, even when a legacy or cached row
  /// predates assessments entirely.
  bool get isUsefulNow {
    if (isHistoricalKnowledgeLedgerRow) return false;
    return !deleted && (!hasCurrencyAssessment || isCurrentForUse);
  }

  /// Whether the owner has explicitly suppressed this memory from agent use.
  /// A null result means the server has not recorded a use decision yet.
  bool? get memoryUseSuppressed {
    final use = arguments?['memory_use'];
    if (use is! Map) return null;
    final suppressed = use['suppressed'];
    return suppressed is bool ? suppressed : null;
  }

  /// The last server-recorded memory-use action, if present.
  String? get memoryUseAction {
    final use = arguments?['memory_use'];
    if (use is! Map) return null;
    final action = use['last_action'] ?? use['state'];
    return action is String ? action : null;
  }

  static DateTime? _parseOptionalDateTime(Object? value) {
    if (value is DateTime) return value;
    if (value is String && value.isNotEmpty) return DateTime.tryParse(value);
    return null;
  }

  bool get isKnowledgeLedger => ledgerSchemaVersion == 'knowledge_ledger.v1' && ledgerKind != null;

  bool get isCurrentKnowledgeLedgerRow =>
      isKnowledgeLedger &&
      intentBacked &&
      !deleted &&
      (ledgerStatus == null || ledgerStatus == 'active') &&
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
      ledgerStatus: generated.ledgerStatus,
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
      arguments: generated.arguments == null ? null : Map<String, dynamic>.from(generated.arguments!),
      triggerCondition: generated.triggerCondition ?? const {},
      writeReason: generated.writeReason,
      evidence: generated.evidence?.map((item) => item.toJson()).toList(growable: false) ?? const [],
      asOf: generated.asOf,
      beliefClass: generated.beliefClass,
      currency: generated.currency,
      currencyBand: generated.currencyBand,
      halfLifeDays: generated.halfLifeDays,
      beliefComputedAt: generated.beliefComputedAt ?? _parseOptionalDateTime(json['belief_computed_at']),
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
      if (ledgerStatus != null) 'ledger_status': ledgerStatus,
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
      if (arguments != null) 'arguments': arguments,
      if (triggerCondition.isNotEmpty) 'trigger_condition': triggerCondition,
      if (writeReason != null) 'write_reason': writeReason,
      if (evidence.isNotEmpty) 'evidence': evidence,
      if (asOf != null) 'as_of': asOf!.toUtc().toIso8601String(),
      if (beliefClass != null) 'belief_class': beliefClass,
      if (currency != null) 'currency': currency,
      if (currencyBand != null) 'currency_band': currencyBand,
      if (halfLifeDays != null) 'half_life_days': halfLifeDays,
      if (beliefComputedAt != null) 'belief_computed_at': beliefComputedAt!.toUtc().toIso8601String(),
      if (layerIsExplicit && layer != null) 'layer': layer!.apiValue,
    };
  }
}
