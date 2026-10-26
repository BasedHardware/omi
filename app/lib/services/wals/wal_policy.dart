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

/// A fragment at or below this length is splice wreckage from a corrupted
/// clock split: there is no conversation in it worth recovering and no clock
/// to recover it with. An `invalid_capture_time` refusal discards it quietly
/// — no "Failed" row — instead of parking it as terminal work the user must
/// dismiss one by one. 1.5 s at the WAL's whole-second resolution.
const int invalidCaptureTimeQuietDiscardMaxSeconds = 1;

/// A plausible replacement capture time for a recording the server refused
/// for its claimed time: right after the latest plausible same-device
/// neighbour that is not in the future, else the file's own timestamp, clamped
/// into the window the server's filename gate accepts
/// ([walMinPlausibleTimerStartSeconds] .. now).
@visibleForTesting
int estimatedCaptureStartSeconds({
  required int nowSeconds,
  Iterable<(int, int)> neighbourSpans = const [],
  DateTime? fileTimestamp,
}) {
  var candidate = 0;
  for (final span in neighbourSpans) {
    // The latest neighbour end that does not put the fragment in the future:
    // the fragment most likely belongs right after the rest of its recording.
    if (span.$2 > candidate && span.$2 <= nowSeconds) candidate = span.$2;
  }
  if (candidate == 0 && fileTimestamp != null) {
    final fileSeconds = fileTimestamp.millisecondsSinceEpoch ~/ 1000;
    if (fileSeconds > 0) candidate = fileSeconds;
  }
  if (candidate < walMinPlausibleTimerStartSeconds) return walMinPlausibleTimerStartSeconds;
  if (candidate > nowSeconds) return nowSeconds;
  return candidate;
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
/// server's own terms: splice wreckage at or below the quiet-discard threshold
/// disappears without a row, anything longer is re-stamped with a plausible
/// estimated time (never in the future) and requeued once, and a second
/// refusal of the same recording is terminal with the reason kept.
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
      if (wal.seconds <= invalidCaptureTimeQuietDiscardMaxSeconds) {
        DebugLogManager.logEvent('invalid_capture_time_discarded', {
          'walId': wal.id,
          'seconds': wal.seconds,
        });
        await _deleteWal(wal, generation: generation);
        continue;
      }
      if (wal.captureTimeRestamped || !await _restampInvalidCaptureTimeWal(wal)) {
        wal.markUploadRejected(reasonCode: WalUploadRejection.invalidCaptureTime);
        DebugLogManager.logEvent('invalid_capture_time_terminal', {
          'walId': wal.id,
          'reason': e.serverReason ?? '',
          'restamped': wal.captureTimeRestamped,
        });
      }
    }
  }

  /// Rewrites [wal]'s capture time to a plausible estimate and renames its
  /// file to match, leaving it `miss` so the queue re-offers it once. The
  /// estimate lands right after the latest plausible same-device neighbour,
  /// else at the file's own timestamp, always inside the server's accepted
  /// window. Returns false (untouched) when the file cannot be renamed.
  Future<bool> _restampInvalidCaptureTimeWal(Wal wal) async {
    if (wal.filePath == null || wal.filePath!.isEmpty) return false;
    final fullPath = await Wal.getFilePath(wal.filePath);
    if (fullPath == null) return false;
    final oldId = wal.id;
    final nowSeconds = _now().millisecondsSinceEpoch ~/ 1000;
    DateTime? fileTimestamp;
    try {
      fileTimestamp = (await File(fullPath).stat()).modified;
    } catch (_) {}
    final estimate = estimatedCaptureStartSeconds(
      nowSeconds: nowSeconds,
      neighbourSpans: [
        for (final other in _wals)
          if (!identical(other, wal) &&
              other.device == wal.device &&
              other.seconds > 0 &&
              walTimerStartPlausible(other.timerStart))
            (other.timerStart, other.timerStart + other.seconds),
      ],
      fileTimestamp: fileTimestamp,
    );
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
      final renamed = await File(fullPath).rename('${directory.path}/$newName');
      wal.filePath = renamed.path.split('/').last;
      wal.timerStart = start;
      wal.clockRun = clockRun;
      wal.uploadRejectionReason = null;
      wal.captureTimeRestamped = true;
      DebugLogManager.logEvent('invalid_capture_time_restamped', {
        'walId': oldId,
        'newTimerStart': start,
      });
      return true;
    } catch (err) {
      Logger.debug('Invalid capture time restamp failed for $oldId: $err');
      return false;
    }
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
