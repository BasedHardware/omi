import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:nooto_v2/services/api_client.dart';

/// External provenance for an action item. Set when the item came from a
/// connected integration (Jira, Linear, …) rather than being captured from
/// transcript. `source` is a stable lower-case identifier (e.g. "jira"),
/// `externalId` is the provider-native key (e.g. "PROJ-123"), and `url` is
/// the deep link the user can tap to jump to the item in the source tool.
///
/// `metadata` carries integration-specific extras (for Jira: status,
/// status_type, project_key, priority, status_changed_at). It's optional and
/// opaque to the model itself — typed access lives on the convenience
/// getters below so we don't sprinkle string keys across the UI layer.
///
/// All three core fields (source, externalId, url) are required for a valid
/// `ExternalSource` — if any are missing or empty, [ExternalSource.fromJson]
/// returns null and the item is treated as transcript-derived.
class ExternalSource {
  const ExternalSource({required this.source, required this.externalId, required this.url, this.metadata});

  final String source;
  final String externalId;
  final String url;

  /// Integration-specific extras. For Jira: `status`, `status_type`
  /// (todo/indeterminate/done), `project_key`, `priority`, optional
  /// `status_changed_at` ISO8601. Null when the backend hasn't shipped
  /// metadata for this source yet — the chip stays pure-id in that case.
  final Map<String, dynamic>? metadata;

  /// Human-readable Jira status (e.g. "In Review"). Null when the source
  /// isn't Jira or the backend hasn't included metadata yet.
  String? get jiraStatus => metadata?['status'] as String?;

  /// Coarse status bucket: "todo" / "indeterminate" / "done". Drives the
  /// metadata-strip dot color and the swipe-transition target list.
  String? get jiraStatusType => metadata?['status_type'] as String?;

  /// Jira project key (e.g. "PROJ"). Used by the By-Project pivot and the
  /// project-tap filter.
  String? get jiraProjectKey => metadata?['project_key'] as String?;

  /// Priority — passed through verbatim from the backend (e.g. "P2",
  /// "Medium"). The UI hides "Medium"/"None" because they're noise.
  String? get jiraPriority => metadata?['priority'] as String?;

  /// Plain-text body of the Jira issue's description field. Fed by the
  /// nooto-jira plugin's ADF→text flattener and capped at 2000 chars
  /// server-side. Null when the issue has no description, or when this
  /// item predates the description-body sync (older docs in Firestore
  /// won't have it until the next /v1/integrations/jira/sync-now or
  /// scheduled sync). The Plan detail screen renders this; chat pills /
  /// rows do not.
  String? get jiraDescriptionBody => metadata?['description_body'] as String?;

  /// When the issue last transitioned status. Optional. Null when missing
  /// or not parseable as ISO8601.
  DateTime? get jiraStatusChangedAt {
    final raw = metadata?['status_changed_at'];
    if (raw is! String || raw.isEmpty) return null;
    try {
      return DateTime.parse(raw).toLocal();
    } catch (_) {
      return null;
    }
  }

  /// Whole-day count since the last status transition. Null when
  /// `status_changed_at` is missing/unparseable. Negative deltas (clock
  /// skew) collapse to null — we'd rather show nothing than "-1d".
  int? get daysAtStatus {
    final at = jiraStatusChangedAt;
    if (at == null) return null;
    final diff = DateTime.now().difference(at).inDays;
    return diff < 0 ? null : diff;
  }

  /// Returns null if the JSON is missing/empty for any required field. We
  /// accept partial drift from the backend (e.g. an integration that hasn't
  /// shipped a URL yet) by collapsing to the transcript-derived shape rather
  /// than rendering a half-broken chip.
  static ExternalSource? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final source = (json['source'] as String?)?.trim();
    final externalId = (json['external_id'] as String?)?.trim();
    final url = (json['url'] as String?)?.trim();
    if (source == null || source.isEmpty) return null;
    if (externalId == null || externalId.isEmpty) return null;
    if (url == null || url.isEmpty) return null;
    final metaRaw = json['metadata'];
    final metadata = metaRaw is Map ? Map<String, dynamic>.from(metaRaw) : null;
    return ExternalSource(source: source, externalId: externalId, url: url, metadata: metadata);
  }

  ExternalSource copyWith({Map<String, dynamic>? metadata}) =>
      ExternalSource(source: source, externalId: externalId, url: url, metadata: metadata ?? this.metadata);
}

/// One commitment captured from a conversation. Server schema is richer (lock,
/// export, indent, sort_order) — v2 ignores those for now and rehydrates them
/// only when a card type needs them.
class ActionItem {
  ActionItem({
    required this.id,
    required this.description,
    required this.completed,
    this.createdAt,
    this.dueAt,
    this.conversationId,
    this.externalSource,
  });

  final String id;
  final String description;
  final bool completed;
  final DateTime? createdAt;
  final DateTime? dueAt;
  final String? conversationId;

  /// Non-null when the item was sourced from a connected integration. Drives
  /// the integration chip on Plan / Home and the proactive stuck-issues card.
  final ExternalSource? externalSource;

  factory ActionItem.fromJson(Map<String, dynamic> json) {
    final extRaw = json['external_source'];
    final externalSource = extRaw is Map ? ExternalSource.fromJson(Map<String, dynamic>.from(extRaw)) : null;
    return ActionItem(
      id: json['id'] as String,
      description: json['description'] as String? ?? '',
      completed: json['completed'] as bool? ?? false,
      createdAt: json['created_at'] != null ? DateTime.parse(json['created_at'] as String).toLocal() : null,
      dueAt: json['due_at'] != null ? DateTime.parse(json['due_at'] as String).toLocal() : null,
      conversationId: json['conversation_id'] as String?,
      externalSource: externalSource,
    );
  }

  ActionItem copyWith({bool? completed, DateTime? dueAt, ExternalSource? externalSource}) => ActionItem(
    id: id,
    description: description,
    completed: completed ?? this.completed,
    createdAt: createdAt,
    dueAt: dueAt ?? this.dueAt,
    conversationId: conversationId,
    externalSource: externalSource ?? this.externalSource,
  );
}

/// Read-only port of legacy `ActionItemsProvider`: fetches the user's open
/// commitments from `/v1/action-items` and lets a card generator surface them
/// on Home. `complete(id)` does an optimistic update + server confirm; on
/// failure the local state rolls back so the card reappears next refresh.
///
/// Two-way-sync writes (Jira transition + snooze) live on this provider too:
/// they mirror the optimistic-then-rollback shape of `complete`. Errors stamp
/// `lastActionError` so the UI can surface a SnackBar that distinguishes
/// "two-way-sync OFF" from "Jira returned an error".
class ActionItemsProvider extends ChangeNotifier {
  ActionItemsProvider({required ApiClient client}) : _client = client;

  final ApiClient _client;
  final List<ActionItem> _items = [];
  bool _loading = false;
  bool _ready = false;

  /// Most recent error from a write action (transition / snooze). Cleared on
  /// the next successful action. Used by the Plan screen to pick a SnackBar
  /// message: `'two_way_sync_disabled'` → "Enable Jira write-back…",
  /// anything else → "Couldn't update Jira. Try again."
  String? _lastActionError;
  String? get lastActionError => _lastActionError;

  List<ActionItem> get items => List.unmodifiable(_items);

  /// Cards consume this — incomplete only, capped at 3 to keep the Home stream
  /// uncluttered. Sorted by createdAt desc (newest commitments first).
  List<ActionItem> get incompleteTop3 {
    final open = _items.where((i) => !i.completed).toList();
    open.sort((a, b) {
      final ac = a.createdAt;
      final bc = b.createdAt;
      if (ac == null && bc == null) return 0;
      if (ac == null) return 1;
      if (bc == null) return -1;
      return bc.compareTo(ac);
    });
    return open.take(3).toList();
  }

  bool get loading => _loading;
  bool get ready => _ready;

  /// Idempotent first-fetch: call freely from screen attach paths. No-op if
  /// a fetch already ran or is in flight. Keeps the fetch-trigger out of
  /// widget `build()` methods.
  Future<void> kickOffIfNeeded() async {
    if (_ready || _loading) return;
    await fetchAll();
  }

  Future<void> fetchAll() async {
    if (_loading) return;
    _loading = true;
    notifyListeners();
    try {
      final res = await _client.get('v1/action-items?limit=50&offset=0&completed=false');
      final body = jsonDecode(res.body) as Map<String, dynamic>;
      final list = (body['action_items'] as List<dynamic>? ?? const [])
          .map((e) => ActionItem.fromJson(e as Map<String, dynamic>))
          .toList();
      _items
        ..clear()
        ..addAll(list);
    } catch (e, st) {
      debugPrint('[ActionItemsProvider] fetchAll failed: $e\n$st');
    } finally {
      _loading = false;
      _ready = true;
      notifyListeners();
    }
  }

  /// Optimistic complete: flip local state, hit server, roll back on failure.
  /// Caller (the Home card generator) sees the card disappear immediately;
  /// if the server rejects, the next refresh will reinstate it.
  Future<bool> complete(String id) async {
    final idx = _items.indexWhere((i) => i.id == id);
    if (idx == -1) return false;
    final original = _items[idx];
    _items[idx] = original.copyWith(completed: true);
    notifyListeners();
    try {
      await _client.patch('v1/action-items/$id/completed?completed=true');
      _lastActionError = null;
      return true;
    } catch (_) {
      _items[idx] = original;
      notifyListeners();
      return false;
    }
  }

  /// Optimistic Jira transition. Updates the local item's metadata.status +
  /// status_type immediately, replaces from server response on success,
  /// rolls back on failure. On 403 with detail "two_way_sync_disabled" the
  /// caller can branch on `lastActionError`.
  ///
  /// When [optimisticallyComplete] is true, also flips `completed=true`
  /// locally before the round-trip so list filters that hide completed rows
  /// (e.g. the Plan tab) drop the item instantly. Caller is responsible for
  /// only passing `true` when [toStatus] resolves to `status_type='done'`
  /// server-side. The backend already flips `completed=true` on a Done
  /// transition, so the server response that lands in `_items[idx]` keeps
  /// the row hidden after rollback-or-confirm. On failure the rollback to
  /// `original` reverts `completed` alongside `metadata`.
  Future<bool> transition(String id, {required String toStatus, bool optimisticallyComplete = false}) async {
    final idx = _items.indexWhere((i) => i.id == id);
    if (idx == -1) return false;
    final original = _items[idx];
    final ext = original.externalSource;
    if (ext == null) return false;
    // Optimistic local mutation: bump status + status_type. The status_type
    // is a best-effort guess (anything→done if the target reads "Done", else
    // indeterminate) so the strip color updates immediately. The server
    // response replaces this whole-cloth on success so the guess never
    // outlives a round-trip.
    final newType = toStatus.toLowerCase() == 'done' ? 'done' : 'indeterminate';
    final optimisticMeta = <String, dynamic>{...?ext.metadata, 'status': toStatus, 'status_type': newType};
    _items[idx] = original.copyWith(
      externalSource: ext.copyWith(metadata: optimisticMeta),
      // copyWith treats `null` as "preserve original" — using
      // original.completed here makes the read explicit instead of relying
      // on the reader to know that null means preserve.
      completed: optimisticallyComplete ? true : original.completed,
    );
    notifyListeners();
    try {
      final res = await _client.post(
        'v1/integrations/jira/transition',
        body: {'action_item_id': id, 'to_status': toStatus},
      );
      final body = jsonDecode(res.body);
      if (body is Map<String, dynamic>) {
        _items[idx] = ActionItem.fromJson(body);
        notifyListeners();
      }
      _lastActionError = null;
      return true;
    } catch (e) {
      _items[idx] = original;
      _lastActionError = _errorKey(e);
      notifyListeners();
      return false;
    }
  }

  /// Optimistic snooze. Updates local `dueAt` to `snoozeUntil`, rolls back on
  /// failure. Same error-stamp semantics as [transition].
  Future<bool> snooze(String id, {required DateTime snoozeUntil}) async {
    final idx = _items.indexWhere((i) => i.id == id);
    if (idx == -1) return false;
    final original = _items[idx];
    if (original.externalSource == null) return false;
    _items[idx] = original.copyWith(dueAt: snoozeUntil);
    notifyListeners();
    try {
      final res = await _client.post(
        'v1/integrations/jira/snooze',
        body: {'action_item_id': id, 'snooze_until': snoozeUntil.toUtc().toIso8601String()},
      );
      final body = jsonDecode(res.body);
      if (body is Map<String, dynamic>) {
        _items[idx] = ActionItem.fromJson(body);
        notifyListeners();
      }
      _lastActionError = null;
      return true;
    } catch (e) {
      _items[idx] = original;
      _lastActionError = _errorKey(e);
      notifyListeners();
      return false;
    }
  }

  /// Maps an exception to a stable string the UI can branch on. We treat the
  /// 403 detail "two_way_sync_disabled" as the canonical "toggle is OFF"
  /// signal; anything else collapses to a generic key so the SnackBar stays
  /// short.
  static String _errorKey(Object e) {
    if (e is ApiError) {
      if (e.statusCode == 403 && e.detail == 'two_way_sync_disabled') {
        return 'two_way_sync_disabled';
      }
      return 'jira_error';
    }
    return 'network_error';
  }
}
