// Server views of work that is not a conversation yet (`GET /v1/pending-work`) and of work the
// server gave up on (`GET /v1/attention-items`). Both answer `enabled: false` while the backend
// gate is off; the app then keeps its local view. Responses decode through the generated wire
// models in `gen/pending_work_wire.g.dart`; these adapters only shape them for the UI.

import 'package:omi/backend/schema/gen/pending_work_wire.g.dart' as wire;

DateTime? _date(Object? v) => v is String ? DateTime.tryParse(v) : null;
int? _int(Object? v) => v is num ? v.toInt() : null;

class PendingWorkItem {
  const PendingWorkItem({
    required this.id,
    required this.kind,
    required this.state,
    required this.conversationIds,
    this.startedAt,
    this.durationSeconds,
  });

  /// `conv:<conversation id>` or `sync:<job id>`.
  final String id;

  /// `conversation` or `sync_job`.
  final String kind;

  /// `queued`, `transcribing` or `summarizing`.
  final String state;
  final List<String> conversationIds;
  final DateTime? startedAt;
  final int? durationSeconds;

  static PendingWorkItem? fromJson(Object? json) {
    if (json is! Map) return null;
    final id = json['id'];
    final kind = json['kind'];
    final state = json['state'];
    if (id is! String || kind is! String || state is! String) return null;
    final ids = json['conversation_ids'];
    return PendingWorkItem(
      id: id,
      kind: kind,
      state: state,
      conversationIds: ids is List
          ? [
              for (final c in ids)
                if (c is String) c,
            ]
          : const [],
      startedAt: _date(json['started_at']),
      durationSeconds: _int(json['duration_seconds']),
    );
  }
}

class PendingWorkSnapshot {
  const PendingWorkSnapshot({required this.enabled, required this.items, required this.attentionUnseenCount});

  static const disabled = PendingWorkSnapshot(enabled: false, items: [], attentionUnseenCount: 0);

  final bool enabled;
  final List<PendingWorkItem> items;
  final int attentionUnseenCount;

  factory PendingWorkSnapshot.fromGenerated(wire.GeneratedPendingWorkSnapshot generated) =>
      PendingWorkSnapshot.fromJson(generated.toJson());

  factory PendingWorkSnapshot.fromJson(Map<String, dynamic> json) {
    final rows = json['items'];
    return PendingWorkSnapshot(
      enabled: json['enabled'] == true,
      items: rows is List
          ? [
              for (final r in rows)
                if (PendingWorkItem.fromJson(r) case final item?) item,
            ]
          : const [],
      attentionUnseenCount: _int(json['attention_unseen_count']) ?? 0,
    );
  }
}

enum AttentionRetryState { none, inProgress, succeeded, failed }

AttentionRetryState _retryState(Object? v) => switch (v) {
      'in_progress' => AttentionRetryState.inProgress,
      'succeeded' => AttentionRetryState.succeeded,
      'failed' => AttentionRetryState.failed,
      _ => AttentionRetryState.none,
    };

class AttentionItem {
  const AttentionItem({
    required this.id,
    required this.kind,
    required this.retryable,
    required this.seen,
    required this.retryState,
    this.conversationId,
    this.title,
    this.startedAt,
    this.durationSeconds,
    this.createdAt,
  });

  final String id;

  /// `conversation_summary_failed` in v1.
  final String kind;
  final String? conversationId;
  final String? title;
  final DateTime? startedAt;
  final int? durationSeconds;
  final DateTime? createdAt;
  final bool retryable;
  final bool seen;
  final AttentionRetryState retryState;

  AttentionItem copyWith({AttentionRetryState? retryState, bool? seen}) => AttentionItem(
        id: id,
        kind: kind,
        retryable: retryable,
        seen: seen ?? this.seen,
        retryState: retryState ?? this.retryState,
        conversationId: conversationId,
        title: title,
        startedAt: startedAt,
        durationSeconds: durationSeconds,
        createdAt: createdAt,
      );

  static AttentionItem? fromJson(Object? json) {
    if (json is! Map) return null;
    final id = json['id'];
    final kind = json['kind'];
    if (id is! String || kind is! String) return null;
    final retry = json['retry'];
    final title = json['title'];
    final conversationId = json['conversation_id'];
    return AttentionItem(
      id: id,
      kind: kind,
      conversationId: conversationId is String ? conversationId : null,
      title: title is String && title.trim().isNotEmpty ? title : null,
      startedAt: _date(json['started_at']),
      durationSeconds: _int(json['duration_seconds']),
      createdAt: _date(json['created_at']),
      retryable: json['retryable'] == true,
      seen: json['seen'] == true,
      retryState: retry is Map ? _retryState(retry['state']) : AttentionRetryState.none,
    );
  }
}

class AttentionItemsPage {
  const AttentionItemsPage({required this.enabled, required this.items, required this.unseenCount});

  static const disabled = AttentionItemsPage(enabled: false, items: [], unseenCount: 0);

  final bool enabled;
  final List<AttentionItem> items;
  final int unseenCount;

  factory AttentionItemsPage.fromGenerated(wire.GeneratedAttentionItemsPage generated) =>
      AttentionItemsPage.fromJson(generated.toJson());

  factory AttentionItemsPage.fromJson(Map<String, dynamic> json) {
    final rows = json['items'];
    return AttentionItemsPage(
      enabled: json['enabled'] == true,
      items: rows is List
          ? [
              for (final r in rows)
                if (AttentionItem.fromJson(r) case final item?) item,
            ]
          : const [],
      unseenCount: _int(json['unseen_count']) ?? 0,
    );
  }
}

class AttentionRetryResult {
  const AttentionRetryResult({required this.itemId, required this.state, this.operationId});

  final String itemId;
  final String? operationId;
  final AttentionRetryState state;

  /// Accepts a single-retry response or one Retry all operation: both carry operation_id and state.
  static AttentionRetryResult fromGenerated(String itemId, Object generated) => fromJson(
        itemId,
        switch (generated) {
          wire.GeneratedAttentionRetryResponse g => g.toJson(),
          wire.GeneratedAttentionRetryAllOperation g => g.toJson(),
          _ => throw ArgumentError.value(generated, 'generated'),
        },
      );

  static AttentionRetryResult fromJson(String itemId, Map<String, dynamic> json) {
    final op = json['operation_id'];
    return AttentionRetryResult(
      itemId: itemId,
      operationId: op is String ? op : null,
      state: _retryState(json['state']),
    );
  }
}
