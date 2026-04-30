import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:nooto_v2/services/api_client.dart';

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
  });

  final String id;
  final String description;
  final bool completed;
  final DateTime? createdAt;
  final DateTime? dueAt;
  final String? conversationId;

  factory ActionItem.fromJson(Map<String, dynamic> json) {
    return ActionItem(
      id: json['id'] as String,
      description: json['description'] as String? ?? '',
      completed: json['completed'] as bool? ?? false,
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'] as String).toLocal()
          : null,
      dueAt: json['due_at'] != null
          ? DateTime.parse(json['due_at'] as String).toLocal()
          : null,
      conversationId: json['conversation_id'] as String?,
    );
  }

  ActionItem copyWith({bool? completed}) => ActionItem(
        id: id,
        description: description,
        completed: completed ?? this.completed,
        createdAt: createdAt,
        dueAt: dueAt,
        conversationId: conversationId,
      );
}

/// Read-only port of legacy `ActionItemsProvider`: fetches the user's open
/// commitments from `/v1/action-items` and lets a card generator surface them
/// on Home. `complete(id)` does an optimistic update + server confirm; on
/// failure the local state rolls back so the card reappears next refresh.
class ActionItemsProvider extends ChangeNotifier {
  ActionItemsProvider({required ApiClient client}) : _client = client;

  final ApiClient _client;
  final List<ActionItem> _items = [];
  bool _loading = false;
  bool _ready = false;

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
      if (res.statusCode == 200) {
        final body = jsonDecode(res.body) as Map<String, dynamic>;
        final list = (body['action_items'] as List<dynamic>? ?? const [])
            .map((e) => ActionItem.fromJson(e as Map<String, dynamic>))
            .toList();
        _items
          ..clear()
          ..addAll(list);
      }
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
      final res = await _client.patch(
        'v1/action-items/$id/completed?completed=true',
      );
      if (res.statusCode == 200) return true;
      _items[idx] = original;
      notifyListeners();
      return false;
    } catch (_) {
      _items[idx] = original;
      notifyListeners();
      return false;
    }
  }
}
