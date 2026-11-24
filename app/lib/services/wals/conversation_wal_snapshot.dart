part of 'local_wal_sync.dart';

/// An exclusive conversation close admitted by one WAL ledger/account.
///
/// Callers can retain this token across asynchronous server responses, but
/// cannot replace its WAL identities or reuse it in another ledger session.
class ConversationWalSnapshot {
  final LocalWalSyncImpl _ledger;
  final int _generation;
  final String _ownerUid;
  final String? _recordingSessionId;
  final Object _reservation;
  final Map<Wal, String?> _walRecordings;

  ConversationWalSnapshot._(
    this._ledger,
    this._generation,
    this._ownerUid,
    this._recordingSessionId,
    this._reservation,
    this._walRecordings,
  );
}

extension _ConversationWalSnapshots on LocalWalSyncImpl {
  Future<ConversationWalSnapshot?> _finalizeAndSnapshotSession(int sessionStartSeconds, String? recordingSessionId) {
    final generation = _sessionGeneration;
    final owner = _currentWalOwnerUid();
    final normalizedRecording = recordingSessionId?.trim();
    final recording = normalizedRecording == null || normalizedRecording.isEmpty ? null : normalizedRecording;
    final through = _now().millisecondsSinceEpoch ~/ 1000;

    // Ingress appends outside the I/O queue. Seal and reserve now, including
    // when an earlier flush is blocked, rather than draining the next session
    // when our queue entry eventually runs.
    _sealCurrentSession(generation, notifyListeners: false);
    final reservation = Object();
    final recordings = Map<Wal, String?>.identity();
    for (final wal in _wals) {
      if (_conversationWalReservations[wal] != null || wal.ownerUid != owner || !_canStampConversationWal(wal)) {
        continue;
      }
      final walRecording = wal.recordingSessionId;
      if (walRecording != null && walRecording.isNotEmpty && walRecording != recording) continue;
      final matchesRecording = recording != null && walRecording == recording;
      final inWindow = wal.timerStart >= sessionStartSeconds && wal.timerStart <= through;
      if (!matchesRecording && !inWindow) continue;
      _conversationWalReservations[wal] = reservation;
      recordings[wal] = walRecording;
    }
    final snapshot = ConversationWalSnapshot._(this, generation, owner, recording, reservation, recordings);

    return _enqueueBuffer(() async {
      if (!_ownsConversationSnapshot(snapshot)) return null;
      await _flush(generation);
      if (!_ownsConversationSnapshot(snapshot)) return null;
      _notifyUpdated(generation);
      return snapshot;
    });
  }

  bool _ownsConversationSnapshot(ConversationWalSnapshot snapshot) =>
      identical(snapshot._ledger, this) &&
      _isCurrent(snapshot._generation) &&
      snapshot._ownerUid == _currentWalOwnerUid();

  bool _canStampConversationWal(Wal wal) =>
      wal.conversationId == null &&
      (wal.status == WalStatus.miss || (wal.status == WalStatus.synced && wal.syncedAt == 0));

  Future<void> _stampConversationSnapshot(ConversationWalSnapshot snapshot, String conversationId) {
    if (!_ownsConversationSnapshot(snapshot) || conversationId.isEmpty) return Future.value();
    return _enqueueBuffer(() async {
      if (!_ownsConversationSnapshot(snapshot)) return;
      var stamped = 0;
      for (final wal in _wals) {
        if (!snapshot._walRecordings.containsKey(wal) ||
            !identical(_conversationWalReservations[wal], snapshot._reservation) ||
            wal.ownerUid != snapshot._ownerUid ||
            wal.recordingSessionId != snapshot._walRecordings[wal] ||
            !_canStampConversationWal(wal)) {
          continue;
        }
        // A known recording identity remains authoritative even if an active
        // session rolls while the server is producing the conversation ID.
        final recording = wal.recordingSessionId;
        if (recording != null && recording.isNotEmpty && recording != snapshot._recordingSessionId) continue;
        wal.conversationId = conversationId;
        stamped++;
      }
      if (stamped == 0) return;
      if (await _saveWalsToFile(snapshot._generation) && _ownsConversationSnapshot(snapshot)) {
        try {
          await refreshWatchCoverage(watchCoverage);
        } catch (e) {
          Logger.debug('Watch journal promotion deferred: $e');
        }
      }
      Logger.debug('stampConversationSnapshot: stamped $stamped WALs with conversation $conversationId');
    });
  }
}
