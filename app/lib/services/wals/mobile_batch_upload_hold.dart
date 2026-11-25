// Schedule transport of sealed mobile Standard batch WALs. The existing
// journal and WAL index retain custody of the files across a restart.
import 'dart:async';

import 'package:omi/services/wals/wal.dart';

enum MobileBatchHoldState {
  background('bg300', Duration(seconds: 300)),
  foregroundPreview('fg_preview300', Duration(seconds: 300)),
  foreground('fg60', Duration(seconds: 60));

  const MobileBatchHoldState(this.header, this.limit);
  final String header;
  final Duration limit;
}

/// A fresh process has no holds, so journal recovery can upload immediately.
class MobileBatchUploadHold {
  MobileBatchUploadHold({
    required this.enabled,
    required void Function() wake,
    DateTime Function()? now,
    Future<void> Function()? refreshFlags,
    bool foreground = true,
  })  : _wake = wake,
        _now = now ?? DateTime.now,
        _refreshFlags = refreshFlags,
        _foreground = foreground;

  static const _flagTick = Duration(seconds: 15);
  static const _flagRefreshInterval = Duration(seconds: 60);

  final bool Function() enabled;
  final void Function() _wake;
  final DateTime Function() _now;
  final Future<void> Function()? _refreshFlags;
  final _pending = <String, _HeldWal>{};
  var _released = Expando<MobileBatchHoldState>();
  bool _foreground;
  bool _preview = false;
  Timer? _timer;
  DateTime? _lastFlagRefresh;

  MobileBatchHoldState get _state => !_foreground
      ? MobileBatchHoldState.background
      : _preview
          ? MobileBatchHoldState.foregroundPreview
          : MobileBatchHoldState.foreground;

  void sealed(Wal wal) {
    if (!enabled() || wal.recordingSessionId?.isNotEmpty != true) return;
    final sealedAt = _now();
    // Keep the timestamp through process eviction. The stored hint never
    // reinstates a hold when the WAL index is loaded.
    wal.mobileBatchHold = (sealedAtMs: sealedAt.millisecondsSinceEpoch, state: _state.header);
    _pending[wal.id] = _HeldWal(wal, sealedAt);
  }

  /// False means this seal uses its original immediate upload wake.
  bool published(Wal wal) {
    final pending = _pending[wal.id];
    if (pending != null) {
      pending.published = true;
      tick();
      return true;
    }
    if (_released[wal] == null) return false;
    // A foreground or end signal arrived while the index write was in flight.
    _wake();
    return true;
  }

  /// A publication failure or an explicit single-file upload ends this hold.
  void forget(Wal wal) {
    if (_pending.remove(wal.id) != null) tick();
  }

  bool isHeld(Wal wal) => _pending.containsKey(wal.id);

  String label(Wal wal) => enabled() ? _released[wal]?.header ?? indexedLabel(wal) : 'none';

  static String indexedLabel(Wal wal) {
    final state = wal.mobileBatchHold?.state;
    return state != null && MobileBatchHoldState.values.any((value) => value.header == state) ? state : 'none';
  }

  static int? oldestSealedAtMs(Iterable<Wal> files) {
    int? oldest;
    for (final wal in files) {
      final sealedAtMs = wal.mobileBatchHold?.sealedAtMs;
      if (sealedAtMs != null && (oldest == null || sealedAtMs < oldest)) oldest = sealedAtMs;
    }
    return oldest;
  }

  void setForeground(bool foreground) {
    if (_foreground == foreground) return;
    final previous = _state;
    _foreground = foreground;
    if (foreground) _release(_pending.values.toList(), previous);
    tick();
  }

  void setPreview(bool running) {
    if (_preview == running) return;
    _preview = running;
    tick();
  }

  void captureEnded(String recordingSessionId) {
    _release(_pending.values.where((entry) => entry.wal.recordingSessionId == recordingSessionId).toList(), _state);
    tick();
  }

  void _release(List<_HeldWal> entries, MobileBatchHoldState state) {
    var readyToUpload = false;
    for (final entry in entries) {
      _pending.remove(entry.wal.id);
      _released[entry.wal] = state;
      readyToUpload |= entry.published;
    }
    if (readyToUpload) _wake();
  }

  void tick() {
    _timer?.cancel();
    _timer = null;
    if (_pending.isEmpty) return;
    final state = _state;
    if (!enabled()) {
      _release(_pending.values.toList(), state);
      return;
    }
    final now = _now();
    final groups = <String, List<_HeldWal>>{};
    for (final entry in _pending.values) {
      if (entry.published) groups.putIfAbsent(entry.wal.recordingSessionId!, () => []).add(entry);
    }
    var nextTick = _flagTick;
    for (final group in groups.values) {
      var remaining = state.limit;
      var audioMicros = 0;
      for (final entry in group) {
        audioMicros += entry.wal.totalFrames * Duration.microsecondsPerSecond ~/ entry.wal.codec.getFramesPerSecond();
        final age = now.difference(entry.sealedAt);
        final untilDue = age.isNegative ? Duration.zero : state.limit - age;
        if (untilDue < remaining) remaining = untilDue;
      }
      if (audioMicros >= state.limit.inMicroseconds || remaining <= Duration.zero) {
        _release(group, state);
      } else if (remaining < nextTick) {
        nextTick = remaining;
      }
    }
    if (_pending.isEmpty) return;
    _timer = Timer(nextTick, tick);
    final refreshFlags = _refreshFlags;
    final last = _lastFlagRefresh;
    if (refreshFlags != null && (last == null || now.difference(last) >= _flagRefreshInterval)) {
      _lastFlagRefresh = now;
      unawaited(refreshFlags().then((_) => tick()));
    }
  }

  void clear() {
    _timer?.cancel();
    _timer = null;
    _pending.clear();
    _released = Expando<MobileBatchHoldState>();
    _lastFlagRefresh = null;
  }
}

class _HeldWal {
  _HeldWal(this.wal, this.sealedAt);
  final Wal wal;
  final DateTime sealedAt;
  bool published = false;
}
