part of 'capture_controller.dart';

// Undo on Home's recording bar: the live teardown that keeps nothing, and the server delete of the
// discarded recording, persisted until the server accepts it.

/// Mutable state for [_CapturePhoneDiscard], in one controller field.
class _PhoneDiscardState {
  _PhoneDiscardState({required this.retryDelays, this.deleteOverride});

  /// When each retry of a server delete starts within one app run.
  final List<Duration> retryDelays;
  final Future<bool> Function(String conversationId)? deleteOverride;

  /// Server deletes running now.
  final Set<Future<void>> deletes = {};
}

/// Undo on Home's recording bar: stop the phone's live recording and keep nothing of it. There is
/// no Home row, nothing is processed, and no audio is left for offline sync. If speech already
/// reached the server, its in-progress copy is deleted once the socket has closed. Its id is the
/// recording id the phone sent as `client_conversation_id`; a discard in the first seconds comes
/// before any silence rollover could mint another.
///
/// The server delete is an obligation that outlives the app run: it is persisted before the first
/// attempt and cleared only when the server accepts it, so a phone that is offline or killed before
/// then deletes it on a later launch, before the stale in-progress sweep could finalize it.
extension _CapturePhoneDiscard on CaptureController {
  static const _pendingDeletesKey = 'captureDiscardedServerDeletes';
  static const _maxPendingDeletes = 20;
  static const _pendingDeleteMaxAge = Duration(days: 7);

  Future<bool> _discardPhoneRecording() async {
    final recordingId = activeRecordingId;
    final outcome = await _capture.dispatch(const PhoneDiscardRequested());
    outcome.throwIfFailed();
    if (outcome.result != true) return false;
    if (recordingId != null && recordingId.isNotEmpty) {
      final entry = _PendingDiscardDelete(uid: _preferences.uid, recordingId: recordingId, discardedAt: _now());
      await _savePendingDeletes([..._loadPendingDeletes(), entry]);
      _startDiscardDelete(entry);
    }
    return true;
  }

  /// Launch: retry the deletes an earlier run could not finish, for the account signed in now.
  Future<void> _resumeDiscardDeletes() async {
    final now = _now();
    final pending = _loadPendingDeletes();
    final fresh = pending.where((e) => now.difference(e.discardedAt) < _pendingDeleteMaxAge).toList();
    if (fresh.length != pending.length) await _savePendingDeletes(fresh);
    for (final entry in fresh) {
      if (entry.uid == _preferences.uid) _startDiscardDelete(entry);
    }
  }

  void _startDiscardDelete(_PendingDiscardDelete entry) {
    final deleting = _deleteDiscardedServerCopy(entry);
    _phoneDiscard.deletes.add(deleting);
    unawaited(deleting.whenComplete(() => _phoneDiscard.deletes.remove(deleting)));
  }

  /// The delete answers 204, and records the tombstone, whether or not a row was ever created, so
  /// only a transport or server failure retries. What this run cannot finish waits for the next.
  Future<void> _deleteDiscardedServerCopy(_PendingDiscardDelete entry) async {
    final delete = _phoneDiscard.deleteOverride ?? deleteConversationServer;
    final delays = _phoneDiscard.retryDelays;
    for (var attempt = 0;; attempt++) {
      var deleted = false;
      try {
        deleted = await delete(entry.recordingId);
      } catch (e) {
        Logger.debug('discardPhoneRecording: server delete failed: $e');
      }
      if (deleted) {
        await _savePendingDeletes(_loadPendingDeletes().where((e) => e.recordingId != entry.recordingId).toList());
      }
      if (deleted || attempt >= delays.length || lifetime.isClosed) {
        Logger.debug('discardPhoneRecording: server delete ${deleted ? 'done' : 'deferred'} after ${attempt + 1}');
        return;
      }
      await Future<void>.delayed(delays[attempt]);
      if (lifetime.isClosed) return;
    }
  }

  List<_PendingDiscardDelete> _loadPendingDeletes() =>
      _preferences.getStringList(_pendingDeletesKey).map(_PendingDiscardDelete.decode).nonNulls.toList();

  Future<void> _savePendingDeletes(List<_PendingDiscardDelete> entries) async {
    final kept = entries.length > _maxPendingDeletes ? entries.sublist(entries.length - _maxPendingDeletes) : entries;
    await _preferences.saveStringList(_pendingDeletesKey, kept.map((e) => e.encode()).toList());
  }

  /// [_stopPhoneLiveBody] without keeping anything. The buffered tail is not flushed to the WAL or
  /// the socket, this recording's WAL audio is dropped, and the in-memory transcript is cleared, so
  /// nothing on the phone can make it a conversation later.
  Future<bool> _discardPhoneLiveBody() async {
    final recordingId = activeRecordingId;
    await _setCaptureForegroundRequired(false);
    _phoneMicWalActive = false;
    // Invalidate before native/WAL teardown so in-flight work cannot publish.
    _rollCaptureSession('discarded');
    await _cleanupCurrentState(disableNativeBackground: true);
    _phoneMic.stop();
    updateRecordingState(RecordingState.stop);
    await _socket?.stop(reason: 'phone recording discarded');
    if (recordingId != null && recordingId.isNotEmpty) {
      await _wal.getSyncs().phone.discardRecording(recordingId);
    }
    _clearSessionLocation();
    _sessionTransportInterrupted = false;
    await _resetStateVariables();
    externalActions.onLiveFinalized(); // The live episode closes; the next counts from now.
    _recordingTelemetry.complete(reason: 'user_discarded');
    await _clearPhoneRestoreMarker();
    return true;
  }
}

/// One discarded recording whose server copy still has to be deleted, for the account that made it.
class _PendingDiscardDelete {
  const _PendingDiscardDelete({required this.uid, required this.recordingId, required this.discardedAt});

  final String uid;
  final String recordingId;
  final DateTime discardedAt;

  String encode() => jsonEncode({'uid': uid, 'id': recordingId, 'at': discardedAt.millisecondsSinceEpoch});

  static _PendingDiscardDelete? decode(String raw) {
    try {
      final json = jsonDecode(raw);
      if (json is! Map) return null;
      final (uid, id, at) = (json['uid'], json['id'], json['at']);
      if (uid is! String || id is! String || id.isEmpty || at is! int) return null;
      return _PendingDiscardDelete(uid: uid, recordingId: id, discardedAt: DateTime.fromMillisecondsSinceEpoch(at));
    } catch (_) {
      return null;
    }
  }
}
