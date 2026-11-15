import 'dart:async';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/utils/logger.dart';

// Owns debounced persistence of task sort order and indent level.
//
// An edit stays pending until the server acknowledges that exact value, so a
// list read cannot revert it on screen and a failed write is retried. One
// write is in flight at a time, so an older layout cannot land after a newer
// one. Acknowledged values are still overlaid on reads that started before the
// acknowledgement, because their server snapshot may predate the write.

typedef BatchUpdateActionItemsRequest = Future<bool> Function(List<Map<String, dynamic>> items);

class TaskLayoutWrites {
  TaskLayoutWrites(this._send);

  final BatchUpdateActionItemsRequest _send;
  final Map<String, int> _sortOrders = {};
  final Map<String, int> _indentLevels = {};
  // ponytail: kept for the session (one entry per edited task); prune by in-flight read marks if this ever grows.
  final Map<String, ({int value, int ack})> _ackedSortOrders = {};
  final Map<String, ({int value, int ack})> _ackedIndentLevels = {};
  int _acks = 0;
  Timer? _debounce;
  Future<void>? _flush;
  bool _flushRequestedDuringSend = false;
  int _generation = 0;

  /// Capture before a task read starts; pass to [overlayFor] for its rows.
  int get readMark => _acks;

  void setSortOrder(String id, int sortOrder) {
    _sortOrders[id] = sortOrder;
    _schedule();
  }

  void setIndentLevel(String id, int indentLevel) {
    _indentLevels[id] = indentLevel;
    _schedule();
  }

  /// Re-applies unacknowledged edits, and edits acknowledged after [readMark],
  /// to rows from a read that started at [readMark].
  ActionItemWithMetadata Function(ActionItemWithMetadata) overlayFor(int readMark) => (item) {
        final ackedSort = _ackedSortOrders[item.id];
        final ackedIndent = _ackedIndentLevels[item.id];
        final sortOrder =
            _sortOrders[item.id] ?? (ackedSort != null && ackedSort.ack > readMark ? ackedSort.value : null);
        final indentLevel =
            _indentLevels[item.id] ?? (ackedIndent != null && ackedIndent.ack > readMark ? ackedIndent.value : null);
        if (sortOrder == null && indentLevel == null) return item;
        return item.copyWith(sortOrder: sortOrder, indentLevel: indentLevel);
      };

  /// Called after any successful task read: the server is reachable again.
  void retryPending() {
    if (_sortOrders.isEmpty && _indentLevels.isEmpty) return;
    // A send in flight may still fail; remember that the server answered meanwhile.
    if (_flush != null) {
      _flushRequestedDuringSend = true;
    } else {
      _schedule();
    }
  }

  /// Drops pending edits, e.g. on sign-out; an in-flight write cannot restore them.
  void clear() {
    _generation++;
    _debounce?.cancel();
    _sortOrders.clear();
    _indentLevels.clear();
    _ackedSortOrders.clear();
    _ackedIndentLevels.clear();
  }

  Future<void> flush() {
    _debounce?.cancel();
    if (_flush != null) {
      _flushRequestedDuringSend = true;
      return _flush!;
    }
    return _flush = _sendPending().whenComplete(() {
      _flush = null;
      // An edit made while the send was in flight lost its timer to this send.
      // If the send failed, give that edit its own attempt.
      final retry = _flushRequestedDuringSend && (_sortOrders.isNotEmpty || _indentLevels.isNotEmpty);
      _flushRequestedDuringSend = false;
      if (retry) _schedule();
    });
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
      _acks++;
      sortOrders.forEach((id, value) {
        if (_sortOrders[id] == value) _sortOrders.remove(id);
        _ackedSortOrders[id] = (value: value, ack: _acks);
      });
      indentLevels.forEach((id, value) {
        if (_indentLevels[id] == value) _indentLevels.remove(id);
        _ackedIndentLevels[id] = (value: value, ack: _acks);
      });
      _flushRequestedDuringSend = false;
    }
  }
}
