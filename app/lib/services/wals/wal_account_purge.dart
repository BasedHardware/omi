part of 'local_wal_sync.dart';

/// Recordings of accounts deleted from this phone, and the file-ownership checks
/// every deletion of a recording goes through.
extension _WalAccountPurge on LocalWalSyncImpl {
  bool _fileReferencedByOtherWal(Wal wal, String fileName) {
    for (final other in [..._retiredWals, ..._foreignWals, ..._wals]) {
      if (identical(other, wal)) continue;
      final otherPath = other.filePath;
      final otherName = (otherPath != null && otherPath.isNotEmpty) ? otherPath.split('/').last : other.getFileName();
      if (otherName == fileName) return true;
    }
    return false;
  }

  bool _isTrackedWal(Wal wal) =>
      _wals.any((w) => identical(w, wal)) ||
      _retiredWals.any((w) => identical(w, wal)) ||
      _foreignWals.any((w) => identical(w, wal));

  /// Foreign-owner records left by accounts deleted from this phone are removed at
  /// load instead of parked forever: the user asked for that data to go, and a parked
  /// backlog of a dead account would otherwise be rewritten into the index on every
  /// save for the life of the install. Returns false when the session moved on.
  Future<bool> _purgeDeletedAccountWalsAtLoad(int generation) async {
    final deleted = (await readDeletedAccountUids()).toSet();
    final receiptPurgeOwners = LiveWalReceipt.purgeEnabled ? deleted : const <String>{};
    final startupReferences =
        receiptPurgeOwners.isEmpty ? null : await WalFileManager.captureLiveWalPurgeSnapshotForPendingReceipts();
    // Receipt-only files are drained in small batches after `_walReady` opens.
    // This leaves index admission and the first recording view independent of
    // the size of the receipt archive. Capture references only if pending
    // receipts exist, then reuse that set after readiness so an index rewrite
    // cannot erase references from the prior backup generation.
    _deletedAccountReceiptPurgeOwners = receiptPurgeOwners;
    _deletedAccountReceiptPurgeSnapshot = startupReferences?.snapshot;
    _deletedAccountReceiptPurgeReferencesComplete =
        receiptPurgeOwners.isEmpty || startupReferences == null || !startupReferences.referenceScanIncomplete;
    final doomed = deleted.isEmpty ? const <Wal>[] : _foreignWals.where((w) => deleted.contains(w.ownerUid)).toList();
    final removed = <String, int>{};
    for (final wal in doomed) {
      if (!_isCurrent(generation)) break;
      if (await _deleteWal(wal, generation: generation)) {
        removed.update(wal.ownerUid!, (n) => n + 1, ifAbsent: () => 1);
      }
    }
    if (removed.isNotEmpty && _isCurrent(generation)) await _saveWalsToFile(generation);
    for (final entry in removed.entries) {
      DebugLogManager.logEvent('wal_orphan_purge', {
        'phase': 'load',
        'owner_uid': entry.key,
        'count': entry.value,
        'reference_scan_incomplete': !_deletedAccountReceiptPurgeReferencesComplete,
      });
    }
    if (_isCurrent(generation)) return true;
    if (!_walReady.isCompleted) _walReady.complete();
    return false;
  }

  /// Purges active, retired and foreign recordings owned by [uid].
  /// Unstamped index rows count as the signed-in account's. Unindexed files
  /// need an exact receipt.
  Future<int> _purgeAccountWals(String uid) async {
    if (uid.isEmpty) return 0;
    final generation = _sessionGeneration;
    // Startup may still be admitting a receipt into the index.
    await _initializationInFlight;
    if (!_isCurrent(generation)) return 0;
    final current = _currentWalOwnerUid();
    bool owned(Wal wal) => wal.ownerUid == uid || (wal.ownerUid == null && uid == current);
    final doomed = [..._wals, ..._retiredWals, ..._foreignWals].where(owned).toList();
    final unindexedPurge = await _purgeUnindexedAccountWals({uid}, generation);
    final unindexedRemoved = unindexedPurge.removed;
    var referenceScanIncomplete = unindexedPurge.referenceScanIncomplete;
    final needsPurgeSnapshot = doomed.any((wal) =>
        LiveWalReceipt.isManagedBasename(path.basename(wal.filePath ?? '')) &&
        !_confirmedDurableWalKeys.contains(_durableKey(wal)));
    final LiveWalPurgeSnapshot? purgeSnapshot;
    if (needsPurgeSnapshot) {
      purgeSnapshot = await WalFileManager.captureLiveWalPurgeSnapshot();
      if (purgeSnapshot == null) referenceScanIncomplete = true;
    } else {
      purgeSnapshot = null;
    }
    var removed = 0;
    for (final wal in doomed) {
      if (!_isCurrent(generation)) break;
      if (await _deleteWal(wal, generation: generation, accountPurge: true, liveWalPurgeSnapshot: purgeSnapshot)) {
        removed++;
      }
    }
    referenceScanIncomplete = referenceScanIncomplete || purgeSnapshot?.refreshFailed == true;
    if (removed > 0 && _isCurrent(generation)) {
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
    }
    DebugLogManager.logEvent('wal_orphan_purge', {
      'phase': 'account_deleted',
      'owner_uid': uid,
      'count': removed,
      'unindexed_removed': unindexedRemoved,
      'reference_scan_incomplete': referenceScanIncomplete,
      'requested': doomed.length,
    });
    return removed + unindexedRemoved;
  }

  Future<LiveWalReceiptPurgeResult> _purgeUnindexedAccountWals(
    Set<String> owners,
    int generation, {
    LiveWalPurgeSnapshot? initialReferenceSnapshot,
    bool initialReferenceScanComplete = true,
  }) async {
    if (!LiveWalReceipt.purgeEnabled || owners.isEmpty || !_isCurrent(generation)) {
      return (removed: 0, referenceScanIncomplete: false);
    }
    return WalFileManager.purgeUnindexedLiveWalReceipts(
      owners: owners,
      reservedNames: _liveWalReservedNames(),
      mayDelete: (name) => _isCurrent(generation) && !_liveWalReservedNames().contains(name.toLowerCase()),
      initialReferenceSnapshot: initialReferenceSnapshot,
      initialReferenceScanComplete: initialReferenceScanComplete,
      shouldContinue: () => _isCurrent(generation),
    );
  }

  Future<void> _purgeDeletedAccountReceiptsAfterReady(
    Set<String> owners,
    int generation, {
    LiveWalPurgeSnapshot? initialReferenceSnapshot,
    bool initialReferenceScanComplete = true,
  }) async {
    final result = await _purgeUnindexedAccountWals(
      owners,
      generation,
      initialReferenceSnapshot: initialReferenceSnapshot,
      initialReferenceScanComplete: initialReferenceScanComplete,
    );
    if (!_isCurrent(generation)) return;
    DebugLogManager.logEvent('wal_orphan_purge', {
      'phase': 'load_unindexed_receipts',
      'count': 0,
      'unindexed_removed': result.removed,
      'reference_scan_incomplete': result.referenceScanIncomplete,
    });
  }

  /// Synchronously reconciles active (`_wals`), foreign (`_foreignWals`), and
  /// retired (`_retiredWals`) buckets when a signed-in user is present.
  bool _reconcileCurrentOwnerSync() {
    final uid = SharedPreferencesUtil().uid;
    if (uid.isEmpty) return false;
    var changed = false;

    bool belongsToCurrent(Wal wal) => _walAdmittedAtLoad(wal);

    if (_wals.any((wal) => !belongsToCurrent(wal))) {
      final retained = <Wal>[];
      for (final wal in _wals) {
        if (belongsToCurrent(wal)) {
          retained.add(wal);
        } else {
          _foreignWals.add(wal);
        }
      }
      _wals = retained;
      changed = true;
    }

    final restored = <Wal>[];
    _foreignWals.removeWhere((wal) {
      if (belongsToCurrent(wal)) {
        restored.add(wal);
        return true;
      }
      return false;
    });
    _retiredWals.removeWhere((wal) {
      if (belongsToCurrent(wal)) {
        restored.add(wal);
        return true;
      }
      return false;
    });

    if (restored.isNotEmpty) {
      changed = true;
      final existingKeys = _wals.map((w) => (w.id, w.codec, w.seconds, w.totalFrames, w.filePath)).toSet();
      final nextActive = List<Wal>.from(_wals);
      for (final wal in restored) {
        wal.isSyncing = false;
        wal.syncStartedAt = null;
        wal.syncEtaSeconds = null;
        if (existingKeys.add((wal.id, wal.codec, wal.seconds, wal.totalFrames, wal.filePath))) {
          nextActive.add(wal);
          changed = true;
        }
      }
      if (changed) {
        _wals = nextActive;
      }
    }

    if (changed) {
      heldRevision.value++;
    }
    return changed;
  }

  Future<void> _reconcileAndPersistCurrentOwner() async {
    final generation = _sessionGeneration;
    if (_reconcileCurrentOwnerSync() && _isCurrent(generation)) {
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
    }
  }

  Future<void> _rehydrateForCurrentUser() async {
    final generation = _sessionGeneration;
    final uid = SharedPreferencesUtil().uid;
    await walReady;
    if (!_isCurrent(generation) || uid != SharedPreferencesUtil().uid) return;
    await _reconcileAndPersistCurrentOwner();
  }
}
