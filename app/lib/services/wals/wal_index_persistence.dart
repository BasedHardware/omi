part of 'local_wal_sync.dart';

extension _WalIndexPersistence on LocalWalSyncImpl {
  Future<bool> _saveWalsToFile(int generation) async {
    if (!_isCurrent(generation)) return false;
    // A save joins all earlier disk writes. After a failure the next caller
    // retries dirty identities; no caller can claim durable before rename.
    final pending = _indexWriteInFlight;
    if (pending != null) {
      try {
        await pending;
      } catch (_) {/* retry below */}
      if (!_isCurrent(generation)) return false;
      return _saveWalsToFile(generation);
    }
    final delta = _indexInventory.takeDelta();
    if (delta.isEmpty && !_forceIndexWrite) return true;
    _forceIndexWrite = false;
    // Capture keys at admission, never from mutable rows after an await.
    final confirmedKeys = delta.disk.map(_durableKey).toList();
    final write = _writeIndexDelta(delta);
    _indexWriteInFlight = write;
    try {
      await write;
      _confirmedDurableWalKeys.addAll(confirmedKeys);
      return true;
    } catch (_) {
      _indexInventory.retry(delta);
      _forceIndexWrite = true;
      rethrow;
    } finally {
      if (identical(_indexWriteInFlight, write)) _indexWriteInFlight = null;
    }
  }

  Future<void> _writeIndexDelta(WalIndexDelta delta) async {
    if (_persistWalsOverride != null) {
      // Legacy hermetic seam only; production never constructs a full snapshot.
      await _persistWalsOverride!([
        ..._retiredWals.where((w) => w.storage != WalStorage.mem),
        ..._foreignWals.where((w) => w.storage != WalStorage.mem),
        ..._wals.where((w) => w.storage != WalStorage.mem),
      ]);
    } else {
      final WalIndexWorker worker;
      try {
        worker =
            await (_indexWorker ??= WalFileManager.createIndexWorker(seedFromDisk: _indexInventory.seedsExistingIndex));
      } catch (_) {
        _indexWorker = null; // A failed spawn must be retryable too.
        rethrow;
      }
      await worker.apply(delta.changed, delta.removed);
    }
  }
}
