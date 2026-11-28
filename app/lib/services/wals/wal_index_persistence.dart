part of 'local_wal_sync.dart';

extension _WalIndexPersistence on LocalWalSyncImpl {
  Future<bool> _saveWalsToFile(int generation) async {
    if (!_isCurrent(generation)) return false;
    if (_initialIndexAdmissionPending) {
      await _initializeWals();
      if (_initialIndexAdmissionPending) return false;
    }
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
    // Snapshot the held rows admitted by this write. Keep pending marks on
    // failure so whichever save commits the rows can count them once.
    final emitHeldTailCount = _lifecycleHeldTailCount;
    final lifecycleHeldTails = emitHeldTailCount == null
        ? const <Wal>[]
        : delta.disk.where((wal) => wal.holdForUser && _pendingLifecycleHeldTails[wal] == true).toList();
    final write = _writeIndexDelta(delta);
    _indexWriteInFlight = write;
    try {
      await write;
      _confirmedDurableWalKeys.addAll(confirmedKeys);
      if (lifecycleHeldTails.isNotEmpty) {
        for (final wal in lifecycleHeldTails) {
          _pendingLifecycleHeldTails[wal] = null;
        }
        try {
          emitHeldTailCount!(lifecycleHeldTails.length);
        } catch (_) {
          Logger.debug('Lifecycle held pendant tail count unavailable');
        }
      }
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
    // Hermetic tests and the kill switch take full snapshots; normal saves send deltas.
    final persist = _persistWalsOverride ?? (await _deltaIndexAllowed ? null : _saveFullSnapshot);
    if (persist != null) {
      await persist([
        ..._retiredWals.where((w) => w.storage != WalStorage.mem),
        ..._foreignWals.where((w) => w.storage != WalStorage.mem),
        ..._wals.where((w) => w.storage != WalStorage.mem),
      ]);
    } else {
      WalIndexWorker? worker;
      try {
        final rebuild = _rebuildIndexWorker;
        // Capture before awaiting startup; later mutations remain dirty for the
        // next save. Recovery includes admitted deltas even if disk is stale.
        final snapshot = rebuild ? _indexInventory.recoverySnapshot() : null;
        worker = await (_indexWorker ??= WalFileManager.createIndexWorker(
            seedFromDisk: !rebuild && _indexInventory.seedsExistingIndex,
            seedPath: rebuild ? null : _indexInventory.seedPath));
        // A replacement can survive a failed disk write with its rows cached.
        // Keep sending removals on retry even when rebuilding a full snapshot.
        await worker.apply(snapshot ?? delta.changed, delta.removed);
        _rebuildIndexWorker = false;
      } catch (_) {
        if (worker == null || worker.isDead) {
          _indexWorker = null;
          _rebuildIndexWorker = true;
        }
        rethrow;
      }
    }
  }

  static Future<void> _saveFullSnapshot(List<Wal> wals) async {
    if (!await WalFileManager.saveWals(wals)) throw const FileSystemException('wal index save failed');
  }
}
