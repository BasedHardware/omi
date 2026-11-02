import 'dart:collection';

import 'wal.dart';

/// Tracks all custody buckets together. Moving a row between buckets is not a
/// deletion. Only changed identities are visited when taking a disk delta.
class WalIndexInventory {
  final _uploaded = LinkedHashSet<Wal>.identity();
  Iterable<Wal> get uploaded => _uploaded;
  final _members = HashMap<Wal, int>.identity();
  final _tokens = Expando<int>('walIndexToken');
  final _dirty = LinkedHashSet<Wal>.identity();
  final _removed = <int>{};
  final _indexedTokens = <int>{};
  var _nextToken = 0;
  bool seedsExistingIndex = false;
  String? seedPath;
  final _seeded = HashSet<Wal>.identity();

  void primeLoaded(Iterable<Wal> loaded) {
    // Only a fresh owner can adopt the disk token namespace. Reloads into an
    // existing owner use ordinary deltas, preserving retired/foreign identities.
    if (_nextToken != 0 || _members.isNotEmpty) return;
    for (final wal in loaded) {
      final token = wal.loadedIndexToken;
      if (token == null) continue;
      seedsExistingIndex = true;
      seedPath = wal.loadedIndexSource;
      _tokens[wal] = token;
      _indexedTokens.add(token);
      _seeded.add(wal);
      if (token >= _nextToken) _nextToken = token + 1;
    }
  }

  void _changed(Wal wal) {
    _dirty.add(wal);
    if (wal.status == WalStatus.uploaded) {
      _uploaded.add(wal);
    } else {
      _uploaded.remove(wal);
    }
  }

  void add(Wal wal) {
    final count = _members[wal] ?? 0;
    _members[wal] = count + 1;
    if (count != 0) return;
    _tokens[wal] ??= _nextToken++;
    _removed.remove(_tokens[wal]);
    if (!_seeded.remove(wal) || wal.storage == WalStorage.mem) _dirty.add(wal);
    if (wal.status == WalStatus.uploaded) _uploaded.add(wal);
    wal.addChangeListener(_changed);
  }

  void remove(Wal wal) {
    final count = _members[wal]!;
    if (count > 1) {
      _members[wal] = count - 1;
      return;
    }
    _members.remove(wal);
    _uploaded.remove(wal);
    wal.removeChangeListener(_changed);
    _dirty.remove(wal);
    if (_indexedTokens.contains(_tokens[wal])) _removed.add(_tokens[wal]!);
  }

  WalTrackedList track(Iterable<Wal> source) => WalTrackedList._(this, source);

  /// Exceptional recovery only: disk order may have compacted since tokens
  /// were assigned. Rebuild with our namespace, including every custody bucket,
  /// rather than adopting possibly stale disk rows under the wrong tokens.
  Map<int, Map<String, dynamic>> recoverySnapshot() => {
        for (final wal in _members.keys)
          if (wal.storage != WalStorage.mem) _tokens[wal]!: wal.toJson(),
      };

  /// Serialization happens synchronously at admission, before any await. The
  /// worker never receives a mutable Wal (or its listener graph/full inventory).
  WalIndexDelta takeDelta() {
    final changed = <int, Map<String, dynamic>>{};
    final disk = <Wal>[];
    final removed = {..._removed};
    final dirty = _dirty.toList();
    for (final wal in dirty) {
      final token = _tokens[wal]!;
      if (wal.storage == WalStorage.mem) {
        if (_indexedTokens.remove(token)) removed.add(token);
      } else {
        changed[token] = wal.toJson();
        _indexedTokens.add(token);
        if (wal.storage == WalStorage.disk) disk.add(wal);
      }
    }
    _indexedTokens.removeAll(removed);
    _dirty.clear();
    _removed.clear();
    return WalIndexDelta(changed, removed.toList(), disk, dirty);
  }

  void retry(WalIndexDelta delta) {
    _removed.addAll(delta.removed);
    for (final wal in delta.dirty) {
      if (_members.containsKey(wal)) {
        _dirty.add(wal);
      } else {
        _removed.add(_tokens[wal]!);
      }
    }
  }
}

class WalIndexDelta {
  WalIndexDelta(this.changed, this.removed, this.disk, this.dirty);
  final Map<int, Map<String, dynamic>> changed;
  final List<int> removed;
  final List<Wal> disk;
  final List<Wal> dirty;
  bool get isEmpty => changed.isEmpty && removed.isEmpty;
}

class WalTrackedList extends ListBase<Wal> {
  WalTrackedList._(this.inventory, Iterable<Wal> source) : _items = List.of(source) {
    for (final wal in _items) {
      _register(wal);
    }
  }
  final WalIndexInventory inventory;
  final List<Wal> _items;
  int revision = 0;
  final _identities = HashMap<Wal, int>.identity();
  bool containsIdentity(Wal wal) => _identities.containsKey(wal);
  void _register(Wal wal) {
    _identities.update(wal, (n) => n + 1, ifAbsent: () => 1);
    inventory.add(wal);
  }

  void _unregister(Wal wal) {
    final count = _identities[wal]!;
    if (count == 1) {
      _identities.remove(wal);
    } else {
      _identities[wal] = count - 1;
    }
    inventory.remove(wal);
  }

  @override
  int get length => _items.length;
  @override
  set length(int value) {
    if (value > length) throw UnsupportedError('WAL lists cannot contain null');
    if (value != length) revision++;
    while (_items.length > value) {
      _unregister(_items.removeLast());
    }
  }

  @override
  Wal operator [](int index) => _items[index];
  @override
  void operator []=(int index, Wal value) {
    final old = _items[index];
    if (identical(old, value)) return;
    revision++;
    _register(value);
    _items[index] = value;
    _unregister(old);
  }

  @override
  void add(Wal element) {
    revision++;
    _items.add(element);
    _register(element);
  }

  @override
  void addAll(Iterable<Wal> iterable) {
    for (final wal in iterable) {
      add(wal);
    }
  }

  @override
  void insert(int index, Wal element) {
    revision++;
    _items.insert(index, element);
    _register(element);
  }

  @override
  Wal removeAt(int index) {
    final wal = _items.removeAt(index);
    revision++;
    _unregister(wal);
    return wal;
  }

  @override
  bool remove(Object? element) {
    if (element is! Wal) return false;
    final index = _items.indexOf(element);
    if (index < 0) return false;
    removeAt(index);
    return true;
  }

  @override
  void removeWhere(bool Function(Wal) test) {
    _items.removeWhere((wal) {
      if (!test(wal)) return false;
      revision++;
      _unregister(wal);
      return true;
    });
  }
}
