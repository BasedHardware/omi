part of 'capture_controller.dart';

/// Retry configuration for discard requests persisted by older app versions.
class _PhoneDiscardState {
  _PhoneDiscardState({required this.retryDelays, this.deleteOverride});

  /// When each retry of a server delete starts within one app run.
  final List<Duration> retryDelays;
  final Future<bool> Function(String conversationId)? deleteOverride;
}

/// Completes phone recording discards persisted by older app versions.
extension _CapturePhoneDiscard on CaptureController {
  static const _pendingDeletesKey = 'captureDiscardedServerDeletes';
  static const _pendingDeleteMaxAge = Duration(days: 7);

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
    unawaited(_deleteDiscardedServerCopy(entry));
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

  Future<void> _savePendingDeletes(List<_PendingDiscardDelete> entries) =>
      _preferences.saveStringList(_pendingDeletesKey, entries.map((e) => e.encode()).toList());
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
