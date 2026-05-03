import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:nooto_v2/library/conversation_model.dart';
import 'package:nooto_v2/services/api_client.dart';

/// Owns the Conversations list state for the Library tab. Hits
/// `/v1/conversations`, surfaces a flat sorted list and date-bucketed groups.
/// Mirrors LibraryProvider's idempotent-load + force-refresh + optimistic-
/// delete shape so the two sub-tabs feel consistent.
class ConversationsProvider extends ChangeNotifier {
  ConversationsProvider({required ApiClient client}) : _client = client;

  final ApiClient _client;

  List<ConversationItem> _items = const [];
  bool _loading = false;
  bool _hasFetched = false;
  String? _error;
  String? _pendingId;

  /// Set of conversation ids currently mid-`reprocessWithApp`. Distinct
  /// from `_pendingId` (used by delete) so the picker sheet can show a
  /// shimmer while the network call is in flight without blocking other
  /// list-level mutations.
  Set<String> _reprocessingIds = const {};

  bool get loading => _loading;
  bool get hasFetched => _hasFetched;
  String? get error => _error;
  bool get isEmpty => _items.isEmpty;
  bool isPending(String id) => _pendingId == id;

  /// True while `reprocessWithApp` is in flight for [id].
  bool isReprocessing(String id) => _reprocessingIds.contains(id);

  List<ConversationItem> get items => _items;

  ConversationItem? byId(String id) {
    for (final c in _items) {
      if (c.id == id) return c;
    }
    return null;
  }

  /// Date-bucketed view, sorted within bucket by createdAt desc. Same labels
  /// the desktop-v2 list uses (Today / Yesterday / This Week / This Month /
  /// month name) so users hopping between surfaces aren't relearning grammar.
  List<ConversationGroup> get groups {
    final byLabel = <String, List<ConversationItem>>{};
    final order = <String>[];
    final now = DateTime.now();
    for (final c in _items) {
      final label = conversationDateBucket(c.createdAt, now: now);
      final bucket = byLabel.putIfAbsent(label, () {
        order.add(label);
        return <ConversationItem>[];
      });
      bucket.add(c);
    }
    for (final list in byLabel.values) {
      list.sort((a, b) {
        final ad = a.createdAt;
        final bd = b.createdAt;
        if (ad == null && bd == null) return 0;
        if (ad == null) return 1;
        if (bd == null) return -1;
        return bd.compareTo(ad);
      });
    }
    return [for (final l in order) ConversationGroup(label: l, items: byLabel[l]!)];
  }

  Future<void> load({bool force = false}) async {
    if (_loading) return;
    if (_hasFetched && !force) return;

    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final res = await _client.get('v1/conversations?limit=100&offset=0');
      final body = jsonDecode(res.body);
      final list = body is List
          ? body
                .whereType<Map>()
                .map((m) => ConversationItem.fromJson(Map<String, dynamic>.from(m)))
                .toList(growable: false)
          : const <ConversationItem>[];
      // Top-level sort by createdAt desc. groups recomputes per read.
      final sorted = [...list]
        ..sort((a, b) {
          final ad = a.createdAt;
          final bd = b.createdAt;
          if (ad == null && bd == null) return 0;
          if (ad == null) return 1;
          if (bd == null) return -1;
          return bd.compareTo(ad);
        });
      _items = sorted;
      _hasFetched = true;
    } catch (e, st) {
      debugPrint('[ConversationsProvider] load failed: $e\n$st');
      _error = e.toString();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// Reprocess a conversation with the chosen summarization app. Hits
  /// `POST /v1/conversations/{id}/reprocess?app_id={appId}` (the same
  /// endpoint the legacy `/app` ConversationDetailProvider uses). The
  /// backend re-runs `_trigger_apps()` with the explicit app id and
  /// returns the updated conversation document, which we splice back
  /// into our local list so the detail screen rebuilds with the new
  /// `apps_results[0].content` immediately.
  ///
  /// Returns true on success, false on any error. Sets `_error` only on
  /// failure so the detail screen can surface a snackbar without
  /// stomping the global "load failed" message from [load].
  Future<bool> reprocessWithApp(String conversationId, String appId) async {
    if (_reprocessingIds.contains(conversationId)) return false;
    _reprocessingIds = {..._reprocessingIds, conversationId};
    notifyListeners();
    try {
      final res = await _client.post(
        'v1/conversations/$conversationId/reprocess?app_id=${Uri.encodeQueryComponent(appId)}',
        body: const {},
      );
      final body = jsonDecode(res.body);
      if (body is! Map) return false;
      final updated = ConversationItem.fromRaw(Map<String, dynamic>.from(body));
      final idx = _items.indexWhere((c) => c.id == conversationId);
      if (idx >= 0) {
        _items = [..._items]..[idx] = updated;
      }
      return true;
    } catch (e) {
      debugPrint('[ConversationsProvider] reprocessWithApp($conversationId, $appId) failed: $e');
      _error = e.toString();
      return false;
    } finally {
      _reprocessingIds = {..._reprocessingIds}..remove(conversationId);
      notifyListeners();
    }
  }

  /// Optimistic delete with rollback at original index on non-2xx, matching
  /// LibraryProvider.delete. The server endpoint is 204 on success.
  Future<bool> delete(String id) async {
    if (_pendingId != null) return false;
    final idx = _items.indexWhere((c) => c.id == id);
    if (idx == -1) return false;
    final removed = _items[idx];
    _pendingId = id;
    _items = [..._items]..removeAt(idx);
    notifyListeners();
    try {
      await _client.delete('v1/conversations/$id');
      return true;
    } catch (e) {
      debugPrint('[ConversationsProvider] delete($id) failed: $e');
      final restored = [..._items];
      restored.insert(idx, removed);
      _items = restored;
      _error = e.toString();
      return false;
    } finally {
      _pendingId = null;
      notifyListeners();
    }
  }
}
