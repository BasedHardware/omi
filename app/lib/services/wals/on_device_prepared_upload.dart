part of 'local_wal_sync.dart';

extension PreparedSegmentCustody on LocalWalSyncImpl {
  Future<bool> rejectDisabledPreparedUpload(Wal wal, int generation) async {
    if (!_isCurrent(generation) || !_wals.contains(wal) || wal.onDevicePreparedUpload == null) return false;
    final prepared = wal.onDevicePreparedUpload;
    final status = wal.status;
    final reason = wal.onDeviceUploadFailure;
    wal.onDevicePreparedUpload = null;
    wal.onDeviceUploadFailure = 'continuation_disabled';
    wal.markUploadRejected();
    try {
      if (!await _saveWalsToFile(generation)) throw StateError('WAL owner changed');
    } catch (_) {
      wal.onDevicePreparedUpload = prepared;
      wal.status = status;
      wal.onDeviceUploadFailure = reason;
      rethrow;
    }
    _notifyUpdated(generation);
    return true;
  }

  /// The ledger owns the outbox, just as it owns the source audio. Freeze the
  /// exact transcript before any chunk can be acknowledged by the server.
  Future<bool> persistPreparedSegmentUpload(Wal wal, Map<String, dynamic> snapshot, int generation) async {
    if (!_isCurrent(generation) || !_wals.contains(wal) || !wal.onDeviceOnly) return false;
    final previous = wal.onDevicePreparedUpload;
    wal.onDevicePreparedUpload = snapshot;
    try {
      await _saveWalsToFile(generation);
    } catch (_) {
      wal.onDevicePreparedUpload = previous;
      rethrow;
    }
    return _isCurrent(generation);
  }
}
