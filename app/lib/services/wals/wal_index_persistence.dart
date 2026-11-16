part of 'local_wal_sync.dart';

extension _WalIndexPersistence on LocalWalSyncImpl {
  Future<String> _uniqueStorageFileName(Wal wal) async {
    final claimable = captureEvidenceWalClaimable(wal);
    final planned = wal.filePath;
    var name = claimable && planned != null && planned.isNotEmpty ? planned.split('/').last : wal.getFileName();
    if (!_fileReferencedByOtherWal(wal, name) && !await _localFileExistsByName(name)) return name;
    for (;;) {
      final candidate = walCollisionName(name, _storageFileSeq++, claimable);
      if (!_fileReferencedByOtherWal(wal, candidate) && !await _localFileExistsByName(candidate)) {
        return candidate;
      }
    }
  }

  Future<bool> _localFileExistsByName(String fileName) async {
    final path = await Wal.getFilePath(fileName);
    if (path == null) return false;
    return await File(path).exists() || await WalWriteIntent.exists(File(path).parent, fileName);
  }

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
    final write = () async {
      await _writeIndexDelta(delta);
      for (final wal in delta.disk.where(WalWriteIntent.hasPending)) {
        // Cleanup is best effort AFTER commit; retrying a leftover intent is
        // idempotent. Never turn a committed write into a failed index delta.
        try {
          if (wal.filePath != null && !wal.filePath!.contains('/')) {
            final directory = await getApplicationDocumentsDirectory();
            await WalWriteIntent.retire(directory, wal);
          }
        } on FileSystemException catch (e) {
          Logger.debug('WAL intent retirement deferred: $e');
        }
      }
    }();
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
