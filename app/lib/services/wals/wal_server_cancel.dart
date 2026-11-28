part of 'local_wal_sync.dart';

/// Deleting an uploaded recording that the server has not transcribed also cancels and erases its
/// server job (`cancelSyncJob`, the owner-cancel endpoint).
///
/// The job id is written to a durable tombstone before the local file goes, so an offline phone, a
/// 409 (the job is being processed right now) or a server error retries from the tombstone on
/// later reconcile passes until the server answers for good. A cancelled recording cannot be
/// re-uploaded: its file and row are gone. Recordings that shared the upload but were not deleted
/// keep waiting on the job while the cancel is unanswered (their job is not polled), and return
/// to local custody to re-upload on their own only once the server confirms nothing will be
/// transcribed. If the job was already processed they are acknowledged by the normal poll.
const walServerCancelTombstonesKey = 'walServerCancelTombstones';
const _serverCancelsPerPass = 5;
const _serverCancelRetryDelays = [Duration(minutes: 5), Duration(minutes: 30), Duration(hours: 6)];

class WalServerCancelTombstone {
  final String jobId;
  final String? ownerUid;
  final Set<String> targetWalIds;
  final int createdAt;
  final int attempts;
  final int nextAttemptAt;

  /// The server confirmed nothing will transcribe; only erasure is unfinished.
  final bool fenced;

  const WalServerCancelTombstone({
    required this.jobId,
    required this.ownerUid,
    required this.createdAt,
    this.targetWalIds = const {},
    this.attempts = 0,
    this.nextAttemptAt = 0,
    this.fenced = false,
  });

  WalServerCancelTombstone retried(int nowSecs, {required bool fenced}) {
    final delay = _serverCancelRetryDelays[min(attempts, _serverCancelRetryDelays.length - 1)];
    return WalServerCancelTombstone(
      jobId: jobId,
      ownerUid: ownerUid,
      createdAt: createdAt,
      targetWalIds: targetWalIds,
      attempts: attempts + 1,
      nextAttemptAt: nowSecs + delay.inSeconds,
      fenced: fenced || this.fenced,
    );
  }

  Map<String, Object?> toJson() => {
        'job_id': jobId,
        'owner_uid': ownerUid,
        'created_at': createdAt,
        'target_wal_ids': targetWalIds.toList(),
        'attempts': attempts,
        'next_attempt_at': nextAttemptAt,
        'fenced': fenced,
      };

  static WalServerCancelTombstone? fromJson(Object? value) {
    if (value is! Map) return null;
    final jobId = value['job_id'];
    if (jobId is! String || jobId.isEmpty) return null;
    final owner = value['owner_uid'];
    final targets = value['target_wal_ids'];
    int number(Object? v) => v is int ? v : 0;
    return WalServerCancelTombstone(
      jobId: jobId,
      ownerUid: owner is String ? owner : null,
      createdAt: number(value['created_at']),
      targetWalIds: targets is List ? targets.whereType<String>().toSet() : const {},
      attempts: number(value['attempts']),
      nextAttemptAt: number(value['next_attempt_at']),
      fenced: value['fenced'] == true,
    );
  }
}

abstract class WalServerCancelStore {
  Future<List<WalServerCancelTombstone>> load();

  /// False when the write did not persist; a delete must then keep its local copy.
  Future<bool> save(List<WalServerCancelTombstone> tombstones);
}

class PreferencesWalServerCancelStore implements WalServerCancelStore {
  @override
  Future<List<WalServerCancelTombstone>> load() async {
    try {
      final rows = (await SharedPreferences.getInstance()).getStringList(walServerCancelTombstonesKey) ?? const [];
      return [
        for (final row in rows)
          if (_decode(row) case final tombstone?) tombstone,
      ];
    } catch (_) {
      return const [];
    }
  }

  static WalServerCancelTombstone? _decode(String row) {
    try {
      return WalServerCancelTombstone.fromJson(jsonDecode(row));
    } catch (_) {
      return null;
    }
  }

  @override
  Future<bool> save(List<WalServerCancelTombstone> tombstones) async {
    try {
      return await (await SharedPreferences.getInstance())
          .setStringList(walServerCancelTombstonesKey, [for (final t in tombstones) jsonEncode(t.toJson())]);
    } catch (_) {
      return false;
    }
  }
}

class _ServerCancelPass {
  final Set<String> pending;
  final Map<String, SyncJobCancelResult> answered;
  const _ServerCancelPass(this.pending, this.answered);
}

extension _WalServerCancel on LocalWalSyncImpl {
  /// One tombstone operation at a time. An idle lock runs [body] directly: chaining onto an already
  /// completed future would schedule on the zone that created it, which a test's fake clock may
  /// never drain.
  Future<T> _serverCancelLocked<T>(Future<T> Function() body) async {
    while (_serverCancelBusy != null) {
      await _serverCancelBusy!.future;
    }
    final busy = _serverCancelBusy = Completer<void>();
    try {
      return await body();
    } finally {
      _serverCancelBusy = null;
      busy.complete();
    }
  }

  /// Keep the drain from sending a new tombstone while its local delete can still fail.
  Future<bool> _deleteWalWithServerCancel(Wal target, String jobId, int generation) => _serverCancelLocked(() async {
        if (!_isCurrent(generation) || !_isTrackedWal(target) || target.isSyncing) return false;
        final tombstones = await _serverCancelStore.load();
        final prior = tombstones.where((t) => t.jobId == jobId).firstOrNull;
        final targetWalIds = {...?prior?.targetWalIds, target.id};
        final ownerUid = target.ownerUid == 'legacy' ? _currentWalOwnerUid() : target.ownerUid;
        if (!await _serverCancelStore.save([
          ...tombstones.where((t) => t.jobId != jobId),
          WalServerCancelTombstone(
            jobId: jobId,
            ownerUid: prior?.ownerUid ?? ownerUid,
            createdAt: prior?.createdAt ?? _now().millisecondsSinceEpoch ~/ 1000,
            attempts: prior?.attempts ?? 0,
            nextAttemptAt: prior?.nextAttemptAt ?? 0,
            fenced: prior?.fenced ?? false,
            targetWalIds: targetWalIds,
          ),
        ])) {
          return false;
        }
        if (!await _deleteWal(target, generation: generation)) {
          if (prior == null) await _serverCancelStore.save(tombstones);
          return false;
        }
        await _saveWalsToFile(generation);
        return true;
      });

  /// Asks the server about due tombstones. [only] forces one job now (the delete that wrote it).
  Future<_ServerCancelPass> _drainServerCancels(int generation, {String? only}) => _serverCancelLocked(() async {
        final tombstones = await _serverCancelStore.load();
        await ServerCancelPause.instance.load();
        if (tombstones.isEmpty) return const _ServerCancelPass({}, {});
        final owner = _currentWalOwnerUid();
        final nowSecs = _now().millisecondsSinceEpoch ~/ 1000;
        final pending = <String>{};
        final answered = <String, SyncJobCancelResult>{};
        final kept = <WalServerCancelTombstone>[];
        var changed = false, asked = 0;
        for (final tombstone in tombstones) {
          final mine = tombstone.ownerUid == null || tombstone.ownerUid == owner || tombstone.ownerUid == 'legacy';
          final due = only == null ? tombstone.nextAttemptAt <= nowSecs : only == tombstone.jobId;
          if (!mine ||
              !due ||
              asked >= _serverCancelsPerPass ||
              SyncRateLimiter.instance.isLimited ||
              !_isCurrent(generation)) {
            kept.add(tombstone);
            pending.add(tombstone.jobId);
            continue;
          }
          asked++;
          final result = await (_serverCancelOverride ?? cancelSyncJob)(tombstone.jobId);
          answered[tombstone.jobId] = result;
          if (result.outcome == SyncJobCancelOutcome.paused) {
            await ServerCancelPause.instance.pause();
          } else if (result.serverAnswered) {
            await ServerCancelPause.instance.clear();
          }
          if (result.fenced && !tombstone.fenced) await _returnCancelledSiblings(tombstone, generation);
          final fenced = result.fenced || tombstone.fenced;
          var localDeletePending = false;
          if (fenced && _isCurrent(generation)) {
            final targets =
                _wals.where((wal) => wal.jobId == tombstone.jobId && tombstone.targetWalIds.contains(wal.id)).toList();
            var removed = false;
            for (final target in targets) {
              if (await _deleteWal(target, generation: generation)) {
                removed = true;
              } else {
                localDeletePending = true;
              }
            }
            if (removed) {
              await _saveWalsToFile(generation);
              _notifyUpdated(generation);
            }
          }
          if (result.settled && !localDeletePending && _isCurrent(generation)) {
            changed = true;
            continue;
          }
          kept.add(tombstone.retried(nowSecs, fenced: fenced));
          changed = true;
          if (!fenced || localDeletePending) pending.add(tombstone.jobId);
        }
        if (changed) await _serverCancelStore.save(kept);
        return _ServerCancelPass(pending, answered);
      });

  /// Recordings that shared the cancelled upload re-upload on their own; the server discarded them.
  Future<void> _returnCancelledSiblings(WalServerCancelTombstone tombstone, int generation) async {
    if (!_isCurrent(generation)) return;
    final jobId = tombstone.jobId;
    final nowSecs = _now().millisecondsSinceEpoch ~/ 1000;
    var changed = false;
    for (final wal in _wals) {
      if (wal.status != WalStatus.uploaded || wal.jobId != jobId || tombstone.targetWalIds.contains(wal.id)) continue;
      wal.status = WalStatus.miss;
      wal.jobId = null;
      wal.lastRetryAt = nowSecs;
      changed = true;
      DebugLogManager.logEvent('reconcile_revert', {'walId': wal.id, 'jobId': jobId, 'outcome': 'owner_cancelled'});
    }
    if (changed) {
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
    }
  }
}
