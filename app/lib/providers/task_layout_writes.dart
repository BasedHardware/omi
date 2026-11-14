import 'dart:async';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/utils/logger.dart';

// Owns debounced persistence of task sort order and indent level.
//
// An edit stays pending until the server acknowledges that exact value, so a
// list read cannot revert it on screen and a failed write is retried. One
// write is in flight at a time, so an older layout cannot land after a newer
// one.

typedef BatchUpdateActionItemsRequest = Future<bool> Function(List<Map<String, dynamic>> items);

class TaskLayoutWrites {
  TaskLayoutWrites(this._send);

  final BatchUpdateActionItemsRequest _send;
  final Map<String, int> _sortOrders = {};
  final Map<String, int> _indentLevels = {};
  Timer? _debounce;
  Future<void>? _flush;
  int _generation = 0;

  void setSortOrder(String id, int sortOrder) {
    _sortOrders[id] = sortOrder;
    _schedule();
  }

  void setIndentLevel(String id, int indentLevel) {
    _indentLevels[id] = indentLevel;
    _schedule();
  }

  /// Re-applies unacknowledged edits to a row read from the server.
  ActionItemWithMetadata overlay(ActionItemWithMetadata item) {
    final sortOrder = _sortOrders[item.id];
    final indentLevel = _indentLevels[item.id];
    if (sortOrder == null && indentLevel == null) return item;
    return item.copyWith(sortOrder: sortOrder, indentLevel: indentLevel);
  }

  /// Called after a successful list read: the server is reachable again.
  void retryPending() {
    if (_flush == null && (_sortOrders.isNotEmpty || _indentLevels.isNotEmpty)) _schedule();
  }

  /// Drops pending edits, e.g. on sign-out; an in-flight write cannot restore them.
  void clear() {
    _generation++;
    _debounce?.cancel();
    _sortOrders.clear();
    _indentLevels.clear();
  }

  Future<void> flush() {
    _debounce?.cancel();
    return _flush ??= _sendPending().whenComplete(() => _flush = null);
  }

  void _schedule() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 500), flush);
  }

  Future<void> _sendPending() async {
    final generation = _generation;
    while (generation == _generation) {
      final sortOrders = Map<String, int>.of(_sortOrders);
      final indentLevels = Map<String, int>.of(_indentLevels);
      if (sortOrders.isEmpty && indentLevels.isEmpty) return;

      final items = [
        for (final id in {...sortOrders.keys, ...indentLevels.keys})
          {
            'id': id,
            if (sortOrders.containsKey(id)) 'sort_order': sortOrders[id],
            if (indentLevels.containsKey(id)) 'indent_level': indentLevels[id],
          },
      ];
      bool saved;
      try {
        saved = await _send(items);
      } catch (e) {
        Logger.debug('Error saving task layout: $e');
        saved = false;
      }
      // Failed edits stay pending; the next edit or list read retries them.
      if (!saved || generation != _generation) return;
      sortOrders.forEach((id, value) {
        if (_sortOrders[id] == value) _sortOrders.remove(id);
      });
      indentLevels.forEach((id, value) {
        if (_indentLevels[id] == value) _indentLevels.remove(id);
      });
    }
  }
}
