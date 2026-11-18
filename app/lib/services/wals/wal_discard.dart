part of 'local_wal_sync.dart';

/// Recordings the reader discarded (Undo on Home's recording bar). The live frames still in memory,
/// when they belong to the recording, and every WAL tagged with it go, in memory or on disk, so
/// offline sync can never turn the recording into a conversation. A WAL that is uploading at the
/// time is never picked again: once its upload settles the next sync pass deletes it, and if the
/// upload landed first, the server-side delete of the recording covers it.
extension _WalDiscard on LocalWalSyncImpl {
  Future<int> _discardRecording(String recordingSessionId) {
    final generation = _sessionGeneration;
    return _enqueueBuffer(() async {
      if (!_isCurrent(generation) || recordingSessionId.isEmpty) return 0;
      if (_activeRecordingSessionId == recordingSessionId && _deviceId == 'phone-mic') {
        _frames = [];
        _frameSynced = [];
        _pendingPhoneOnly = false;
      }
      _discardedRecordingSessionIds.add(recordingSessionId);
      final removed = await _deleteDiscardedWals(generation);
      Logger.debug('discardRecording: removed $removed WALs of the discarded recording');
      return removed;
    });
  }

  bool _isDiscardedRecording(Wal wal) {
    final session = wal.recordingSessionId;
    return session != null && _discardedRecordingSessionIds.contains(session);
  }

  /// Deletes what a discard had to leave because it was uploading, once that upload has settled.
  Future<void> _dropDiscardedWals(int generation) async {
    if (_discardedRecordingSessionIds.isEmpty) return;
    await _enqueueBuffer(() => _deleteDiscardedWals(generation));
  }

  Future<int> _deleteDiscardedWals(int generation) async {
    if (!_isCurrent(generation)) return 0;
    var removed = 0;
    final uploading = <String>{};
    for (final wal in List<Wal>.of(_wals)) {
      if (!_isDiscardedRecording(wal)) continue;
      if (wal.isSyncing) {
        uploading.add(wal.recordingSessionId!);
        continue;
      }
      if (await _deleteWal(wal, generation: generation)) removed++;
    }
    // A recording with nothing left uploading needs no more watching.
    _discardedRecordingSessionIds.retainWhere(uploading.contains);
    if (removed > 0) await _saveWalsToFile(generation);
    _notifyUpdated(generation);
    return removed;
  }
}
