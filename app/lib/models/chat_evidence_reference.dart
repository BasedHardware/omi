/// Additive, versioned references that let a chat answer point at supporting
/// conversation or screen evidence without making that evidence required for
/// the text answer to render.
///
/// Older mobile releases ignore the containing JSON field. Newer releases
/// ignore unknown fields/kinds/states, so the envelope can evolve without
/// changing the existing ServerMessage JSON contract.

library;

import 'dart:convert';

enum ChatEvidenceReferenceKind {
  conversationSummary('conversation_summary'),
  conversationSegment('conversation_segment'),
  screen('screen'),
  keyframe('keyframe'),
  request('request'),
  unknown('unknown');

  const ChatEvidenceReferenceKind(this.wireValue);

  final String wireValue;

  static ChatEvidenceReferenceKind fromWire(Object? value) {
    final wireValue = value?.toString().trim().toLowerCase();
    return values.firstWhere(
      (kind) => kind.wireValue == wireValue,
      orElse: () => ChatEvidenceReferenceKind.unknown,
    );
  }
}

enum ChatEvidenceReferenceState {
  available('available'),
  loading('loading'),
  offline('offline'),
  pruned('pruned'),
  failed('failed'),
  unknown('unknown');

  const ChatEvidenceReferenceState(this.wireValue);

  final String wireValue;

  static ChatEvidenceReferenceState fromWire(Object? value) {
    final wireValue = value?.toString().trim().toLowerCase();
    return values.firstWhere(
      (state) => state.wireValue == wireValue,
      orElse: () => ChatEvidenceReferenceState.unknown,
    );
  }
}

class ChatEvidenceReference {
  static const maxReferencesPerEnvelope = 24;
  static const maxIdentifierCharacters = 256;
  static const maxTitleCharacters = 160;
  static const maxSummaryCharacters = 600;
  static const maxErrorCodeCharacters = 128;
  static const maxErrorMessageCharacters = 600;
  static const maxMetadataEntries = 16;
  static const maxMetadataSerializedCharacters = 2000;
  static const maxMetadataDepth = 3;
  static const maxMetadataListItems = 24;

  const ChatEvidenceReference({
    required this.id,
    required this.kind,
    required this.state,
    this.title,
    this.summary,
    this.conversationId,
    this.segmentId,
    this.frameId,
    this.requestId,
    this.startMs,
    this.endMs,
    this.capturedAtMs,
    this.errorCode,
    this.errorMessage,
    this.metadata = const {},
  });

  final String id;
  final ChatEvidenceReferenceKind kind;
  final ChatEvidenceReferenceState state;
  final String? title;
  final String? summary;
  final String? conversationId;
  final String? segmentId;
  final String? frameId;
  final String? requestId;
  final int? startMs;
  final int? endMs;
  final int? capturedAtMs;
  final String? errorCode;
  final String? errorMessage;
  final Map<String, dynamic> metadata;

  factory ChatEvidenceReference.fromJson(Map<String, dynamic> json) {
    return ChatEvidenceReference(
      id: _string(json['id'] ?? json['reference_id'], maxLength: maxIdentifierCharacters) ?? '',
      kind: ChatEvidenceReferenceKind.fromWire(json['kind'] ?? json['type']),
      state: ChatEvidenceReferenceState.fromWire(
        json['state'] ?? json['status'],
      ),
      title: _string(json['title'], maxLength: maxTitleCharacters),
      summary: _string(json['summary'] ?? json['preview'], maxLength: maxSummaryCharacters),
      conversationId: _string(
        json['conversation_id'] ?? json['conversationId'],
        maxLength: maxIdentifierCharacters,
      ),
      segmentId: _string(
        json['segment_id'] ?? json['segmentId'],
        maxLength: maxIdentifierCharacters,
      ),
      frameId: _string(json['frame_id'] ?? json['frameId'], maxLength: maxIdentifierCharacters),
      requestId: _string(json['request_id'] ?? json['requestId'], maxLength: maxIdentifierCharacters),
      startMs: _int(json['start_ms'] ?? json['startMs']),
      endMs: _int(json['end_ms'] ?? json['endMs']),
      capturedAtMs: _int(json['captured_at_ms'] ?? json['capturedAtMs']),
      errorCode: _string(
        json['error_code'] ?? json['errorCode'],
        maxLength: maxErrorCodeCharacters,
      ),
      errorMessage: _string(
        json['error_message'] ?? json['errorMessage'],
        maxLength: maxErrorMessageCharacters,
      ),
      metadata: _map(json['metadata']),
    );
  }

  /// A usable reference is optional UI chrome; the answer must not depend on it.
  bool get canOpen {
    if (id.trim().isEmpty || state != ChatEvidenceReferenceState.available) return false;
    return switch (kind) {
      ChatEvidenceReferenceKind.conversationSummary => conversationId != null,
      ChatEvidenceReferenceKind.conversationSegment => conversationId != null && segmentId != null,
      ChatEvidenceReferenceKind.screen || ChatEvidenceReferenceKind.keyframe => frameId != null,
      ChatEvidenceReferenceKind.request => requestId != null,
      ChatEvidenceReferenceKind.unknown => false,
    };
  }

  String get sourceLabel {
    switch (kind) {
      case ChatEvidenceReferenceKind.conversationSummary:
        return 'Conversation summary';
      case ChatEvidenceReferenceKind.conversationSegment:
        return 'Conversation segment';
      case ChatEvidenceReferenceKind.screen:
        return 'Current screen';
      case ChatEvidenceReferenceKind.keyframe:
        return 'Screen keyframe';
      case ChatEvidenceReferenceKind.request:
        return 'Evidence request';
      case ChatEvidenceReferenceKind.unknown:
        return 'Evidence';
    }
  }

  String get statusLabel {
    switch (state) {
      case ChatEvidenceReferenceState.available:
        return 'Available';
      case ChatEvidenceReferenceState.loading:
        return 'Loading';
      case ChatEvidenceReferenceState.offline:
        return 'Unavailable offline';
      case ChatEvidenceReferenceState.pruned:
        return 'No longer available';
      case ChatEvidenceReferenceState.failed:
        return 'Failed to load';
      case ChatEvidenceReferenceState.unknown:
        return 'Unavailable';
    }
  }

  String get accessibilityLabel {
    final detail = (title ?? summary)?.trim();
    final suffix = detail == null || detail.isEmpty ? '' : ': $detail';
    return '$sourceLabel$suffix, $statusLabel';
  }

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{
      'id': id,
      'kind': kind.wireValue,
      'state': state.wireValue,
    };
    _put(json, 'title', title);
    _put(json, 'summary', summary);
    _put(json, 'conversation_id', conversationId);
    _put(json, 'segment_id', segmentId);
    _put(json, 'frame_id', frameId);
    _put(json, 'request_id', requestId);
    _put(json, 'start_ms', startMs);
    _put(json, 'end_ms', endMs);
    _put(json, 'captured_at_ms', capturedAtMs);
    _put(
      json,
      'error_code',
      _string(errorCode, maxLength: maxErrorCodeCharacters),
    );
    _put(
      json,
      'error_message',
      _string(errorMessage, maxLength: maxErrorMessageCharacters),
    );
    final boundedMetadata = _map(metadata);
    if (boundedMetadata.isNotEmpty) json['metadata'] = boundedMetadata;
    return json;
  }

  static String? _string(Object? value, {int? maxLength}) {
    if (value is! String) return null;
    final stripped = value.trim();
    if (stripped.isEmpty) return null;
    if (maxLength != null && stripped.length > maxLength) return stripped.substring(0, maxLength);
    return stripped;
  }

  static int? _int(Object? value) => value is num ? value.toInt() : int.tryParse(value?.toString() ?? '');

  static Map<String, dynamic> _map(Object? value) {
    if (value is! Map) return const {};
    final bounded = <String, dynamic>{};
    for (final entry in value.entries.take(maxMetadataEntries)) {
      final key = _string(entry.key.toString(), maxLength: maxIdentifierCharacters);
      final item = _metadataValue(entry.value, 0);
      if (key != null && !identical(item, _omitMetadataValue)) bounded[key] = item;
    }
    while (bounded.isNotEmpty) {
      try {
        if (jsonEncode(bounded).length <= maxMetadataSerializedCharacters) break;
      } catch (_) {
        return const {};
      }
      bounded.remove(bounded.keys.last);
    }
    return bounded;
  }

  static final Object _omitMetadataValue = Object();

  static dynamic _metadataValue(Object? value, int depth) {
    if (value == null || value is bool) return value;
    if (value is num) return value.isFinite ? value : _omitMetadataValue;
    if (value is String) return _string(value, maxLength: maxSummaryCharacters);
    if (depth > maxMetadataDepth) return _omitMetadataValue;
    if (value is List) {
      return value
          .take(maxMetadataListItems)
          .map((item) => _metadataValue(item, depth + 1))
          .where((item) => !identical(item, _omitMetadataValue))
          .toList(growable: false);
    }
    if (value is Map) {
      final nested = <String, dynamic>{};
      for (final entry in value.entries.take(maxMetadataEntries)) {
        final key = _string(entry.key.toString(), maxLength: maxIdentifierCharacters);
        final item = _metadataValue(entry.value, depth + 1);
        if (key != null && !identical(item, _omitMetadataValue)) nested[key] = item;
      }
      return nested;
    }
    return _omitMetadataValue;
  }

  static void _put(Map<String, dynamic> json, String key, Object? value) {
    if (value != null) json[key] = value;
  }
}

class ChatEvidenceReferenceEnvelope {
  static const currentSchemaVersion = 1;

  const ChatEvidenceReferenceEnvelope({
    this.schemaVersion = currentSchemaVersion,
    required this.references,
    this.requestId,
  });

  final int schemaVersion;
  final String? requestId;
  final List<ChatEvidenceReference> references;

  bool get isEmpty => references.isEmpty;

  factory ChatEvidenceReferenceEnvelope.fromJson(Map<String, dynamic> json) {
    const schemaKeys = ['schema_version', 'schemaVersion', 'version'];
    final schemaKey = schemaKeys.firstWhere(
      json.containsKey,
      orElse: () => '',
    );
    final schemaVersion = schemaKey.isEmpty ? currentSchemaVersion : _schemaVersion(json[schemaKey]) ?? 0;
    final rawReferences = json['references'] ?? json['evidence_refs'] ?? json['evidence_references'];
    final references = rawReferences is List
        ? rawReferences
            .whereType<Map>()
            .map((value) {
              Map<String, dynamic> reference;
              try {
                reference = Map<String, dynamic>.from(value);
              } catch (_) {
                return null;
              }
              if (schemaVersion != currentSchemaVersion) {
                // Preserve the envelope for diagnostics, but a future wire
                // contract must never become actionable under v1 semantics.
                reference['kind'] = 'unknown';
                reference['state'] = 'unknown';
              }
              return ChatEvidenceReference.fromJson(
                reference,
              );
            })
            .whereType<ChatEvidenceReference>()
            .take(ChatEvidenceReference.maxReferencesPerEnvelope)
            .toList(growable: false)
        : const <ChatEvidenceReference>[];
    return ChatEvidenceReferenceEnvelope(
      schemaVersion: schemaVersion,
      requestId: ChatEvidenceReference._string(
        json['request_id'] ?? json['requestId'],
        maxLength: ChatEvidenceReference.maxIdentifierCharacters,
      ),
      references: references,
    );
  }

  static ChatEvidenceReferenceEnvelope? tryFromJson(Object? value) {
    if (value is! Map) return null;
    try {
      return ChatEvidenceReferenceEnvelope.fromJson(Map<String, dynamic>.from(value));
    } catch (_) {
      return null;
    }
  }

  static int? _schemaVersion(Object? value) {
    if (value is int) return value;
    if (value is num && value.isFinite && value == value.toInt()) return value.toInt();
    if (value is String) return int.tryParse(value.trim());
    return null;
  }

  Map<String, dynamic> toJson() {
    return {
      'schema_version': schemaVersion,
      if (requestId != null) 'request_id': requestId,
      'references': references.map((reference) => reference.toJson()).toList(growable: false),
    };
  }
}
