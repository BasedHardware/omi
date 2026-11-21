part of 'local_wal_sync.dart';

// Replays exact live write receipts through the same index admission as
// external WALs. The capture queue can still write fresh audio during startup.
extension _LiveWalReceiptReplay on LocalWalSyncImpl {
  Set<String> _liveWalReservedNames() => {
        for (final bucket in [_wals, _foreignWals, _retiredWals])
          for (final wal in bucket)
            if (wal.filePath case final name? when LiveWalReceipt.isManagedBasename(path.basename(name)))
              path.basename(name).toLowerCase(),
        for (final name in _liveWalWrites) name.toLowerCase(),
      };

  Future<void> _recoverLiveWalReceipts(int generation) async {
    LiveWalReplay replay;
    try {
      final documents = await getApplicationDocumentsDirectory();
      if (!await LiveWalReceipt.directory(documents).exists() || !_isCurrent(generation)) return;
      replay = await LiveWalReceipt.recover(documents,
          knownBasenames: _liveWalReservedNames(), deletedOwners: (await readDeletedAccountUids()).toSet());
    } catch (_) {
      _emitLiveWalReceipt(WalWriteReceiptResult.scanUnavailable);
      return;
    }
    if (!_isCurrent(generation)) return;
    for (final entry in replay.withheld.entries) {
      final result = switch (entry.key) {
        LiveWalWithheld.invalid => WalWriteReceiptResult.invalid,
        LiveWalWithheld.deletedOwner => WalWriteReceiptResult.deletedOwner,
        LiveWalWithheld.missingAudio => WalWriteReceiptResult.missingAudio,
        LiveWalWithheld.contentMismatch => WalWriteReceiptResult.contentMismatch,
      };
      _emitLiveWalReceipt(result, withheld: entry.value);
    }
    if (replay.budgetExhausted) _emitLiveWalReceipt(WalWriteReceiptResult.budgetExhausted);

    // A flush may have published a receipt or finished writing its file
    // during the scan. Give that producer sole ownership of its transaction.
    final reserved = _liveWalReservedNames();
    final staged = <({Wal wal, List<Wal> bucket})>[];
    for (final wal in replay.rows) {
      if (!reserved.add(wal.filePath!.toLowerCase())) continue;
      final bucket = _walAdmittedAtLoad(wal) ? _wals : _foreignWals;
      bucket.add(wal);
      staged.add((wal: wal, bucket: bucket));
    }
    if (staged.isEmpty) return;
    try {
      if (await _saveWalsToFile(generation)) {
        _emitLiveWalReceipt(WalWriteReceiptResult.replay, recovered: staged.length);
        if (_isCurrent(generation) && staged.any((entry) => identical(entry.bucket, _wals))) heldRevision.value++;
        return;
      }
    } catch (_) {
      // Preserve receipts and bytes if we cannot commit ownership.
    }
    if (_isCurrent(generation)) {
      for (final entry in staged) {
        entry.bucket.remove(entry.wal);
      }
    }
    _emitLiveWalReceipt(WalWriteReceiptResult.indexUnavailable, withheld: staged.length);
  }

  void _emitLiveWalReceipt(WalWriteReceiptResult result, {int recovered = 0, int withheld = 0}) {
    try {
      const TypedEvents().emit(WalWriteReceipt(result: result, recovered: recovered, withheld: withheld));
    } catch (_) {/* Diagnostics never affect custody. */}
  }
}
