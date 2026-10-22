part of 'local_wal_sync.dart';

extension PreparedSegmentCustody on LocalWalSyncImpl {
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
