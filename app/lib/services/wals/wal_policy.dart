part of 'local_wal_sync.dart';

/// Error string the backend's stale guard sets when a job sits queued past
/// STALE_THRESHOLD_SECONDS without ever reaching a worker. See backend issue
/// #7469 — if this string changes, update here and keep the structural check
/// below ('failed' with totalSegments==0) as the durable signal.

/// Phone-local safety copies include 10-second pendant chunks. The 720-file
/// threshold spans every account bucket and represents about two hours when
/// every pendant chunk remains unacknowledged. It is a warning only: pending
/// copies are never evicted and new audio is never refused for count — on
/// legacy firmware the pendant has already freed it. Only the free-disk
/// reserve ([minFreeDiskReserveBytes]) refuses admission.
const int maxRetainedCaptureWalCount = 720;

const int minFreeDiskReserveBytes = 512 * 1024 * 1024;

extension _PendantBufferPolicy on LocalWalSyncImpl {
  int _countPendantBuffered() {
    var count = _frames.where(_isPendantFrame).length;
    for (final wal in _wals) {
      if (wal.storage == WalStorage.mem && _isPendantWal(wal)) {
        count += wal.totalFrames;
      }
    }
    return count;
  }
}

class WalRetentionRisk {
  const WalRetentionRisk({
    required this.engagedAt,
    required this.retainedCount,
    required this.blockedCount,
    required this.reason,
  });

  final DateTime engagedAt;
  final int retainedCount;

  final int blockedCount;

  final String reason;
}

/// The capture manifest is immutable per conversation, so claiming one for a
/// partial batch strands the siblings that did not fit.
@visibleForTesting
bool canClaimLiveCapture(List<Wal> batch, List<Wal> pendingForConversation, int nowSeconds) =>
    batch.isNotEmpty &&
    batch.first.conversationId != null &&
    isLiveCaptureWal(batch.first, nowSeconds) &&
    pendingForConversation.length <= batch.length;

/// A recording the automatic drain may still upload.
///
/// Spending [walMaxAutoRetries] takes it out of the current auto loop. A later
/// connectivity restoration re-arms transient disk WALs, while an unclassified
/// failure still stops within one connectivity epoch rather than re-uploading
/// the same bytes forever. The per-recording manual Retry
/// ([LocalWalSyncImpl.syncWal]) deliberately ignores this budget.
@visibleForTesting
bool isAutoUploadEligible(Wal wal) =>
    !wal.onDeviceOnly &&
    !wal.holdForUser &&
    wal.status == WalStatus.miss &&
    wal.storage == WalStorage.disk &&
    wal.retryCount < walMaxAutoRetries;

/// Pause tolerance for saved utterance gaps and WAL edges; coverage only suppresses automatic
/// repair, never deletes audio, so short gaps are treated as pauses while the copy stays recoverable.
const walTranscriptPauseToleranceSeconds = 30;

/// Whether the saved transcript covers [wal]: [transcriptSpans] share its absolute epoch clock,
/// must reach both edges within [walTranscriptPauseToleranceSeconds], have no longer interior
/// hole, and include at least one actually overlapping span.
@visibleForTesting
bool walCoveredByTranscript(Wal wal, List<(int, int)> transcriptSpans, int conversationStartSeconds) {
  final framesPerSecond = wal.codec.getFramesPerSecond();
  if (wal.seconds <= 0 ||
      (wal.totalFrames > 0 &&
          (framesPerSecond <= 0 ||
              wal.totalFrames % framesPerSecond != 0 ||
              wal.totalFrames ~/ framesPerSecond != wal.seconds))) {
    return false;
  }
  final start = wal.timerStart, end = wal.timerStart + wal.seconds;
  final spans = transcriptSpans.where((span) => span.$2 > span.$1).toList()..sort((a, b) => a.$1.compareTo(b.$1));
  final first = spans.indexWhere((span) => span.$2 > start); // first span that can touch the WAL
  if (first < 0 || spans[first].$1 >= end) return false; // nothing actually overlaps it
  var unionStart = spans[first].$1, unionEnd = spans[first].$2;
  for (final span in spans.skip(first + 1)) {
    if (unionEnd >= end || span.$1 >= end) break; // coverage finished, or no later span can touch the WAL
    if (span.$1 > unionEnd + walTranscriptPauseToleranceSeconds) return false; // an interior hole longer than a pause
    unionEnd = max(unionEnd, span.$2);
  }
  return unionStart <= start + walTranscriptPauseToleranceSeconds &&
      unionEnd >= end - walTranscriptPauseToleranceSeconds;
}

/// Where a saved transcript starts on the phone's clock, from when its live segments last arrived:
/// each arrives a moment after the segment's end, so arrival minus end is that start plus the
/// transcription delay. The median ignores stray matches; non-finite ends and non-positive arrivals
/// are skipped, and null means no usable live arrival.
int? transcriptStartOnDevice(Iterable<(String, double)> segmentEnds, Map<String, int> lastArrivals) {
  final estimates = [
    for (final (id, end) in segmentEnds)
      if (end.isFinite)
        if (lastArrivals[id] case final arrived? when arrived > 0) arrived - end.ceil(),
  ]..sort();
  return estimates.isEmpty ? null : estimates[estimates.length ~/ 2];
}

const _kDefinitiveUploadRefusalStatusCodes = {400, 413};

/// The longest pause that may separate two chunks of one source recording and
/// still let the earlier chunk's end name when the later one began: the same
/// conversation-pause tolerance the backend and [recordingBlockGapSeconds]
/// use. A wider gap is a silence the recording does not prove continuity
/// across, so no capture time may be derived from it.
const int invalidCaptureTimeNeighbourGapSeconds = 120;

/// Whether [wal] carries the source's own frame coordinates, the strongest
/// proof two chunks recorded one continuous run of audio.
bool _hasSourceFramePosition(Wal wal) =>
    wal.captureRoot != null && wal.sourceClockEpoch != null && wal.sourceFrameStart != null;

/// Whether [other] records the audio immediately before [wal] on the source's
/// own clock: same capture root and frame-clock epoch, ending exactly where
/// [wal] begins in frame positions. Frame adjacency survives any wall-clock
/// error in the filenames — the very error being repaired.
bool _isFrameAdjacentPredecessor(Wal wal, Wal other) =>
    _hasSourceFramePosition(wal) &&
    other.captureRoot == wal.captureRoot &&
    other.sourceClockEpoch == wal.sourceClockEpoch &&
    other.sourceFrameStart != null &&
    wal.sourceFrameStart != null &&
    other.sourceFrameStart! + other.totalFrames == wal.sourceFrameStart;

/// A capture time proven by contiguous audio: the wall-clock end of the
/// neighbour that recorded the audio immediately before [wal] in the same
/// source run — proven by exact frame adjacency on the source's own clock, or
/// by a shared clock run or recording session with the neighbour's end within
/// [invalidCaptureTimeNeighbourGapSeconds] of this WAL's claimed start, i.e.
/// of its position in the run's own clock. The neighbour is picked by that
/// recording position, never by the latest plausible end anywhere on the
/// device, and its end must itself be a time the server accepts.
///
/// Null when no such neighbour exists. Then no date may be invented — not
/// from the file's timestamp (mtime is the copy time, not the capture time)
/// and not from the plausibility floor — and the row stays on attention with
/// the user's Delete and a Retry that resends unchanged.
@visibleForTesting
int? contiguousCaptureStartSeconds(
  Wal wal,
  Iterable<Wal> candidates,
  int nowSeconds, {
  int gapSeconds = invalidCaptureTimeNeighbourGapSeconds,
}) {
  Wal? framePredecessor;
  Wal? runPredecessor;
  for (final other in candidates) {
    if (identical(other, wal) || other.device != wal.device) continue;
    if (_isFrameAdjacentPredecessor(wal, other)) framePredecessor = other;
    if (other.seconds <= 0 || !walTimerStartPlausible(other.timerStart)) continue;
    final end = other.timerStart + other.seconds;
    // The neighbour's end must be a time the server itself accepts — a
    // neighbour on the same wrong clock cannot name this chunk's real time.
    if (end < walMinPlausibleTimerStartSeconds || end > nowSeconds) continue;
    if (_sharesSourceRun(wal, other)) {
      // Within the run's own clock the predecessor ends where this chunk
      // begins, at most a pause apart; anything wider proves nothing.
      final gap = wal.timerStart - end;
      if (gap >= 0 &&
          gap <= gapSeconds &&
          (runPredecessor == null || end > runPredecessor.timerStart + runPredecessor.seconds)) {
        runPredecessor = other;
      }
    }
  }
  final byFrames = framePredecessor;
  if (byFrames != null && byFrames.seconds > 0 && walTimerStartPlausible(byFrames.timerStart)) {
    final end = (byFrames.timerStart + walAudioSeconds(byFrames)).round();
    if (end >= walMinPlausibleTimerStartSeconds && end <= nowSeconds) return end;
  }
  final byRun = runPredecessor;
  return byRun == null ? null : byRun.timerStart + byRun.seconds;
}

/// Whether [other] shares this WAL's source-run identity: its clock run
/// (chunks of one estimated recording) or its recording session (chunks of
/// one live capture). Same device alone proves nothing — every recording on
/// the pendant shares that.
bool _sharesSourceRun(Wal wal, Wal other) {
  final run = wal.clockRun;
  if (run != null && other.clockRun == run) return true;
  final session = wal.recordingSessionId;
  return session != null && other.recordingSessionId == session;
}

/// Pause before the next batch after [streak] consecutive unscoped 5xx
/// refusals. Exponential from 2s, capped at 30s: long enough that a shedding
/// or restarting backend gets breathing room within a drain, short enough that
/// a healthy drain's total added latency stays bounded (~1min worst case).
@visibleForTesting
int syncServerUnavailablePauseSeconds(int streak) {
  if (streak <= 0) return 0;
  return min(30, 2 * (1 << min(streak - 1, 4)));
}

@visibleForTesting
bool isDefinitiveUploadRefusal(Object error) =>
    error is SyncUploadHttpException && _kDefinitiveUploadRefusalStatusCodes.contains(error.statusCode);

typedef WalCoverageTelemetryEmitter = void Function(Map<String, Object?> fields);

/// The bounded refusal token for a terminal upload HTTP status.
String uploadRejectionTokenForStatus(int statusCode) =>
    statusCode == 413 ? WalUploadRejection.tooLarge : WalUploadRejection.serverRefused;

/// Repairs an `invalid_capture_time` refusal on a single recording, in the
/// server's own terms: audio is never deleted for its claimed time, however
/// short — a fragment that has no proven contiguous neighbour stays as an
/// attention row with the user's Delete. When a neighbour proves when the
/// recording began, the file is re-stamped with that time and requeued once;
/// a second refusal of the same recording is terminal with the reason kept.
extension InvalidCaptureTimeRepair on LocalWalSyncImpl {
  /// A request-level refusal proves nothing about every member: isolate the
  /// batch so the next attempt names the actual file, exactly like a
  /// definitive 400/413. A single-file refusal gets that file's repair.
  Future<void> handleBatchInvalidCaptureTime(
    List<Wal> batchWals,
    int generation,
    SyncInvalidCaptureTimeException e, {
    required Set<String> isolateAfterRefusal,
    required Set<String> attemptedWalIds,
    required String Function(Wal wal) walAttemptKey,
  }) async {
    if (batchWals.length > 1) {
      await isolateBatchAfterRefusal(
        batchWals,
        generation,
        isolateAfterRefusal: isolateAfterRefusal,
        attemptedWalIds: attemptedWalIds,
        walAttemptKey: walAttemptKey,
        reason: 'invalid_capture_time',
      );
      return;
    }
    await applyInvalidCaptureTimeRefusal(batchWals, generation, e);
    await _saveWalsToFile(generation);
    _notifyUpdated(generation);
  }

  /// The single-recording retry path's share of the same repair.
  Future<void> handleSingleInvalidCaptureTime(
    Wal wal,
    int generation,
    SyncInvalidCaptureTimeException e,
  ) async {
    wal.isSyncing = false;
    wal.syncStartedAt = null;
    wal.syncEtaSeconds = null;
    await applyInvalidCaptureTimeRefusal([wal], generation, e);
    await _saveWalsToFile(generation);
    _notifyUpdated(generation);
  }

  /// Re-queues every member of a refused batch for its own single-file
  /// attempt: clears the in-flight flags, pulls the batch's attempt keys, and
  /// records the isolation. Shared by the definitive 400/413 handler and the
  /// invalid-capture-time handler, whose refusals are equally unattributed at
  /// the request level.
  Future<void> isolateBatchAfterRefusal(
    List<Wal> batchWals,
    int generation, {
    required Set<String> isolateAfterRefusal,
    required Set<String> attemptedWalIds,
    required String Function(Wal wal) walAttemptKey,
    int statusCode = 400,
    String reason = '',
  }) async {
    for (final wal in batchWals) {
      final key = walAttemptKey(wal);
      isolateAfterRefusal.add(key);
      attemptedWalIds.remove(key);
      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
    }
    DebugLogManager.logEvent('local_upload_batch_isolated', {
      'statusCode': statusCode,
      'walCount': batchWals.length,
      if (reason.isNotEmpty) 'reason': reason,
    });
    await _saveWalsToFile(generation);
    _notifyUpdated(generation);
  }

  Future<void> applyInvalidCaptureTimeRefusal(
    List<Wal> wals,
    int generation,
    SyncInvalidCaptureTimeException e,
  ) async {
    for (final wal in wals) {
      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
      if (wal.captureTimeRestamped || !await _restampInvalidCaptureTimeWal(wal, generation)) {
        wal.markUploadRejected(reasonCode: WalUploadRejection.invalidCaptureTime);
        DebugLogManager.logEvent('invalid_capture_time_terminal', {
          'walId': wal.id,
          'reason': e.serverReason ?? '',
          'restamped': wal.captureTimeRestamped,
        });
      }
    }
  }

  /// Rewrites [wal]'s capture time to the time proven by its contiguous
  /// neighbour and moves its file to the matching name, leaving it `miss` so
  /// the queue re-offers it once. Returns false (untouched) when no neighbour
  /// proves a time or the file cannot be moved.
  Future<bool> _restampInvalidCaptureTimeWal(Wal wal, int generation) async {
    if (wal.filePath == null || wal.filePath!.isEmpty) return false;
    final fullPath = await Wal.getFilePath(wal.filePath);
    if (fullPath == null) return false;
    final nowSeconds = _now().millisecondsSinceEpoch ~/ 1000;
    final estimate = contiguousCaptureStartSeconds(wal, _wals, nowSeconds);
    if (estimate == null) return false;
    try {
      // An estimated time carries a clock run so the backend never merges the
      // fragment with audio outside its run by invented adjacency.
      final clockRun = wal.clockRun ?? Wal.newClockRun();
      // Two fragments of one run can chain to the same neighbour-end estimate;
      // rename would silently replace, so step the seconds apart instead.
      var start = estimate;
      final directory = File(fullPath).parent;
      while (await File('${directory.path}/${wal.getFileNameByTimeStarts(start, clockRun: clockRun)}').exists()) {
        start++;
      }
      final newName = wal.getFileNameByTimeStarts(start, clockRun: clockRun);
      // Crash-safe move: copy to the new name first, durably save the index
      // that points there, and only then remove the old file. A crash at any
      // step leaves the audio reachable under a name the index can still name
      // — the old one until the save lands, the copy after it.
      final copied = await File(fullPath).copy('${directory.path}/$newName');
      final oldFilePath = wal.filePath;
      final oldTimerStart = wal.timerStart;
      final oldClockRun = wal.clockRun;
      wal
        ..filePath = copied.path.split('/').last
        ..timerStart = start
        ..clockRun = clockRun
        ..uploadRejectionReason = null
        ..captureTimeRestamped = true;
      try {
        if (!await _saveWalsToFile(generation)) {
          // A stale generation means this session never wrote: no durable index
          // can point at the copy, so it is removed again.
          _rollbackRestamp(wal, oldFilePath, oldTimerStart, oldClockRun);
          await copied.delete().catchError((_) => copied);
          return false;
        }
      } catch (err) {
        // The index write failed or was interrupted: whether its bytes landed
        // is unknown, so the copy is kept (deleting it could unlink the last
        // name the durable index points at) and the in-memory row returns to
        // the old name, which a later save re-persists.
        _rollbackRestamp(wal, oldFilePath, oldTimerStart, oldClockRun);
        Logger.debug('Invalid capture time restamp index save failed for ${wal.id}: $err');
        return false;
      }
      try {
        await File(fullPath).delete();
      } catch (err) {
        // The index points at the copy; the old name is only an orphan.
        Logger.debug('Invalid capture time restamp left the old file for ${wal.id}: $err');
      }
      DebugLogManager.logEvent('invalid_capture_time_restamped', {
        'walId': wal.id,
        'newTimerStart': start,
      });
      return true;
    } catch (err) {
      Logger.debug('Invalid capture time restamp failed for ${wal.id}: $err');
      return false;
    }
  }

  void _rollbackRestamp(Wal wal, String? oldFilePath, int oldTimerStart, String? oldClockRun) {
    wal
      ..filePath = oldFilePath
      ..timerStart = oldTimerStart
      ..clockRun = oldClockRun
      ..uploadRejectionReason = null
      ..captureTimeRestamped = false;
  }
}

/// Lookup/proof helpers shared by native custody producers.
extension NativeCustodyInventory on LocalWalSyncImpl {
  Wal? nativeWalForFileName(String name) {
    for (final wal in [..._wals, ..._foreignWals, ..._retiredWals]) {
      if (wal.filePath == name) return wal;
    }
    return null;
  }

  Future<bool> nativeWalIsDurable(Wal wal, int generation) async =>
      _isCurrent(generation) && _confirmedDurableWalKeys.contains(_durableKey(wal));
}

/// The owner stamp for records created in this session: the signed-in uid,
/// or a fixed marker when there is none (anonymous/pre-auth capture).
String _currentWalOwnerUid() {
  final uid = SharedPreferencesUtil().uid;
  return uid.isEmpty ? 'legacy' : uid;
}

/// Only acknowledged jobs publish Home updates, after the ledger save succeeds.
extension _WalConversationCompletion on LocalWalSyncImpl {
  void _publishConversationCompletions(List<SyncLocalFilesResponse> completed, int generation) {
    if (!_isCurrent(generation) || completed.isEmpty) return;
    final newIds = {for (final result in completed) ...result.newConversationIds};
    final updatedIds = {for (final result in completed) ...result.updatedConversationIds}..removeAll(newIds);
    if (newIds.isEmpty && updatedIds.isEmpty) return;
    conversationCompletions.value =
        SyncLocalFilesResponse(newConversationIds: newIds.toList(), updatedConversationIds: updatedIds.toList());
  }
}

/// Transport sends alone are not a server custody guarantee.
bool watchWalWillReachServer(Wal wal) =>
    (wal.conversationId?.isNotEmpty ?? false) ||
    wal.syncedAt > 0 ||
    (wal.status == WalStatus.miss && !wal.holdForUser && !wal.onDeviceOnly);

extension WatchCustodyJournal on LocalWalSyncImpl {
  Future<void> refreshWatchCoverage(WatchLiveCoverage coverage) async {
    final generation = _sessionGeneration;
    final records = <(String, double, double, bool)>[];
    for (final wal in List<Wal>.of(_wals)) {
      if (wal.deviceType != DeviceType.appleWatch ||
          wal.ownerUid == null ||
          !await nativeWalIsDurable(wal, generation)) {
        continue;
      }
      records.add((
        wal.ownerUid!,
        wal.timerStart.toDouble(),
        wal.timerStart + wal.totalFrames * wal.frameSize / wal.sampleRate,
        watchWalWillReachServer(wal)
      ));
    }
    if (_isCurrent(generation)) await coverage.recordMany(records);
  }

  void _observeNativeUpload(Iterable<Wal> wals) {
    for (final wal in wals) {
      if (wal.device.startsWith('omibatchwatch')) nativeCustodyObserved(NativeCustodyObservedOutcome.watchUploaded);
    }
  }
}
