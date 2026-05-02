import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:nooto_v2/library/memory_model.dart';
import 'package:nooto_v2/services/api_client.dart';

/// Owns the Library state — flat list of memories from `/v3/memories`,
/// surfaced as 4 buckets via [groups]. Delete is optimistic; rolls back on
/// non-2xx and surfaces error string. Mirrors the AppsProvider pattern.
class LibraryProvider extends ChangeNotifier {
  LibraryProvider({required ApiClient client}) : _client = client;

  final ApiClient _client;

  List<MemoryItem> _items = const [];
  bool _loading = false;
  bool _hasFetched = false;
  String? _error;
  String? _pendingId;

  bool get loading => _loading;
  bool get hasFetched => _hasFetched;
  String? get error => _error;
  bool get isEmpty => _items.isEmpty;
  bool isPending(String id) => _pendingId == id;

  /// Memories grouped into 4 buckets, empty buckets dropped, sorted within
  /// bucket by updatedAt desc (createdAt fallback). Computed on each read so
  /// delete + add stay simple — the list is small (<500 typical).
  List<MemoryGroup> get groups {
    final byBucket = <MemoryBucket, List<MemoryItem>>{};
    for (final item in _items) {
      byBucket.putIfAbsent(item.bucket, () => []).add(item);
    }
    final result = <MemoryGroup>[];
    for (final bucket in MemoryBucket.values) {
      final items = byBucket[bucket];
      if (items == null || items.isEmpty) continue;
      items.sort((a, b) {
        final ad = a.updatedAt ?? a.createdAt;
        final bd = b.updatedAt ?? b.createdAt;
        if (ad == null && bd == null) return 0;
        if (ad == null) return 1;
        if (bd == null) return -1;
        return bd.compareTo(ad);
      });
      result.add(MemoryGroup(bucket: bucket, items: items));
    }
    return result;
  }

  /// Idempotent first load. Subsequent calls no-op unless [force].
  Future<void> load({bool force = false}) async {
    if (_loading) return;
    if (_hasFetched && !force) return;

    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final res = await _client.get('v3/memories?limit=200&offset=0');
      final body = jsonDecode(res.body);
      final list = body is List
          ? body
              .whereType<Map>()
              .map((m) => MemoryItem.fromJson(Map<String, dynamic>.from(m)))
              .toList(growable: false)
          : const <MemoryItem>[];
      _items = list;
      _hasFetched = true;
    } catch (e, st) {
      debugPrint('[LibraryProvider] load failed: $e\n$st');
      _error = e.toString();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// Optimistic delete. Removes locally, posts DELETE; rolls back at the
  /// original index if the server rejects so the row reappears in place.
  Future<bool> delete(String id) async {
    if (_pendingId != null) return false;
    final idx = _items.indexWhere((m) => m.id == id);
    if (idx == -1) return false;
    final removed = _items[idx];
    _pendingId = id;
    _items = [..._items]..removeAt(idx);
    notifyListeners();
    try {
      await _client.delete('v3/memories/$id');
      return true;
    } catch (e) {
      debugPrint('[LibraryProvider] delete($id) failed: $e');
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
