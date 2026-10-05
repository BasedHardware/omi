import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:disk_space_2/disk_space_2.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal_evidence_runs.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/wal_file_manager.dart';

/// Error string the backend's stale guard sets when a job sits queued past
/// STALE_THRESHOLD_SECONDS without ever reaching a worker. See backend issue
/// #7469 — if this string changes, update here and keep the structural check
/// below ('failed' with totalSegments==0) as the durable signal.
const _kBackendBusyErrorHint = 'background worker likely died';
const _liveCaptureMaxAgeSeconds = 6 * 60 * 60;

/// Phone-local safety copies include 10-second pendant chunks. The 720-file
/// threshold spans every account bucket and represents about two hours when
/// every pendant chunk remains unacknowledged. It is a warning only: pending
/// copies are never evicted and new audio is never refused for count — on
/// legacy firmware the pendant has already freed it. Only the free-disk
/// reserve ([minFreeDiskReserveBytes]) refuses admission.
const int maxRetainedCaptureWalCount = 720;

const int minFreeDiskReserveBytes = 512 * 1024 * 1024;

const _captureEvidenceV1DarkWrite = bool.fromEnvironment('CAPTURE_EVIDENCE_V1_DARK_WRITE');

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

enum SyncJobTerminalPolicy { wait, acknowledge, retry }

/// The shared WAL acknowledgement boundary for async sync jobs.
///
/// Only the backend's truthful `completed` state permits local audio to become
/// terminally synced. Partial and full failures deliberately take the retry
/// path so the retained WAL remains recoverable.
@visibleForTesting
SyncJobTerminalPolicy syncJobTerminalPolicy({required String status, required bool isTerminal}) {
  if (!isTerminal) return SyncJobTerminalPolicy.wait;
  return status == 'completed' ? SyncJobTerminalPolicy.acknowledge : SyncJobTerminalPolicy.retry;
}

/// Terminal `reason_code`s the backend only reaches because of the uploaded
/// audio itself. `sync_invalid_audio` is raised by `decode_files_to_wav` once
/// *nothing* in the batch decoded, and `stt_invalid_input` is the provider
/// refusing the decoded audio as invalid — re-sending identical bytes produces
/// the identical verdict. Keep in sync with `_SYNC_FAILURE_REASON_CODES` in
/// backend/utils/sync/pipeline.py.
const _kPermanentInputFailureReasonCodes = {'sync_invalid_audio', 'stt_invalid_input'};

/// Whether a terminal job failed for a reason no re-upload can change.
///
/// Only a whole-job `failed` qualifies: `partial_failure` proves some segments
/// landed, so the batch is not shown to be bad. A permanent verdict therefore
/// never strands a good sibling — the decoder drops unreadable files
/// individually and only fails the job when the batch has nothing left.
@visibleForTesting
bool syncJobFailureIsPermanent(SyncJobStatusResponse status) =>
    status.status == 'failed' && _kPermanentInputFailureReasonCodes.contains(status.reasonCode);

@visibleForTesting
bool syncJobIsBackendBusy(SyncJobStatusResponse status) {
  if ((status.error ?? '').contains(_kBackendBusyErrorHint)) return true;
  // Legacy stale-worker failures predate reason_code. New typed failures with
  // totalSegments=0 carry a reason and must consume retry budget normally.
  final reasonCode = status.reasonCode;
  return status.status == 'failed' && status.totalSegments == 0 && (reasonCode == null || reasonCode.isEmpty);
}

bool isLiveCaptureWal(Wal wal, int nowSeconds) => nowSeconds - wal.timerStart <= _liveCaptureMaxAgeSeconds;

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
    wal.status == WalStatus.miss && wal.storage == WalStorage.disk && wal.retryCount < walMaxAutoRetries;

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

const _kDefinitiveUploadRefusalStatusCodes = {400, 403, 413};

@visibleForTesting
bool isDefinitiveUploadRefusal(Object error) =>
    error is SyncUploadHttpException && _kDefinitiveUploadRefusalStatusCodes.contains(error.statusCode);

typedef WalCoverageTelemetryEmitter = void Function(Map<String, Object?> fields);

class LocalWalSyncImpl with WidgetsBindingObserver implements LocalWalSync {
  List<Wal> _wals = [];

  List<WalFrame> _frames = [];
  String? _captureEvidenceRoot;
  int _captureEvidenceGeneration = 0;
  int _nextSourceFramePosition = 0;
  int _sourceClockEpoch = 0;
  List<bool> _frameSynced = [];

  Timer? _chunkingTimer;
  Timer? _flushingTimer;
  Timer? _pendantTimer;

  Future<void> _bufferQueue = Future.value();

  Future<T> _enqueueBuffer<T>(Future<T> Function() op) {
    final prev = _bufferQueue;
    final completer = Completer<T>();
    _bufferQueue = prev.then((_) async {
      try {
        completer.complete(await op());
      } catch (e, st) {
        completer.completeError(e, st);
      }
    });
    return completer.future;
  }

  IWalSyncListener listener;

  int _framesPerSecond = 100;
  BleAudioCodec _codec = BleAudioCodec.opus;
  String? _deviceId;
  String? _deviceModel;
  Geolocation? _sessionGeolocation;
  int? _sessionGeolocationSetAt;
  String? _activeRecordingSessionId;
  String? _conversationStampRecordingId;

  void setActiveRecordingSessionId(String? recordingSessionId) {
    final trimmed = recordingSessionId?.trim();
    _activeRecordingSessionId = (trimmed == null || trimmed.isEmpty) ? null : trimmed;
  }

  /// Recording id captured before a flush. [stampConversationId] keeps its
  /// original signature so session spies do not have to learn a new argument.
  void prepareConversationStamp(String? recordingSessionId) {
    final trimmed = recordingSessionId?.trim();
    _conversationStampRecordingId = (trimmed == null || trimmed.isEmpty) ? null : trimmed;
  }

  bool _isCancelled = false;

  /// Session fence. Incremented on logout so in-flight chunk/flush/sync cannot
  /// publish retired-account WALs into the successor via [listener.onWalUpdated].
  int _sessionGeneration = 0;

  /// Durable inventory moved off the published list on logout. Saves write
  /// both this and [_wals] so disk is not wiped; [getAllWals] returns [_wals]
  /// only. Adopting the current generation is not a fix.
  final List<Wal> _retiredWals = [];

  /// Durable inventory parked at load: records whose [Wal.ownerUid] names a
  /// different account. They are excluded from [_wals] (never rendered, never
  /// uploaded) but included in every persist — the save rewrites the whole
  /// index from memory, so leaving them out would silently delete the other
  /// account's recordings from disk.
  final List<Wal> _foreignWals = [];

  WalRetentionRisk? _retentionRisk;

  WalRetentionRisk? get retentionRisk => _retentionRisk;

  bool _isCurrent(int generation) => generation == _sessionGeneration;

  /// The owner stamp for records created in this session: the signed-in uid,
  /// or a fixed marker when there is none (anonymous/pre-auth capture).
  String _currentWalOwnerUid() {
    final uid = SharedPreferencesUtil().uid;
    return uid.isEmpty ? 'legacy' : uid;
  }

  /// Load admission for a disk record: it belongs to this session when it
  /// predates owner stamping (null — pre-upgrade data), was marked shared
  /// ('legacy'), or was created by the current account.
  bool _walAdmittedAtLoad(Wal wal) {
    final owner = wal.ownerUid;
    return owner == null || owner == 'legacy' || owner == _currentWalOwnerUid();
  }

  /// Partitions a freshly-loaded disk index into current-session records and
  /// foreign-owner records. Foreign records are parked in [_foreignWals] so
  /// every later persist rewrites them back to disk untouched. Both call
  /// sites load the full disk index, so parking uses replace semantics.
  void _admitLoadedWals(List<Wal> loaded) {
    final admitted = <Wal>[];
    final foreign = <Wal>[];
    for (final wal in loaded) {
      if (_walAdmittedAtLoad(wal)) {
        admitted.add(wal);
      } else {
        foreign.add(wal);
      }
    }
    _wals = admitted;
    _foreignWals
      ..clear()
      ..addAll(foreign);
    _confirmedDurableWalKeys
      ..clear()
      ..addAll(loaded.where((w) => w.storage == WalStorage.disk).map(_durableKey));
  }

  void _notifyUpdated(int generation) {
    if (!_isCurrent(generation)) return;
    listener.onWalUpdated();
  }

  @override
  void clearUserData() {
    _sessionGeneration++;
    cancelSync();
    // Back-fill the owner on retiring records that predate stamping, while the
    // logout path still has the signing-out uid available (clearUserData runs
    // before prefs are cleared). Unstamped records otherwise fall through the
    // load filter as "shared" and would reappear in the next account.
    for (final wal in _wals) {
      wal.ownerUid ??= _currentWalOwnerUid();
    }
    _retiredWals.addAll(_wals);
    _wals = [];
    _frames = [];
    _frameSynced = [];
    _captureEvidenceRoot = null;
    _captureEvidenceGeneration++;
    _nextSourceFramePosition = 0;
    _sourceClockEpoch = 0;
    _admissionReservations.clear();
    _liveProofPendingWalIds.clear();
    _pendantBlockedByStorage = false;
  }

  /// Completes when _initializeWals() finishes loading WALs from disk.
  final Completer<void> _walReady = Completer<void>();

  /// Future that resolves when WALs are loaded and ready to query.
  Future<void> get walReady => _walReady.future;

  /// Accumulated conversation IDs from completed batches during an ongoing sync.
  /// Accessible so that cancel can retrieve partial results.
  SyncLocalFilesResponse? _accumulatedResponse;
  SyncLocalFilesResponse? get accumulatedResponse => _accumulatedResponse;

  final SyncUploadGate? _uploadGateOverride;
  SyncUploadGate get _uploadGate => _uploadGateOverride ?? SyncUploadGate.instance;

  // Deterministic-replay seams: null means production wall clock, dart:async
  // periodic timers, and the shared HTTP job-status endpoint.
  final DateTime Function()? _nowOverride;
  final Timer Function(Duration, void Function(Timer))? _periodicOverride;
  final Future<SyncJobFetch> Function(String jobId)? _jobStatusFetcherOverride;
  final Future<void> Function(List<Wal> wals)? _persistWalsOverride;
  final Future<List<Wal>> Function()? _loadWalsOverride;
  final WalCoverageTelemetryEmitter? _coverageTelemetryOverride;
  final Future<int?> Function()? _freeDiskBytesOverride;
  final PendantRingCustody _custody;
  final Future<DeviceConnection?> Function(String deviceId)? _connectionResolver;

  DateTime _now() => _nowOverride?.call() ?? DateTime.now();

  Timer Function(Duration, void Function(Timer)) get _periodic => _periodicOverride ?? Timer.periodic;

  Future<SyncJobFetch> Function(String jobId) get _jobStatusFetcher => _jobStatusFetcherOverride ?? fetchSyncJobStatus;

  LocalWalSyncImpl(
    this.listener, {
    SyncUploadGate? uploadGate,
    DateTime Function()? now,
    Timer Function(Duration, void Function(Timer))? periodic,
    Future<SyncJobFetch> Function(String jobId)? jobStatusFetcher,
    Future<void> Function(List<Wal> wals)? persistWals,
    Future<List<Wal>> Function()? loadWals,
    WalCoverageTelemetryEmitter? coverageTelemetry,
    Future<int?> Function()? freeDiskBytes,
    PendantRingCustody? custody,
    Future<DeviceConnection?> Function(String deviceId)? connectionResolver,
  })  : _uploadGateOverride = uploadGate,
        _nowOverride = now,
        _periodicOverride = periodic,
        _jobStatusFetcherOverride = jobStatusFetcher,
        _persistWalsOverride = persistWals,
        _loadWalsOverride = loadWals,
        _coverageTelemetryOverride = coverageTelemetry,
        _freeDiskBytesOverride = freeDiskBytes,
        _custody = custody ?? PendantRingCustody.shared,
        _connectionResolver = connectionResolver;

  @override
  int get sessionGeneration => _sessionGeneration;

  @override
  int get captureEvidenceGeneration => _captureEvidenceGeneration;

  @visibleForTesting
  List<WalFrame> get testFrames => _frames;

  @visibleForTesting
  List<bool> get testFrameSynced => _frameSynced;

  @visibleForTesting
  List<Wal> get testWals => _wals;

  @visibleForTesting
  set testWals(List<Wal> wals) => _wals = wals;

  @visibleForTesting
  List<Wal> get testForeignWals => _foreignWals;

  @visibleForTesting
  List<Wal> get testRetiredWals => _retiredWals;

  @override
  void cancelSync() {
    _isCancelled = true;
  }

  @override
  Future<void> addExternalWal(Wal wal, {required int admittedGeneration}) async {
    if (!_isCurrent(admittedGeneration)) return;
    // Cover all four external callers: any record admitted into this session
    // is owned by the signed-in account. Stamp only when unstamped so a
    // record surfaced by native recovery keeps its original owner.
    wal.ownerUid ??= _currentWalOwnerUid();
    // Native-storage recovery can surface old WALs while a new recording is
    // active. Only inherit the current session's location for WALs that began
    // at (or after) this session, never for historical recordings.
    if (wal.geolocation == null &&
        _sessionGeolocation != null &&
        _sessionGeolocationSetAt != null &&
        wal.timerStart >= _sessionGeolocationSetAt! - 60) {
      wal.geolocation = _copyGeolocation(_sessionGeolocation);
    }
    final existingIndex = _wals.indexWhere((w) => w.id == wal.id);
    if (existingIndex >= 0) {
      final existing = _wals[existingIndex];
      final sameRecord = existing.codec == wal.codec &&
          existing.timerStart == wal.timerStart &&
          existing.seconds == wal.seconds &&
          existing.totalFrames == wal.totalFrames;
      final sameFile = wal.filePath != null && existing.filePath == wal.filePath;
      if (sameRecord && sameFile && await _localFileExists(existing)) {
        Logger.debug("LocalWalSync: WAL ${wal.id} already exists, skipping");
        if (!_confirmedDurableWalKeys.contains(_durableKey(existing))) {
          await _saveWalsToFile(admittedGeneration);
        }
        return;
      }
      Logger.debug("LocalWalSync: WAL id collision on ${wal.id}; admitting both on distinct file paths");
    }
    if (!_isCurrent(admittedGeneration)) return;
    _wals.add(wal);
    final reservedBytes = await _walFileLength(wal);
    if (reservedBytes != null) _consumeAdmission(reservedBytes);
    await _evaluateRetentionPressure();
    await _saveWalsToFile(admittedGeneration);
    _notifyUpdated(admittedGeneration);
    Logger.debug("LocalWalSync: Added external WAL ${wal.id} (${wal.seconds}s)");
  }

  @override
  void start() {
    _initializeWals();
    _chunkingTimer = _periodic(const Duration(seconds: chunkSizeInSeconds + newFrameSyncDelaySeconds), (t) async {
      final generation = _sessionGeneration;
      await _enqueueBuffer(() => _chunk(generation));
    });
    _flushingTimer = _periodic(const Duration(seconds: flushIntervalInSeconds + newFrameSyncDelaySeconds), (t) async {
      final generation = _sessionGeneration;
      await _enqueueBuffer(() => _flush(generation));
    });
    _pendantTimer = _periodic(const Duration(seconds: 10), (t) async {
      final generation = _sessionGeneration;
      await _drainPendantTail(generation);
    });
    try {
      WidgetsBinding.instance.addObserver(this);
    } catch (_) {}
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive ||
        state == AppLifecycleState.detached) {
      final generation = _sessionGeneration;
      unawaited(
        _drainPendantTail(generation).catchError((e) {
          Logger.debug('LocalWalSync: lifecycle pendant drain failed: $e');
        }),
      );
    }
  }

  Future<void> _initializeWals() async {
    final generation = _sessionGeneration;
    await WalFileManager.init();
    if (!_isCurrent(generation)) {
      if (!_walReady.isCompleted) _walReady.complete();
      return;
    }
    final loaded = _loadWalsOverride != null ? await _loadWalsOverride!() : await WalFileManager.loadWals();
    if (!_isCurrent(generation)) {
      if (!_walReady.isCompleted) _walReady.complete();
      return;
    }
    _admitLoadedWals(loaded);
    Logger.debug("wal service start: ${_wals.length}");

    final missingCount = _wals.where((w) => w.status == WalStatus.miss).length;
    final syncedCount = _wals.where((w) => w.status == WalStatus.synced).length;
    DebugLogManager.logEvent('wal_initialized', {
      'totalWals': _wals.length,
      'missing': missingCount,
      'synced': syncedCount,
    });

    // Run migrations for legacy Limitless files
    final migratedCount = await WalFileManager.migrateLegacyLimitlessFiles(_wals);
    if (!_isCurrent(generation)) {
      if (!_walReady.isCompleted) _walReady.complete();
      return;
    }
    if (migratedCount > 0) {
      // Reload WALs after migration
      _admitLoadedWals(_loadWalsOverride != null ? await _loadWalsOverride!() : await WalFileManager.loadWals());
      if (!_isCurrent(generation)) {
        if (!_walReady.isCompleted) _walReady.complete();
        return;
      }
      Logger.debug("wal service after migration: ${_wals.length}");
      DebugLogManager.logInfo('WAL migration completed', {'migratedCount': migratedCount, 'totalAfter': _wals.length});
    }

    // Fix any inconsistent WAL states from old implementations
    await WalFileManager.migrateInconsistentWals(_wals);
    if (!_isCurrent(generation)) {
      if (!_walReady.isCompleted) _walReady.complete();
      return;
    }

    await _evaluateRetentionPressure();

    // Expired synced-copy auto-remove runs before the ready gate, so the
    // first list the user sees already reflects the retention policy. Never
    // let a sweep failure hold the ready gate: records stay for the next hook.
    try {
      await _removeExpiredSyncedCopies();
    } catch (e) {
      Logger.debug('synced-copy auto-remove sweep failed: $e');
    }

    if (!_walReady.isCompleted) _walReady.complete();
    _notifyUpdated(generation);
  }

  @override
  Future stop() async {
    final generation = _sessionGeneration;
    _chunkingTimer?.cancel();
    _flushingTimer?.cancel();
    _pendantTimer?.cancel();
    try {
      WidgetsBinding.instance.removeObserver(this);
    } catch (_) {}

    await _drainPendantTail(generation);
    await _enqueueBuffer(() => _chunk(generation));
    await _enqueueBuffer(() => _flush(generation));

    _frames = [];
    _frameSynced = [];
  }

  @override
  Future onAudioCodecChanged(BleAudioCodec codec) async {
    final generation = _sessionGeneration;
    // Always chunk+flush+clear to ensure clean session boundaries.
    // This is safe when frames are empty (_chunk returns immediately).
    await _drainPendantTail(generation);
    await _enqueueBuffer(() => _chunk(generation));
    await _enqueueBuffer(() => _flush(generation));
    if (!_isCurrent(generation)) return;
    _frames = [];
    _frameSynced = [];

    _framesPerSecond = codec.getFramesPerSecond();
    _codec = codec;
    _sourceClockEpoch++;
    _nextSourceFramePosition = 0;
    _captureEvidenceGeneration++;
  }

  @override
  void setDeviceInfo(String? deviceId, String? deviceModel) {
    _deviceId = deviceId;
    _deviceModel = deviceModel;
  }

  @override
  void setSessionGeolocation(Geolocation? geolocation) {
    _sessionGeolocation = _copyGeolocation(geolocation);
    _sessionGeolocationSetAt = geolocation == null ? null : _now().millisecondsSinceEpoch ~/ 1000;
  }

  Geolocation? _copyGeolocation(Geolocation? geolocation) =>
      geolocation == null ? null : Geolocation.fromJson(geolocation.toJson());

  Future _chunk(int generation) async {
    if (!_isCurrent(generation)) return;
    if (_frames.isEmpty) {
      Logger.debug("Frames are empty");
      return;
    }

    final now = _now();
    var timerEnd = now.millisecondsSinceEpoch ~/ 1000 - newFrameSyncDelaySeconds;
    var pivot = _frames.length - newFrameSyncDelaySeconds * _framesPerSecond;
    if (pivot <= 0) {
      return;
    }

    var high = pivot;
    var low = 0;
    final evidenceFrames = _frames.sublist(low, high);
    final evidence = stableCaptureEvidence(evidenceFrames);
    var chunk = _frames.sublist(low, high).map((f) => f.payload).toList();
    var timerStart = timerEnd - (high - low) ~/ _framesPerSecond;
    var chunkFrameCount = high - low;

    if (partitionsEvidenceRuns(_captureEvidenceV1DarkWrite, _codec, evidenceFrames)) {
      _storeSelectedRuns(
        evidenceFrames,
        _frameSynced.sublist(low, high),
        captureSelectionStartSeconds(
            now.subtract(const Duration(seconds: newFrameSyncDelaySeconds)), chunkFrameCount, _framesPerSecond),
        generation,
        extendMemWal: true,
        legacySelectionTimerStart: timerStart,
      );
    } else {
      final live = _liveEvidenceFor(evidenceFrames);

      bool shouldStored = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
      if (!shouldStored) {
        shouldStored = _frameSynced.sublist(low, high).any((synced) => !synced);
      }

      if (shouldStored) {
        final syncedOffset = syncedPrefixCount(_frameSynced.sublist(low, high));
        Logger.debug("${low} - ${high} - ${syncedOffset} - ${chunkFrameCount} - ${_framesPerSecond}");

        Wal wal;
        var walIdx = _wals.indexWhere(
          (w) =>
              w.storage == WalStorage.mem &&
              w.timerStart == timerStart &&
              w.device == (_deviceId ?? "omi") &&
              w.codec == _codec,
        );
        if (walIdx < 0) {
          wal = Wal(
            codec: _codec,
            timerStart: timerStart,
            data: chunk,
            storage: WalStorage.mem,
            status: syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss,
            device: _deviceId ?? "omi",
            deviceModel: _deviceModel ?? "Omi",
            seconds: chunkFrameCount ~/ _framesPerSecond,
            totalFrames: chunkFrameCount,
            syncedFrameOffset: syncedOffset,
            ownerUid: _currentWalOwnerUid(),
            captureRoot: evidence.root,
            sourceFrameStart: evidence.start,
            sourceClockEpoch: evidence.epoch,
            geolocation: _copyGeolocation(_sessionGeolocation),
            recordingSessionId: _activeRecordingSessionId,
            liveRingId: live.ringId,
            liveOrdinalStart: live.start,
            liveOrdinalEnd: live.end,
          );
          wal.liveConnectionEpoch = live.epoch;
          // Transport-only sync (socket send) must NOT start the retention
          // clock: syncedAt stays 0 so the sweep never treats an
          // unacknowledged streamed copy as server-confirmed.
          _wals.add(wal);
        } else {
          wal = _wals[walIdx];
          final contiguousEvidence = evidence.root != null &&
              wal.captureRoot == evidence.root &&
              wal.sourceClockEpoch == evidence.epoch &&
              wal.sourceFrameStart != null &&
              wal.sourceFrameStart! + wal.totalFrames == evidence.start;
          final oldFrameCount = wal.totalFrames;
          wal.data.addAll(chunk);
          wal.storage = WalStorage.mem;
          wal.totalFrames = contiguousEvidence ? oldFrameCount + chunkFrameCount : chunkFrameCount;
          if (!contiguousEvidence) {
            wal.captureRoot = null;
            wal.sourceFrameStart = null;
            wal.sourceClockEpoch = null;
          }
          if (live.start != null &&
              live.end != null &&
              wal.liveRingId == live.ringId &&
              wal.liveOrdinalEnd == live.start &&
              wal.liveConnectionEpoch == live.epoch) {
            wal.liveOrdinalEnd = live.end;
          } else {
            wal.liveRingId = null;
            wal.liveOrdinalStart = null;
            wal.liveOrdinalEnd = null;
            wal.liveConnectionEpoch = null;
          }
          wal.syncedFrameOffset = syncedOffset;
          wal.status = syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss;
          if (wal.status != WalStatus.synced) {
            // New unacknowledged frames invalidate the retention clock: the
            // next server-confirmed transition must re-stamp syncedAt so the
            // whole WAL ages from fresh confirmation, not a prior one.
            wal.syncedAt = 0;
          }
          // Transport-only sync (socket send) never starts the retention clock:
          // syncedAt stays 0 until a server-confirmed transition stamps it.
          _wals[walIdx] = wal;
        }

        if (wal.status == WalStatus.synced && _isCurrent(generation)) {
          listener.onWalSynced(wal);
        }
        _notifyUpdated(generation);
      }
    }

    Logger.debug("_chunk wals ${_wals.length}");

    _frames.removeRange(0, pivot);
    _frameSynced.removeRange(0, pivot);
  }

  void _storeSelectedRuns(
    List<WalFrame> selection,
    List<bool> selectionSynced,
    double selectionStartSeconds,
    int generation, {
    required bool extendMemWal,
    required int legacySelectionTimerStart,
  }) {
    for (final run in walEvidenceRunRanges(selection)) {
      final runFrames = selection.sublist(run.start, run.end);
      final runSynced = selectionSynced.sublist(run.start, run.end);
      final shouldStored = SharedPreferencesUtil().unlimitedLocalStorageEnabled || runSynced.any((synced) => !synced);
      if (!shouldStored) continue;
      final syncedOffset = syncedPrefixCount(runSynced);
      final frameCount = run.end - run.start;
      final timerStart = run.claimable
          ? (selectionStartSeconds + run.start / _framesPerSecond).floor()
          : legacySelectionTimerStart + run.start ~/ _framesPerSecond;
      final first = runFrames.first;
      final live = _liveEvidenceFor(runFrames);
      Wal wal;
      var walIdx = -1;
      if (extendMemWal) {
        walIdx = _wals.indexWhere(
          (w) =>
              w.storage == WalStorage.mem &&
              w.timerStart == timerStart &&
              w.device == (_deviceId ?? "omi") &&
              w.codec == _codec &&
              walExtendsRun(w, run, first),
        );
      }
      if (walIdx < 0) {
        wal = Wal(
          codec: _codec,
          timerStart: timerStart,
          data: runFrames.map((f) => f.payload).toList(),
          storage: WalStorage.mem,
          status: syncedOffset == frameCount ? WalStatus.synced : WalStatus.miss,
          device: _deviceId ?? "omi",
          deviceModel: _deviceModel ?? "Omi",
          seconds: frameCount ~/ _framesPerSecond,
          totalFrames: frameCount,
          syncedFrameOffset: syncedOffset,
          ownerUid: _currentWalOwnerUid(),
          captureRoot: run.claimable ? first.captureRoot : null,
          sourceFrameStart: run.claimable ? first.sourceFramePosition : null,
          sourceClockEpoch: run.claimable ? first.sourceClockEpoch : null,
          geolocation: _copyGeolocation(_sessionGeolocation),
          recordingSessionId: _activeRecordingSessionId,
          liveRingId: live.ringId,
          liveOrdinalStart: live.start,
          liveOrdinalEnd: live.end,
        );
        wal.liveConnectionEpoch = live.epoch;
        if (run.claimable) {
          wal.filePath = walEvidenceRunFileName(wal, selectionStartSeconds, run.start, _framesPerSecond);
        }
        _wals.add(wal);
      } else {
        wal = _wals[walIdx];
        final priorTotal = wal.totalFrames;
        final priorPrefix = wal.syncedFrameOffset;
        wal.data.addAll(runFrames.map((f) => f.payload).toList());
        wal.storage = WalStorage.mem;
        wal.totalFrames = priorTotal + frameCount;
        wal.seconds = wal.totalFrames ~/ _framesPerSecond;
        wal.syncedFrameOffset = priorPrefix == priorTotal ? priorTotal + syncedOffset : priorPrefix;
        if (live.start != null &&
            live.end != null &&
            wal.liveRingId == live.ringId &&
            wal.liveOrdinalEnd == live.start &&
            wal.liveConnectionEpoch == live.epoch) {
          wal.liveOrdinalEnd = live.end;
        } else {
          wal.liveRingId = null;
          wal.liveOrdinalStart = null;
          wal.liveOrdinalEnd = null;
          wal.liveConnectionEpoch = null;
        }
        wal.status = wal.syncedFrameOffset == wal.totalFrames ? WalStatus.synced : WalStatus.miss;
        if (wal.status != WalStatus.synced) {
          wal.syncedAt = 0;
        }
        _wals[walIdx] = wal;
      }
      if (wal.status == WalStatus.synced && _isCurrent(generation)) {
        listener.onWalSynced(wal);
      }
    }
    _notifyUpdated(generation);
  }

  ({int? start, int? end, int? ringId, int? epoch}) _liveEvidenceFor(List<WalFrame> frames) =>
      stableLiveWalEvidence(frames, _deviceId, _custody);

  void _removeFrameIndices(List<int> indices) {
    for (var i = indices.length - 1; i >= 0; i--) {
      _frames.removeAt(indices[i]);
      _frameSynced.removeAt(indices[i]);
    }
  }

  Future<void> _drainPendantTail(int generation) => _enqueueBuffer(() async {
        if (!_isCurrent(generation)) return;
        final indices = <int>[];
        for (var i = 0; i < _frames.length; i++) {
          if (_isPendantFrame(_frames[i])) indices.add(i);
        }
        if (indices.isEmpty) return;
        final frames = indices.map((i) => _frames[i]).toList();
        final synced = indices.map((i) => _frameSynced[i]).toList();

        var shouldStore = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
        if (!shouldStore) shouldStore = synced.any((s) => !s);
        if (!shouldStore) {
          _removeFrameIndices(indices);
          return;
        }
        final syncedOffset = syncedPrefixCount(synced);

        final frameCount = frames.length;
        final now = _now();
        var timerEnd = now.millisecondsSinceEpoch ~/ 1000;
        var timerStart = timerEnd - frameCount ~/ _framesPerSecond;
        final evidence = stableCaptureEvidence(frames);
        final live = _liveEvidenceFor(frames);

        if (partitionsEvidenceRuns(_captureEvidenceV1DarkWrite, _codec, frames)) {
          _storeSelectedRuns(
            frames,
            synced,
            captureSelectionStartSeconds(now, frameCount, _framesPerSecond),
            generation,
            extendMemWal: false,
            legacySelectionTimerStart: timerStart,
          );
        } else {
          final wal = Wal(
            codec: _codec,
            timerStart: timerStart,
            data: frames.map((f) => f.payload).toList(),
            storage: WalStorage.mem,
            status: syncedOffset == frameCount ? WalStatus.synced : WalStatus.miss,
            device: _deviceId ?? "omi",
            deviceModel: _deviceModel ?? "Omi",
            seconds: frameCount ~/ _framesPerSecond,
            totalFrames: frameCount,
            syncedFrameOffset: syncedOffset,
            ownerUid: _currentWalOwnerUid(),
            captureRoot: evidence.root,
            sourceFrameStart: evidence.start,
            sourceClockEpoch: evidence.epoch,
            geolocation: _copyGeolocation(_sessionGeolocation),
            recordingSessionId: _activeRecordingSessionId,
            liveRingId: live.ringId,
            liveOrdinalStart: live.start,
            liveOrdinalEnd: live.end,
          );
          wal.liveConnectionEpoch = live.epoch;
          _wals.add(wal);
        }
        _removeFrameIndices(indices);
        _notifyUpdated(generation);
        await _flush(generation);
      });

  int _storageFileSeq = 0;

  Future<String> _uniqueStorageFileName(Wal wal) async {
    final claimable = captureEvidenceWalClaimable(wal);
    final planned = wal.filePath;
    var name = claimable && planned != null && planned.isNotEmpty ? planned.split('/').last : wal.getFileName();
    if (!_fileReferencedByOtherWal(wal, name) && !await _localFileExistsByName(name)) return name;
    for (;;) {
      final candidate = walCollisionName(name, _storageFileSeq++, claimable);
      if (!_fileReferencedByOtherWal(wal, candidate) && !await _localFileExistsByName(candidate)) {
        return candidate;
      }
    }
  }

  Future<bool> _localFileExistsByName(String fileName) async {
    final path = await Wal.getFilePath(fileName);
    if (path == null) return false;
    return File(path).exists();
  }

  Future _flush(int generation) async {
    Logger.debug("_flushing");
    int flushedCount = 0;
    final durableWals = <Wal>[];
    final wals = List<Wal>.from(_wals);
    for (var i = 0; i < wals.length; i++) {
      final wal = wals[i];

      if (wal.storage == WalStorage.mem) {
        final fileName = await _uniqueStorageFileName(wal);
        String? filePath = await Wal.getFilePath(fileName);
        if (filePath == null) {
          DebugLogManager.logError('LocalWalSync flush error: Flush failed: cannot get file path', null, null, {
            'walId': wal.id,
            'timerStart': wal.timerStart,
          });
          throw Exception('Flushing to storage failed. Cannot get file path.');
        }

        List<int> data = [];
        for (int i = 0; i < wal.data.length; i++) {
          var frame = wal.data[i];

          final byteFrame = ByteData(frame.length);
          for (int j = 0; j < frame.length; j++) {
            byteFrame.setUint8(j, frame[j]);
          }
          data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
          data.addAll(byteFrame.buffer.asUint8List());
        }
        if (!await _checkStorageAdmission(
          bytes: data.length,
          admittedGeneration: generation,
          failClosedOnUnknownSpace: false,
        )) {
          if (_isPendantWal(wal)) _pendantBlockedByStorage = true;
          break;
        }
        final file = File(filePath);
        try {
          await file.writeAsBytes(data, flush: true);
        } catch (e) {
          Logger.debug('LocalWalSync: flush write failed for ${wal.id}: $e');
          _releaseAdmission(data.length);
          if (_isPendantWal(wal)) _pendantBlockedByStorage = true;
          break;
        }
        _consumeAdmission(data.length);
        wal.filePath = fileName;
        wal.storage = WalStorage.disk;
        if (wal.liveRingId != null && wal.liveOrdinalStart != null) {
          _liveProofPendingWalIds.add(_durableKey(wal));
        }

        Logger.debug("_flush file ${wal.filePath}");
        flushedCount++;
        durableWals.add(wal);
      }
    }

    if (flushedCount > 0) {
      DebugLogManager.logInfo('Flushed WALs from memory to disk', {'count': flushedCount});
    }

    await _evaluateRetentionPressure();
    final indexSaved = await _saveWalsToFile(generation);
    if (indexSaved && flushedCount > 0) _pendantBlockedByStorage = false;

    if (indexSaved) {
      for (final wal in durableWals) {
        wal.data = [];
      }
      for (final wal in List<Wal>.from(_wals)) {
        if (!_liveProofPendingWalIds.contains(_durableKey(wal))) continue;
        await _reportDurableLiveWal(wal, generation);
        _liveProofPendingWalIds.remove(_durableKey(wal));
      }
    }
  }

  Future<void> _reportDurableLiveWal(Wal wal, int generation) async {
    final ringId = wal.liveRingId;
    final start = wal.liveOrdinalStart;
    final end = wal.liveOrdinalEnd;
    final epoch = wal.liveConnectionEpoch;
    final deviceId = wal.device;
    if (ringId == null || start == null || end == null || epoch == null) return;
    if (!_isCurrent(generation)) return;
    final fileName = wal.filePath ?? wal.getFileName();
    var fileBytes = 0;
    try {
      final path = await Wal.getFilePath(fileName);
      if (path != null) fileBytes = await File(path).length();
    } catch (_) {}
    await _custody.recordDurableLiveFrames(
      deviceId,
      epoch,
      start,
      end,
      CustodyWalRef(
        fileName: fileName,
        bytes: fileBytes,
        frames: wal.totalFrames,
        liveRingId: ringId,
        liveOrdinalStart: start,
        liveOrdinalEnd: end,
      ),
    );
    DebugLogManager.logEvent('pendant_custody', {
      'action': 'live_durable',
      'device': deviceId,
      'ring_id': ringId,
      'ordinal_start': start,
      'ordinal_end': end,
      'file_bytes': fileBytes,
    });
    await _maybeAdvanceCustody(deviceId, epoch, ringId);
  }

  Future<void> _maybeAdvanceCustody(String deviceId, int epoch, int? proofRingId) async {
    final target = await _custody.validatedAdvanceTarget(deviceId, epoch, proofRingId);
    if (target == null) return;
    DeviceConnection? connection;
    try {
      connection =
          await (_connectionResolver?.call(deviceId) ?? ServiceManager.instance().device.ensureConnection(deviceId));
    } catch (e) {
      Logger.debug('LocalWalSync: custody advance skipped, no connection: $e');
      return;
    }
    if (connection == null) return;
    if (connection.ringCustodyEpoch != epoch) return;
    final ack = await connection.advanceRingCustody(target, expectedEpoch: epoch, expectedRingId: proofRingId);
    if (ack == null) return;
    if (ack.isOk) {
      await _custody.markAdvanced(deviceId, epoch, target);
      DebugLogManager.logEvent('pendant_custody', {
        'action': 'live_advance',
        'device': deviceId,
        'ring_id': proofRingId,
        'seq': target,
      });
      return;
    }
    if (ack.isSeqOutOfRange) {
      final info = await connection.getRingInfo();
      if (connection.ringCustodyEpoch != epoch || info == null) return;
      _custody.noteInfo(deviceId, epoch, info);
      if ((proofRingId == null || info.ringId == proofRingId) && target <= info.readSeq) {
        await _custody.markAdvanced(deviceId, epoch, target);
      }
      return;
    }
    if (ack.isRingIdMismatch) {
      _custody.noteMismatch(deviceId, epoch);
      DebugLogManager.logWarning('pendant_custody ring_id mismatch; refusing release', {
        'action': 'advance_mismatch',
        'device': deviceId,
        'ring_id': proofRingId,
      });
    }
  }

  int get _pendingDiskWalCount => [
        ..._retiredWals,
        ..._foreignWals,
        ..._wals,
      ].where((wal) => wal.storage == WalStorage.disk && (wal.status != WalStatus.synced || wal.syncedAt == 0)).length;

  /// Surfaces the bounded-retention pressure once per cap-engagement event.
  /// Pending (unsynced) copies are never evicted and admission is not refused
  /// for count; only the disk reserve refuses new audio.
  ///
  /// Synced WALs are excluded because their lifecycle is governed by the
  /// user's local-storage preference; this policy specifically bounds audio
  /// retained because the backend has not acknowledged it.
  Future<int> _evaluateRetentionPressure() async {
    final retained = _pendingDiskWalCount;
    if (retained < maxRetainedCaptureWalCount) {
      if (_retentionRisk?.reason == 'count_cap') _retentionRisk = null;
      return 0;
    }
    if (_retentionRisk == null) {
      _admissionBlockedCount = 0;
      _retentionRisk = WalRetentionRisk(
        engagedAt: _now(),
        retainedCount: retained,
        blockedCount: 0,
        reason: 'count_cap',
      );
    }
    DebugLogManager.logEvent('wal_admission_pressure', {
      'policy': 'admission_count_cap',
      'cap': maxRetainedCaptureWalCount,
      'retained_count': retained,
      'blocked_count': _admissionBlockedCount,
    });
    return retained - maxRetainedCaptureWalCount;
  }

  int _admissionBlockedCount = 0;

  Future<int?> _freeDiskBytes() async {
    final override = _freeDiskBytesOverride;
    if (override != null) return override();
    try {
      final dir = await getApplicationDocumentsDirectory();
      final mb = await DiskSpace.getFreeDiskSpaceForPath(dir.path);
      if (mb == null) return null;
      return (mb * 1024 * 1024).round();
    } catch (e) {
      Logger.debug('LocalWalSync: free disk probe failed: $e');
      return null;
    }
  }

  @override
  Future<bool> ensureStorageAdmission({required int bytes, required int admittedGeneration}) =>
      _checkStorageAdmission(bytes: bytes, admittedGeneration: admittedGeneration, failClosedOnUnknownSpace: true);

  Future<void> _admissionQueue = Future.value();
  final List<int> _admissionReservations = [];

  Future<T> _enqueueAdmission<T>(Future<T> Function() op) {
    final prev = _admissionQueue;
    final completer = Completer<T>();
    _admissionQueue = prev.then((_) async {
      try {
        completer.complete(await op());
      } catch (e, st) {
        completer.completeError(e, st);
      }
    });
    return completer.future;
  }

  void _consumeAdmission(int bytes) {
    final i = _admissionReservations.indexOf(bytes);
    if (i >= 0) _admissionReservations.removeAt(i);
  }

  Future<int?> _walFileLength(Wal wal) async {
    final name = wal.filePath;
    if (name == null) return null;
    try {
      final path = await Wal.getFilePath(name);
      if (path == null) return null;
      return File(path).length();
    } catch (_) {
      return null;
    }
  }

  void _releaseAdmission(int bytes) => _consumeAdmission(bytes);

  @override
  void releaseStorageAdmission(int bytes) => _releaseAdmission(bytes);

  Future<bool> _checkStorageAdmission({
    required int bytes,
    required int admittedGeneration,
    required bool failClosedOnUnknownSpace,
  }) {
    return _enqueueAdmission(
      () => _checkStorageAdmissionLocked(
        bytes: bytes,
        admittedGeneration: admittedGeneration,
        failClosedOnUnknownSpace: failClosedOnUnknownSpace,
      ),
    );
  }

  Future<bool> _checkStorageAdmissionLocked({
    required int bytes,
    required int admittedGeneration,
    required bool failClosedOnUnknownSpace,
  }) async {
    if (!_isCurrent(admittedGeneration)) return false;
    final retained = _pendingDiskWalCount + _admissionReservations.length;
    String? blockReason;
    var unknownSpaceDiagnostic = false;
    final free = await _freeDiskBytes();
    if (!_isCurrent(admittedGeneration)) return false;
    if (free == null) {
      if (failClosedOnUnknownSpace) {
        blockReason = 'disk_space_unknown';
      } else {
        unknownSpaceDiagnostic = true;
      }
    } else {
      final reserved = _admissionReservations.fold<int>(0, (a, b) => a + b);
      if (free - reserved - bytes < minFreeDiskReserveBytes) {
        blockReason = 'disk_reserve';
      }
    }
    if (blockReason == null) {
      _admissionReservations.add(bytes);
      if (_retentionRisk?.reason == 'disk_reserve') _retentionRisk = null;
      if (unknownSpaceDiagnostic) {
        DebugLogManager.logEvent('wal_admission_space_unknown', {
          'policy': 'admission_count_cap',
          'retained_count': retained,
          'reason': 'disk_space_unknown',
          'proposed_bytes': bytes,
        });
      }
      return true;
    }

    _admissionBlockedCount++;
    _retentionRisk = WalRetentionRisk(
      engagedAt: _retentionRisk?.engagedAt ?? _now(),
      retainedCount: retained,
      blockedCount: _admissionBlockedCount,
      reason: blockReason,
    );
    DebugLogManager.logEvent('wal_admission_blocked', {
      'policy': 'admission_count_cap',
      'cap': maxRetainedCaptureWalCount,
      'retained_count': retained,
      'blocked_count': _admissionBlockedCount,
      'reason': blockReason,
      'proposed_bytes': bytes,
    });
    _notifyUpdated(admittedGeneration);
    return false;
  }

  @override
  Future<bool> hasDurableWal(Wal wal, {required int admittedGeneration}) async {
    if (!_isCurrent(admittedGeneration)) return false;
    if (!_isTrackedWal(wal) || wal.storage != WalStorage.disk) return false;
    if (!_confirmedDurableWalKeys.contains(_durableKey(wal))) return false;
    return _localFileExists(wal);
  }

  /// Auto-remove preference sweep: deletes phone-local copies of synced
  /// recordings whose [Wal.syncedAt] is older than the retention window.
  /// Cloud storage keeps the data — the server ack is what makes the local
  /// copy redundant. Records with an unknown sync time (syncedAt == 0: synced
  /// before the field existed, or a live-streamed copy whose status came from
  /// transport-only socket sends rather than a server acknowledgement) are
  /// deliberately never removed.
  ///
  /// Best-effort and quiet: a record whose file delete fails stays for the
  /// next hook. Returns the number of local copies removed.
  @visibleForTesting
  Future<int> enforceSyncedCopyRetentionForTesting() => _removeExpiredSyncedCopies();

  @override
  Future<int> applySyncedCopyRetention() => _removeExpiredSyncedCopies();

  Future<int> _removeExpiredSyncedCopies() async {
    final prefs = SharedPreferencesUtil();
    if (!prefs.autoRemoveSyncedCopies) return 0;
    final generation = _sessionGeneration;
    final cutoff = _now().millisecondsSinceEpoch ~/ 1000 - prefs.autoRemoveSyncedCopiesDays * Duration.secondsPerDay;
    // All three durable buckets: retired (logged-out) and foreign-owner
    // (parked at load) records occupy the same device storage as the active
    // account's, so the retention preference applies to them too — matching
    // the device-wide scope of _enforceRetentionPolicy.
    final expired = [..._retiredWals, ..._foreignWals, ..._wals]
        .where(
          (wal) =>
              wal.storage == WalStorage.disk &&
              wal.status == WalStatus.synced &&
              wal.syncedAt > 0 &&
              wal.syncedAt <= cutoff,
        )
        .toList();
    if (expired.isEmpty) return 0;

    var removed = 0;
    for (final wal in expired) {
      if (!_isCurrent(generation)) break;
      if (await _deleteWal(wal, generation: generation)) removed++;
    }
    if (removed == 0) return 0;

    await _saveWalsToFile(generation);
    _notifyUpdated(generation);
    DebugLogManager.logEvent('wal_synced_copy_autoremove', {
      'policy': 'synced_age_days',
      'days': prefs.autoRemoveSyncedCopiesDays,
      'removed': removed,
    });
    return removed;
  }

  @visibleForTesting
  Future<int> enforceRetentionPolicyForTesting() => _evaluateRetentionPressure();

  Future<bool> _saveWalsToFile(int generation) async {
    if (!_isCurrent(generation)) return false;
    // The save rewrites the whole index from memory, so every durable bucket
    // must be included: retired (logged-out) and foreign-owner (parked at
    // load) records alike — omitting either would silently delete those
    // recordings from disk on the next save.
    final snapshot = [..._retiredWals, ..._foreignWals, ..._wals].where((w) => w.storage != WalStorage.mem).toList();
    final confirmedKeys = snapshot.where((w) => w.storage == WalStorage.disk).map(_durableKey).toList();
    Logger.debug('Saving WALs to file');
    if (_persistWalsOverride != null) {
      await _persistWalsOverride!(snapshot);
      _confirmedDurableWalKeys.addAll(confirmedKeys);
      return true;
    }
    if (!await WalFileManager.saveWals(snapshot)) {
      throw StateError('WAL index save reported failure');
    }
    _confirmedDurableWalKeys.addAll(confirmedKeys);
    return true;
  }

  String _durableKey(Wal wal) => '${wal.id}|${wal.filePath ?? wal.getFileName()}';

  /// In the `upload` phase [kept] holds only the members an upload accepted (HTTP 200/202).
  void _emitWalTranscriptCoverage({
    required int generation,
    required String phase,
    List<Wal> covered = const [],
    List<Wal> kept = const [],
    String? failClosedReason,
  }) {
    if (!_isCurrent(generation)) return;
    double audioSeconds(List<Wal> wals) => wals.fold(0.0, (sum, wal) => sum + walAudioSeconds(wal));
    final fields = <String, Object?>{
      'policy': 'retain_covered_upload_gaps',
      'phase': phase,
      'retained_covered_count': covered.length,
      'retained_covered_seconds': audioSeconds(covered),
      'kept_count': kept.length,
      'kept_seconds': audioSeconds(kept),
      'kept_uploaded_count': phase == 'upload' ? kept.length : 0,
      'kept_uploaded_seconds': phase == 'upload' ? audioSeconds(kept) : 0.0,
      if (failClosedReason != null) 'fail_closed_reason': failClosedReason,
    };
    final override = _coverageTelemetryOverride;
    if (override != null) {
      override(fields);
      return;
    }
    DebugLogManager.logEvent('wal_transcript_coverage', fields);
    AnalyticsManager().trackEvent('wal_transcript_coverage', properties: fields);
  }

  bool _fileReferencedByOtherWal(Wal wal, String fileName) {
    for (final other in [..._retiredWals, ..._foreignWals, ..._wals]) {
      if (identical(other, wal)) continue;
      final otherPath = other.filePath;
      final otherName = (otherPath != null && otherPath.isNotEmpty) ? otherPath.split('/').last : other.getFileName();
      if (otherName == fileName) return true;
    }
    return false;
  }

  bool _isTrackedWal(Wal wal) =>
      _wals.any((w) => identical(w, wal)) ||
      _retiredWals.any((w) => identical(w, wal)) ||
      _foreignWals.any((w) => identical(w, wal));

  Future<bool> _deleteWal(Wal wal, {required int generation}) async {
    if (!_isCurrent(generation) || !_isTrackedWal(wal)) return false;
    final filePath = wal.filePath;
    if (filePath != null && filePath.isNotEmpty) {
      try {
        final fullPath = await Wal.getFilePath(filePath);
        if (fullPath == null) return false;
        if (!_isCurrent(generation) || !_isTrackedWal(wal)) return false;
        final type = await FileSystemEntity.type(fullPath, followLinks: false);
        if (!_isCurrent(generation) || !_isTrackedWal(wal)) return false;
        if (type == FileSystemEntityType.file || type == FileSystemEntityType.link) {
          if (!_fileReferencedByOtherWal(wal, fullPath.split('/').last)) {
            await File(fullPath).delete();
            if (!_isCurrent(generation)) return false;
          }
        } else if (type != FileSystemEntityType.notFound) {
          return false;
        }
      } catch (e) {
        Logger.debug(e.toString());
        return false;
      }
    }

    final removed = _wals.remove(wal) | _retiredWals.remove(wal) | _foreignWals.remove(wal);
    return removed;
  }

  @override
  Future deleteWal(Wal wal) async {
    final generation = _sessionGeneration;
    Wal? target;
    for (final candidate in _wals) {
      if (identical(candidate, wal)) {
        target = candidate;
        break;
      }
    }
    target ??= _wals
        .where(
          (w) =>
              w.id == wal.id &&
              w.storage == wal.storage &&
              w.codec == wal.codec &&
              w.ownerUid == wal.ownerUid &&
              w.recordingSessionId == wal.recordingSessionId &&
              (wal.filePath == null ||
                  wal.filePath!.isEmpty ||
                  ((w.filePath != null && w.filePath!.isNotEmpty) ? w.filePath!.split('/').last : w.getFileName()) ==
                      wal.filePath!.split('/').last),
        )
        .singleOrNull;
    if (target == null) {
      _notifyUpdated(generation);
      return;
    }
    if (await _deleteWal(target, generation: generation)) {
      await _saveWalsToFile(generation);
    }
    _notifyUpdated(generation);
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss).toList();
  }

  /// Returns unsynced WALs whose timerStart falls within [sessionStartSeconds, now].
  /// Used by the live capture screen to show inline audio safety indicators.
  List<Wal> getSessionUnsyncedWals(int sessionStartSeconds) {
    final now = _now().millisecondsSinceEpoch ~/ 1000;
    return _wals
        .where(
          (w) =>
              w.status == WalStatus.miss &&
              w.storage == WalStorage.disk &&
              w.timerStart >= sessionStartSeconds &&
              w.timerStart <= now,
        )
        .toList();
  }

  /// All disk WALs of the session window — synced ones included — so callers
  /// can render a pending/total backlog count that drains as uploads finish.
  /// Same window and storage scope as [getSessionUnsyncedWals].
  List<Wal> getSessionWals(int sessionStartSeconds) {
    final now = _now().millisecondsSinceEpoch ~/ 1000;
    return _wals
        .where((w) => w.storage == WalStorage.disk && w.timerStart >= sessionStartSeconds && w.timerStart <= now)
        .toList();
  }

  /// Mark a WAL as synced and persist the change to disk.
  Future<void> markWalSyncedAndPersist(Wal wal) async {
    final generation = _sessionGeneration;
    wal.status = WalStatus.synced;
    if (wal.syncedAt == 0) {
      wal.syncedAt = _now().millisecondsSinceEpoch ~/ 1000;
    }
    await _saveWalsToFile(generation);
    _notifyUpdated(generation);
  }

  /// Force-drain all in-flight frames (including the tail buffer that _chunk() normally
  /// keeps in memory) and flush everything to disk. Call this when a capture session ends
  /// to ensure no audio is lost in memory.
  Future<void> finalizeCurrentSession() async {
    final generation = _sessionGeneration;
    await _enqueueBuffer(() => _finalizeCurrentSession(generation));
  }

  Future<void> _finalizeCurrentSession(int generation) async {
    if (_frames.isEmpty) return;

    final high = _frames.length;
    if (high <= 0) return;

    final now = _now();
    var timerEnd = now.millisecondsSinceEpoch ~/ 1000;
    final evidenceFrames = _frames.sublist(0, high);
    final evidence = stableCaptureEvidence(evidenceFrames);
    var chunk = _frames.sublist(0, high).map((f) => f.payload).toList();
    var timerStart = timerEnd - high ~/ _framesPerSecond;
    var chunkFrameCount = high;

    // Same shouldStored check as _chunk(): one unconfirmed frame is enough to
    // retain the session. A transport send is not transcript confirmation.
    bool shouldStored = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    if (!shouldStored) {
      shouldStored = _frameSynced.sublist(0, high).any((synced) => !synced);
    }

    if (shouldStored) {
      if (partitionsEvidenceRuns(_captureEvidenceV1DarkWrite, _codec, evidenceFrames)) {
        _storeSelectedRuns(
          evidenceFrames,
          _frameSynced.sublist(0, high),
          captureSelectionStartSeconds(now, chunkFrameCount, _framesPerSecond),
          generation,
          extendMemWal: false,
          legacySelectionTimerStart: timerStart,
        );
      } else {
        final syncedOffset = syncedPrefixCount(_frameSynced.sublist(0, high));

        // Use a distinct timerStart so we don't collide with WALs from _chunk().
        // This is the tail buffer that _chunk() left behind.
        final tailWal = Wal(
          codec: _codec,
          timerStart: timerStart,
          data: chunk,
          storage: WalStorage.mem,
          status: syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss,
          device: _deviceId ?? "omi",
          deviceModel: _deviceModel ?? "Omi",
          seconds: chunkFrameCount ~/ _framesPerSecond,
          totalFrames: chunkFrameCount,
          syncedFrameOffset: syncedOffset,
          ownerUid: _currentWalOwnerUid(),
          captureRoot: evidence.root,
          sourceFrameStart: evidence.start,
          sourceClockEpoch: evidence.epoch,
          geolocation: _copyGeolocation(_sessionGeolocation),
          recordingSessionId: _activeRecordingSessionId,
        );
        // Transport-only sync (socket send) must NOT start the retention
        // clock: syncedAt stays 0 so the sweep never treats an
        // unacknowledged streamed tail copy as server-confirmed.
        _wals = List.from(_wals)..add(tailWal);
      }
    }

    _frames = [];
    _frameSynced = [];

    // Flush all in-memory WALs to disk immediately
    await _flush(generation);
    _notifyUpdated(generation);
    Logger.debug('finalizeCurrentSession: drained $chunkFrameCount frames (stored=$shouldStored), flushed to disk');
  }

  /// Stamp all session WALs with the given conversationId and persist to disk.
  /// This makes WAL→conversation linkage survive app kill.
  ///
  /// A WAL created for the recording passed to [prepareConversationStamp] is
  /// stamped even when its backdated [Wal.timerStart] is earlier than
  /// [sessionStartSeconds]. A WAL that already belongs to a different recording
  /// is left alone, so a session roll during the flush cannot attach the next
  /// recording to this conversation.
  Future<void> stampConversationId(int sessionStartSeconds, String conversationId) async {
    final generation = _sessionGeneration;
    final now = _now().millisecondsSinceEpoch ~/ 1000;
    final recordingId = _conversationStampRecordingId;
    _conversationStampRecordingId = null;
    final matchRecording = recordingId != null && recordingId.isNotEmpty;
    int stamped = 0;
    for (final wal in _wals) {
      if (wal.status != WalStatus.miss || wal.conversationId != null) continue;
      final walRecording = wal.recordingSessionId;
      final foreignRecording = walRecording != null && walRecording.isNotEmpty && walRecording != recordingId;
      if (foreignRecording) continue;
      final matchesRecording = matchRecording && walRecording == recordingId;
      final inWindow = wal.timerStart >= sessionStartSeconds && wal.timerStart <= now;
      if (matchesRecording || inWindow) {
        wal.conversationId = conversationId;
        stamped++;
      }
    }
    if (stamped > 0) {
      await _saveWalsToFile(generation);
      Logger.debug('stampConversationId: stamped $stamped WALs with conversation $conversationId');
    }
  }

  /// Returns WALs that have a conversationId but haven't been synced yet.
  /// Used for startup recovery after app kill.
  List<Wal> getOrphanedWals() {
    return _wals.where((w) => isAutoUploadEligible(w) && w.conversationId != null).toList();
  }

  /// Persist retry metadata (retryCount, lastRetryAt) for a WAL after failed sync attempts.
  Future<void> persistRetryMetadata(Wal wal) async {
    final generation = _sessionGeneration;
    await _saveWalsToFile(generation);
  }

  /// Re-arm recordings that spent their transient retry budget when the
  /// network returns. Permanent audio/lookback failures use terminal statuses
  /// and are intentionally untouched.
  Future<int> resetExhaustedAutoRetries() async {
    final generation = _sessionGeneration;
    var reset = 0;
    for (final wal in _wals) {
      if (wal.status != WalStatus.miss || wal.storage != WalStorage.disk || wal.retryCount < walMaxAutoRetries) {
        continue;
      }
      wal.retryCount = 0;
      wal.lastRetryAt = 0;
      reset++;
    }
    if (reset > 0) {
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
      DebugLogManager.logInfo('Re-armed exhausted WAL retries after connectivity restored', {'count': reset});
    }
    return reset;
  }

  /// Judges each stamped WAL of [conversationId] against the saved transcript: a covered WAL moves
  /// into synced retention (the `autoRemoveSyncedCopies` lifecycle) and is not uploaded — the saved
  /// text suppresses the repair upload, never deletes the copy; an uncovered WAL stays `miss`,
  /// marked `keptForTranscriptRecovery`, and uploads for repair. Without [transcriptSpans], or with
  /// an explicit [failClosedReason], every eligible stamped WAL fails closed into repair.
  Future<({int released, int kept})> confirmSessionTranscription(
    int sessionStartSeconds,
    String conversationId, {
    List<(int, int)>? transcriptSpans,
    int? conversationStartSeconds,
    String? failClosedReason,
  }) async {
    final generation = _sessionGeneration;
    // A stamped WAL can start before the session window — its timerStart is backdated from its
    // frame count — so the transcript evidence judges every stamped copy instead.
    final stamped = _wals.where((wal) => wal.conversationId == conversationId).toList();
    if (stamped.isEmpty) return (released: 0, kept: 0);

    final spans =
        failClosedReason == null && transcriptSpans != null && transcriptSpans.isNotEmpty ? transcriptSpans : null;
    final reason = failClosedReason ?? (spans != null ? null : 'no_spans');
    final nowSeconds = _now().millisecondsSinceEpoch ~/ 1000;
    final covered = <Wal>[], kept = <Wal>[];
    for (final wal in stamped) {
      // Only phone-side pending copies and transport-only synced ones (socket sends, never
      // server-confirmed) are judged; in-flight, durable and terminal copies never regress.
      final eligible = !wal.isSyncing &&
          (wal.storage == WalStorage.disk || wal.storage == WalStorage.mem) &&
          (wal.status == WalStatus.miss || wal.status == WalStatus.synced && wal.syncedAt == 0);
      if (!eligible) continue;
      if (spans != null && walCoveredByTranscript(wal, spans, conversationStartSeconds ?? sessionStartSeconds)) {
        wal.status = WalStatus.synced;
        wal.syncedAt = nowSeconds;
        wal.keptForTranscriptRecovery = false;
        covered.add(wal);
      } else {
        // An uncovered transport-only synced copy reclassifies to miss so
        // fail-closed recovery uploads it instead of status-skipping it.
        _keepForTranscriptRepair(wal);
        kept.add(wal);
      }
    }
    if (covered.isNotEmpty || kept.isNotEmpty) {
      try {
        await _saveWalsToFile(generation);
      } catch (_) {
        // The durable index never recorded the coverage, so covered copies fail closed too.
        if (_isCurrent(generation)) {
          covered.where((wal) => _wals.any((tracked) => identical(tracked, wal))).forEach(_keepForTranscriptRepair);
        }
        rethrow;
      }
    }
    if (_isCurrent(generation) && covered.isNotEmpty) _notifyUpdated(generation);
    _emitWalTranscriptCoverage(
      generation: generation,
      phase: 'confirmation',
      covered: covered,
      kept: kept,
      failClosedReason: reason,
    );
    return (released: 0, kept: kept.length);
  }

  void _keepForTranscriptRepair(Wal wal) {
    wal.status = WalStatus.miss;
    wal.syncedAt = 0;
    wal.keptForTranscriptRecovery = true;
  }

  /// Returns the approximate duration (in seconds) of UNSYNCED audio frames
  /// still in memory. Frames already delivered via WebSocket are excluded so
  /// the "Audio Saved Locally" indicator only appears when data is at risk.
  int getInFlightSeconds() {
    if (_framesPerSecond <= 0) return 0;
    int unsyncedCount = 0;
    for (int i = 0; i < _frameSynced.length; i++) {
      if (!_frameSynced[i]) unsyncedCount++;
    }
    return unsyncedCount ~/ _framesPerSecond;
  }

  @override
  Future<List<Wal>> getAllWals() async {
    return List.from(_wals);
  }

  @override
  Future<void> deleteAllSyncedWals() async {
    final generation = _sessionGeneration;
    final syncedWals = _wals.where((w) => w.status == WalStatus.synced).toList();
    for (final wal in syncedWals) {
      if (!_isCurrent(generation)) break;
      await _deleteWal(wal, generation: generation);
    }
    await _saveWalsToFile(generation);
    _notifyUpdated(generation);
  }

  @override
  Future<void> deleteAllPendingWals() async {
    final generation = _sessionGeneration;
    final pendingWals = _wals.where((w) => w.status == WalStatus.miss).toList();
    for (final wal in pendingWals) {
      if (!_isCurrent(generation)) break;
      await _deleteWal(wal, generation: generation);
    }
    await _saveWalsToFile(generation);
    _notifyUpdated(generation);
  }

  /// Removes terminally unavailable recordings when the user explicitly
  /// clears all local recordings. They are intentionally excluded from the
  /// retryable Pending action.
  @override
  Future<void> deleteAllCorruptedWals() async {
    final generation = _sessionGeneration;
    final corruptedWals = _wals
        .where(
          (w) =>
              w.status == WalStatus.corrupted ||
              w.status == WalStatus.outsideRecoveryWindow ||
              w.status == WalStatus.unsupportedAudio ||
              w.status == WalStatus.uploadRejected,
        )
        .toList();
    for (final wal in corruptedWals) {
      if (!_isCurrent(generation)) break;
      await _deleteWal(wal, generation: generation);
    }
    await _saveWalsToFile(generation);
    _notifyUpdated(generation);
  }

  @override
  WalFrame onFrameCaptured(WalFrame frame, {String? captureRoot}) {
    if (captureRoot != _captureEvidenceRoot) {
      _captureEvidenceRoot = captureRoot;
      // A restored WAL for the same root is the durable high-water mark.
      // Never reuse an ordinal after an app restart or an index reload.
      final prior = _wals.where((wal) => wal.captureRoot == captureRoot && wal.sourceFrameStart != null).toList();
      if (captureRoot != null && prior.isNotEmpty) {
        _sourceClockEpoch = prior.map((wal) => wal.sourceClockEpoch ?? 0).reduce(max);
        _nextSourceFramePosition = prior
            .where((wal) => wal.sourceClockEpoch == _sourceClockEpoch)
            .map((wal) => wal.sourceFrameStart! + wal.totalFrames)
            .reduce(max);
      } else {
        _nextSourceFramePosition = 0;
        _sourceClockEpoch = 0;
      }
    }
    int? liveOrdinal;
    int? liveEpoch;
    int? liveRingId;
    if (_isPendantFrame(frame)) {
      if ((_retentionRisk != null || _pendantBlockedByStorage) &&
          _countPendantBuffered() >= _maxPendantBufferedFrames) {
        _pendantDroppedWhileBlocked++;
        DebugLogManager.logWarning('LocalWalSync: pendant frame dropped, storage admission blocked', {
          'device': _deviceId,
          'dropped_count': _pendantDroppedWhileBlocked,
        });
        return frame;
      }
      final counter = _packetCounterOf(frame);
      final fragment = _fragmentIndexOf(frame);
      if (counter != null && fragment != null) {
        liveEpoch = _custody.latestEpoch(_deviceId!);
        liveOrdinal = _custody.observeLiveFrameLatest(_deviceId!, counter, fragment);
        liveRingId = liveOrdinal != null ? _custody.currentRingId(_deviceId!) : null;
        if (liveOrdinal == null || liveRingId == null) {
          liveEpoch = null;
          liveOrdinal = null;
          liveRingId = null;
        }
      }
    }
    final positioned = WalFrame(
      payload: frame.payload,
      syncKey: frame.syncKey,
      captureRoot: captureRoot,
      sourceFramePosition: captureRoot == null ? null : _nextSourceFramePosition++,
      sourceClockEpoch: captureRoot == null ? null : _sourceClockEpoch,
      connectionEpoch: liveEpoch,
      livePacketCounter: liveOrdinal != null ? _packetCounterOf(frame) : null,
      liveFragmentIndex: liveOrdinal != null ? _fragmentIndexOf(frame) : null,
      liveOrdinal: liveOrdinal,
      liveRingId: liveRingId,
    );
    _frames.add(positioned);
    _frameSynced.add(false);
    return positioned;
  }

  bool _isPendantFrame(WalFrame frame) =>
      frame.syncKey.bytes.length == 3 && _deviceId != null && _deviceId!.isNotEmpty && _deviceId != 'phone';

  int? _packetCounterOf(WalFrame frame) {
    final b = frame.syncKey.bytes;
    if (b.length < 2) return null;
    return b[0] | (b[1] << 8);
  }

  int? _fragmentIndexOf(WalFrame frame) {
    final b = frame.syncKey.bytes;
    return b.length == 3 ? b[2] : null;
  }

  static const _maxPendantBufferedFrames = 2000;
  int _pendantDroppedWhileBlocked = 0;

  final Set<String> _confirmedDurableWalKeys = {};

  bool _pendantBlockedByStorage = false;

  final Set<String> _liveProofPendingWalIds = {};

  bool _isPendantWal(Wal wal) =>
      _deviceId != null && _deviceId!.isNotEmpty && _deviceId != 'phone' && wal.device == _deviceId;

  int _countPendantBuffered() {
    var count = _frames.where(_isPendantFrame).length;
    for (final wal in _wals) {
      if (wal.storage == WalStorage.mem && _isPendantWal(wal)) {
        count += wal.totalFrames;
      }
    }
    return count;
  }

  @override
  void markFrameSynced(FrameSyncKey key) {
    for (int i = _frames.length - 1; i >= 0; i--) {
      if (_frames[i].syncKey == key) {
        _frameSynced[i] = true;
        break;
      }
    }
  }

  void _clearRecoveryMarkers(List<Wal> accepted, int generation) {
    if (!_isCurrent(generation)) return;
    final marked = accepted.where((wal) => wal.keptForTranscriptRecovery).toList();
    if (marked.isEmpty) return;
    for (final wal in marked) {
      wal.keptForTranscriptRecovery = false;
    }
    _emitWalTranscriptCoverage(generation: generation, phase: 'upload', kept: marked);
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) =>
      _syncAll(progress: progress, liveCaptureOnly: false);

  Future<SyncLocalFilesResponse?> syncLiveCaptureOnly({IWalSyncProgressListener? progress}) =>
      _syncAll(progress: progress, liveCaptureOnly: true);

  Future<SyncLocalFilesResponse?> _syncAll({IWalSyncProgressListener? progress, required bool liveCaptureOnly}) async {
    final generation = _sessionGeneration;
    await _enqueueBuffer(() => _flush(generation));
    if (!_isCurrent(generation)) return null;
    _isCancelled = false;
    _accumulatedResponse = null;

    final initialNowSeconds = _now().millisecondsSinceEpoch ~/ 1000;
    var wals = _wals
        .where((wal) => isAutoUploadEligible(wal) && (!liveCaptureOnly || isLiveCaptureWal(wal, initialNowSeconds)))
        .toList();
    if (wals.isEmpty) {
      Logger.debug("All synced!");
      DebugLogManager.logInfo('Local upload: no files to sync');
      // No pending work does not mean no retention work: expired synced
      // copies must still age out even when every WAL is already synced.
      try {
        await _removeExpiredSyncedCopies();
      } catch (e) {
        Logger.warning('Synced-copy retention sweep failed: $e');
      }
      return null;
    }

    if (SyncRateLimiter.instance.isLimited) {
      Logger.debug('Local upload: rate-limited until ${SyncRateLimiter.instance.until}, skipping');
      DebugLogManager.logEvent('local_upload_rate_limited', {'until': '${SyncRateLimiter.instance.until}'});
      return null;
    }

    DebugLogManager.logEvent('local_upload_started', {'walCount': wals.length});

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    _accumulatedResponse = resp;

    int batchesCompleted = 0;
    int batchesFailed = 0;
    int corruptedCount = 0;
    final totalFilesToUpload = wals.length;

    final attemptedWalIds = <String>{};
    String walAttemptKey(Wal wal) => captureEvidenceWalClaimable(wal) ? _durableKey(wal) : wal.id;
    // A conversation whose first batch uploaded unclaimed stays unclaimable for
    // the rest of the drain: the manifest is immutable per conversation, so a
    // later remainder must not claim one covering only part of it.
    final unclaimableConversationIds = <String>{};
    while (true) {
      // Re-snapshot between batches so a newly captured WAL can preempt an
      // hours-long historical drain without waiting for the original list.
      final batchNowSeconds = _now().millisecondsSinceEpoch ~/ 1000;
      final candidates =
          _wals.where((wal) => isAutoUploadEligible(wal) && !attemptedWalIds.contains(walAttemptKey(wal))).toList();
      final pending = candidates.where((wal) => !liveCaptureOnly || isLiveCaptureWal(wal, batchNowSeconds)).toList();
      if (pending.isEmpty) break;
      final batch = nextSyncUploadBatch(pending, batchNowSeconds);
      if (batch.isEmpty) break;
      attemptedWalIds.addAll(batch.map(walAttemptKey));
      final batchConversationId = batch.first.conversationId;
      final claimLiveCapture = !unclaimableConversationIds.contains(batchConversationId) &&
          canClaimLiveCapture(
            batch,
            candidates.where((wal) => wal.conversationId == batchConversationId).toList(),
            batchNowSeconds,
          );
      if (!claimLiveCapture && batchConversationId != null) {
        unclaimableConversationIds.add(batchConversationId);
      }
      if (_isCancelled) {
        Logger.debug("LocalWalSync: Upload cancelled");
        DebugLogManager.logWarning('Local upload cancelled', {
          'batchesUploaded': batchesCompleted,
          'batchesFailed': batchesFailed,
          'walsRemaining': wals.where((w) => w.status == WalStatus.miss).length,
        });
        // Clear the transient syncing flag on WALs not yet uploaded. Do NOT
        // touch status: any WAL already marked `uploaded` is safe on the
        // server and the reconciler will finish it — reverting it here would
        // cause a needless re-upload.
        for (final w in wals) {
          if (w.status != WalStatus.uploaded) {
            w.isSyncing = false;
            w.syncStartedAt = null;
            w.syncEtaSeconds = null;
          }
        }
        await _saveWalsToFile(generation);
        _notifyUpdated(generation);
        break;
      }
      List<File> files = [];
      List<Wal> batchWals = [];
      for (final wal in batch) {
        Logger.debug("sync id ${wal.id} ${wal.timerStart}");
        if (wal.filePath == null) {
          Logger.debug("file path is not found. wal id ${wal.id}");
          wal.markCorrupted();
          corruptedCount++;
          DebugLogManager.logWarning('WAL corrupted: file path missing', {'walId': wal.id});
          continue;
        }

        final fullPath = await Wal.getFilePath(wal.filePath);
        Logger.debug("sync wal: ${wal.id} file: $fullPath");

        try {
          if (fullPath == null) {
            Logger.debug("could not construct file path for wal id ${wal.id}");
            wal.markCorrupted();
            corruptedCount++;
            DebugLogManager.logWarning('WAL corrupted: cannot construct path', {'walId': wal.id});
            continue;
          }

          File file = File(fullPath);
          if (!file.existsSync()) {
            Logger.debug("file $fullPath does not exist");
            wal.markCorrupted();
            corruptedCount++;
            DebugLogManager.logWarning('WAL corrupted: file not found on disk', {
              'walId': wal.id,
              'filePath': wal.filePath ?? '',
            });
            continue;
          }
          files.add(file);
          wal.isSyncing = true;
          batchWals.add(wal);
        } catch (e) {
          wal.markCorrupted();
          corruptedCount++;
          Logger.debug(e.toString());
          DebugLogManager.logError(e, null, 'WAL corrupted: unexpected error - ${e.toString()}', {'walId': wal.id});
        }
      }

      if (files.isEmpty) {
        Logger.debug("Files are empty");
        continue;
      }

      void reportUploadProgress() {
        if (!_isCurrent(generation)) return;
        final done = wals.where((w) => w.status == WalStatus.uploaded || w.status == WalStatus.synced).length;
        progress?.onWalSyncedProgress(
          totalFilesToUpload > 0 ? done / totalFilesToUpload : 0.0,
          phase: SyncPhase.uploadingToCloud,
          currentFile: done,
          totalFiles: totalFilesToUpload,
        );
      }

      reportUploadProgress();

      _notifyUpdated(generation);
      try {
        // Upload only — return as soon as the server acknowledges. We do NOT
        // wait for server-side processing here; the reconciler resolves the
        // job_id later. Only WALs that actually became files (batchWals) are
        // mutated — corrupted ones already short-circuited above.
        final audioBounds = syncUploadAudioBounds(batchWals);
        final result = await _uploadGate.upload(
          files,
          conversationId: batchWals.first.conversationId,
          captureEvidence: captureEvidenceUploadHeader(batchWals, files),
          recordingSessionId: batchWals.first.recordingSessionId,
          audioStartSeconds: audioBounds.start,
          audioEndSeconds: audioBounds.end,
          claimLiveCapture: claimLiveCapture,
          geolocation: batchWals.first.geolocation,
        );

        if (result.completed != null) {
          // 200 fast-path: server processed synchronously and returned a result.
          final r = result.completed!;
          final nowSeconds = _now().millisecondsSinceEpoch ~/ 1000;
          resp.newConversationIds.addAll(r.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
          resp.updatedConversationIds.addAll(
            r.updatedConversationIds.where(
              (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
            ),
          );
          for (final wal in batchWals) {
            wal.status = WalStatus.synced;
            wal.isSyncing = false;
            wal.syncStartedAt = null;
            wal.syncEtaSeconds = null;
            if (wal.syncedAt == 0) wal.syncedAt = nowSeconds;
            if (_isCurrent(generation)) listener.onWalSynced(wal);
          }
        } else {
          // 202: audio safely received; processing in the background. Stamp the
          // shared job_id and mark uploaded. The reconciler resolves this to
          // synced / miss(retry) / corrupted out of the critical path. The
          // local file is retained until confirmed synced.
          final now = _now().millisecondsSinceEpoch ~/ 1000;
          for (final wal in batchWals) {
            wal.status = WalStatus.uploaded;
            wal.jobId = result.jobId;
            wal.uploadedAt = now;
            wal.isSyncing = false;
            wal.syncStartedAt = null;
            wal.syncEtaSeconds = null;
          }
          _notifyUpdated(generation);
        }

        _clearRecoveryMarkers(batchWals, generation);
        batchesCompleted++;
        reportUploadProgress();
      } on SyncRateLimitedException {
        // The cooldown is account-global, so every remaining batch would hit it too.
        DebugLogManager.logEvent('local_upload_rate_limited', {'until': '${SyncRateLimiter.instance.until}'});
        for (final wal in batchWals) {
          wal.isSyncing = false;
          wal.syncStartedAt = null;
          wal.syncEtaSeconds = null;
        }
        await _saveWalsToFile(generation);
        _notifyUpdated(generation);
        break;
      } on SyncOfflineQueueQuarantinedException {
        // Cutover fence: leave WALs retryable and skip quietly until control allows drain.
        DebugLogManager.logEvent('local_upload_cutover_quarantined', {
          'batchWalIds': batchWals.map((w) => w.id).toList(),
        });
        for (final wal in batchWals) {
          wal.isSyncing = false;
          wal.syncStartedAt = null;
          wal.syncEtaSeconds = null;
        }
        await _saveWalsToFile(generation);
        _notifyUpdated(generation);
        break;
      } on SyncRecoveryWindowExceededException {
        // Clear the in-flight flag on the whole batch first: the members the
        // rejection does NOT prove too old stay `miss` and must not be left
        // rendering as an upload that never finishes.
        for (final wal in batchWals) {
          wal.isSyncing = false;
          wal.syncStartedAt = null;
          wal.syncEtaSeconds = null;
        }
        final retired = _retireOutsideRecoveryWindow(batchWals);
        DebugLogManager.logEvent('local_upload_outside_recovery_window', {
          'batchWalIds': batchWals.map((w) => w.id).toList(),
          'retiredWalIds': retired.map((w) => w.id).toList(),
        });
        await _saveWalsToFile(generation);
        _notifyUpdated(generation);
        continue;
      } on SyncUploadHttpException catch (e) {
        batchesFailed++;
        final definitive = isDefinitiveUploadRefusal(e);
        if (definitive) {
          for (final wal in batchWals) {
            wal.markUploadRejected();
          }
          resp.localUploadPermanentFailures += batchWals.length;
          resp.localUploadPermanentError = e.toString();
          DebugLogManager.logEvent('local_upload_terminal_http_refusal', {
            'statusCode': e.statusCode,
            'walCount': batchWals.length,
          });
        } else {
          for (final wal in batchWals) {
            wal.isSyncing = false;
            wal.syncStartedAt = null;
            wal.syncEtaSeconds = null;
          }
        }
        DebugLogManager.logError(e, null, 'Local upload HTTP failure: ${e.toString()}', {
          'batchIndex': batchesCompleted + batchesFailed,
          'filesInBatch': files.length,
          'statusCode': e.statusCode,
          'terminal': definitive,
        });
      } catch (e) {
        print('Local WAL upload batch failed: $e, continuing with remaining files');
        batchesFailed++;
        if (!isTransientNetworkError(e)) {
          resp.localUploadPermanentFailures++;
          resp.localUploadPermanentError = e.toString();
        }
        DebugLogManager.logError(e, null, 'Local upload batch failed: ${e.toString()}', {
          'batchIndex': batchesCompleted + batchesFailed,
          'filesInBatch': files.length,
          'transient': isTransientNetworkError(e),
        });
        // Upload failed: clear the transient flag, leave status `miss` so the
        // batch is retried on the next sync.
        for (final wal in batchWals) {
          wal.isSyncing = false;
          wal.syncStartedAt = null;
          wal.syncEtaSeconds = null;
        }
      }

      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
    }

    DebugLogManager.logEvent('local_upload_finished', {
      'batchesUploaded': batchesCompleted,
      'batchesFailed': batchesFailed,
      'permanentFailures': resp.localUploadPermanentFailures,
      'corrupted': corruptedCount,
      'newConversations': resp.newConversationIds.length,
      'updatedConversations': resp.updatedConversationIds.length,
    });

    resp.localUploadFailures = batchesFailed;
    if (_isCurrent(generation)) progress?.onWalSyncedProgress(1.0);

    // Uploads just confirmed; sweep expired synced copies now so auto-removal
    // keeps pace with syncing instead of waiting for the next app start.
    try {
      await _removeExpiredSyncedCopies();
    } catch (e) {
      Logger.debug('synced-copy auto-remove sweep failed: $e');
    }
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    final generation = _sessionGeneration;
    await _enqueueBuffer(() => _flush(generation));
    if (!_isCurrent(generation)) return null;

    final matches = _wals.where((w) => w == wal).toList();
    if (matches.isEmpty) {
      DebugLogManager.logInfo('Single WAL upload skipped — WAL no longer tracked', {'walId': wal.id});
      return null;
    }
    final walToSync = matches.first;
    // A deliberate single-recording retry is a fresh start, so it restores the
    // auto-upload budget a previous failure spent. It costs at most one extra
    // upload for a permanently refused recording: the reconciler spends the
    // whole budget again on the same verdict.
    walToSync.retryCount = 0;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    DebugLogManager.logInfo('Single WAL upload started', {
      'walId': wal.id,
      'seconds': wal.seconds,
      'codec': wal.codec.toString(),
    });

    File? walFile;
    if (wal.filePath == null) {
      Logger.debug("file path is not found. wal id ${wal.id}");
      wal.markCorrupted();
      DebugLogManager.logWarning('Single WAL corrupted: file path missing', {'walId': wal.id});
    } else {
      try {
        final fullPath = await Wal.getFilePath(wal.filePath);
        if (fullPath == null) {
          Logger.debug("could not construct file path for wal id ${wal.id}");
          wal.markCorrupted();
          DebugLogManager.logWarning('Single WAL corrupted: cannot construct path', {'walId': wal.id});
        } else {
          File file = File(fullPath);
          if (!file.existsSync()) {
            Logger.debug("file $fullPath does not exist");
            wal.markCorrupted();
            DebugLogManager.logWarning('Single WAL corrupted: file not found', {'walId': wal.id});
          } else {
            walFile = file;
            wal.isSyncing = true;
          }
        }
      } catch (e) {
        wal.markCorrupted();
        print(e.toString());
        DebugLogManager.logError(e, null, 'Single WAL corrupted: unexpected error - ${e.toString()}', {
          'walId': wal.id,
        });
      }
    }

    _notifyUpdated(generation);

    // File unusable — nothing to upload (avoids a LateInit crash on walFile).
    if (walFile == null) {
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
      return resp;
    }

    try {
      // Upload only — no poll-to-terminal. Reconciler resolves the job later.
      final claimLiveCapture = canClaimLiveCapture(
        [walToSync],
        _wals
            .where(
              (candidate) => candidate.status == WalStatus.miss && candidate.conversationId == walToSync.conversationId,
            )
            .toList(),
        _now().millisecondsSinceEpoch ~/ 1000,
      );
      final audioBounds = syncUploadAudioBounds([walToSync]);
      final result = await _uploadGate.upload(
        [walFile],
        conversationId: walToSync.conversationId,
        captureEvidence: captureEvidenceUploadHeader([walToSync], [walFile]),
        recordingSessionId: walToSync.recordingSessionId,
        audioStartSeconds: audioBounds.start,
        audioEndSeconds: audioBounds.end,
        claimLiveCapture: claimLiveCapture,
        geolocation: walToSync.geolocation,
      );

      if (result.completed != null) {
        final r = result.completed!;
        resp.newConversationIds.addAll(r.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
        resp.updatedConversationIds.addAll(
          r.updatedConversationIds.where(
            (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
          ),
        );
        walToSync.status = WalStatus.synced;
        walToSync.isSyncing = false;
        walToSync.syncStartedAt = null;
        walToSync.syncEtaSeconds = null;
        if (walToSync.syncedAt == 0) {
          walToSync.syncedAt = _now().millisecondsSinceEpoch ~/ 1000;
        }
        DebugLogManager.logInfo('Single WAL upload succeeded (fast-path)', {'walId': wal.id});
        if (_isCurrent(generation)) listener.onWalSynced(wal);
      } else {
        final now = _now().millisecondsSinceEpoch ~/ 1000;
        walToSync.status = WalStatus.uploaded;
        walToSync.jobId = result.jobId;
        walToSync.uploadedAt = now;
        walToSync.isSyncing = false;
        walToSync.syncStartedAt = null;
        walToSync.syncEtaSeconds = null;
        DebugLogManager.logInfo('Single WAL uploaded; reconciler will finish', {'walId': wal.id});
        _notifyUpdated(generation);
      }
    } on SyncRateLimitedException {
      // Account-level rate limit — leave the WAL pending without consuming its
      // retry budget. The global upload gate owns the cooldown.
      DebugLogManager.logEvent('single_wal_rate_limited', {'walId': wal.id});
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
      return resp;
    } on SyncOfflineQueueQuarantinedException {
      DebugLogManager.logEvent('single_wal_cutover_quarantined', {'walId': wal.id});
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
      return resp;
    } on SyncRecoveryWindowExceededException {
      // Terminal: older than the server's automatic-recovery window. A manual
      // retry cannot succeed either, so stop presenting it as retryable work.
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      final retired = _retireOutsideRecoveryWindow([walToSync]);
      DebugLogManager.logEvent('single_wal_outside_recovery_window', {
        'walId': wal.id,
        'retiredWalIds': retired.map((w) => w.id).toList(),
      });
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
      return resp;
    } on SyncUploadHttpException catch (e) {
      if (isDefinitiveUploadRefusal(e)) {
        walToSync.markUploadRejected();
        resp.localUploadFailures = 1;
        resp.localUploadPermanentFailures = 1;
        resp.localUploadPermanentError = e.toString();
        DebugLogManager.logEvent('single_wal_terminal_http_refusal', {'walId': wal.id, 'statusCode': e.statusCode});
        await _saveWalsToFile(generation);
        _notifyUpdated(generation);
        return resp;
      }
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      rethrow;
    } catch (e) {
      Logger.debug('Single WAL upload failed: $e');
      DebugLogManager.logError(e, null, 'Single WAL upload failed: ${e.toString()}', {'walId': wal.id});
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      rethrow;
    }

    _clearRecoveryMarkers([walToSync], generation);
    await _saveWalsToFile(generation);
    _notifyUpdated(generation);

    if (_isCurrent(generation)) progress?.onWalSyncedProgress(1.0);
    return resp;
  }

  /// Retires the recordings a `backfill_lookback_exceeded` rejection proves the
  /// server will never accept, and only those.
  ///
  /// The backend decides the lookback from the OLDEST capture in the upload
  /// (`classify_sync_lane` measures `now - oldest_capture_at`), so a rejection
  /// only proves that one recording is outside the window — a batch mixes ages,
  /// and retiring all of it would strand recordings the server would still take.
  /// Everything captured no later than the proven-too-old one is necessarily
  /// outside the window as well, so the whole tail retires in one pass instead
  /// of costing another doomed upload per recording. The rest of the batch stays
  /// `miss` and re-forms into a batch without the poison on the next drain.
  List<Wal> _retireOutsideRecoveryWindow(List<Wal> rejectedBatch) {
    if (rejectedBatch.isEmpty) return const [];
    final provenTooOld = rejectedBatch.map((w) => w.timerStart).reduce(min);
    final retired = _wals
        .where((w) => w.status == WalStatus.miss && w.storage == WalStorage.disk && w.timerStart <= provenTooOld)
        .toList();
    for (final wal in retired) {
      wal.markOutsideRecoveryWindow();
    }
    return retired;
  }

  Future<bool> _localFileExists(Wal wal) async {
    if (wal.filePath == null) return false;
    final p = await Wal.getFilePath(wal.filePath);
    if (p == null) return false;
    return File(p).existsSync();
  }

  /// Resolve WALs sitting in [WalStatus.uploaded] by polling their server job
  /// — out of the upload critical path. Returns the new/updated conversation
  /// ids from jobs that reached a terminal state this pass so the caller can
  /// surface them to the UI.
  ///
  /// Idempotent and safe to run repeatedly and concurrently with an upload:
  /// it only touches `uploaded` WALs, and the upload loop only ever touches
  /// `miss` WALs, so the two never contend for the same recording. WALs are
  /// grouped by their shared `jobId` (batched upload → one job : N WALs).
  Future<SyncLocalFilesResponse> reconcileUploadedWals() async {
    final generation = _sessionGeneration;
    final resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    final byJob = <String, List<Wal>>{};
    for (final w in _wals) {
      if (w.status == WalStatus.uploaded && w.jobId != null && w.jobId!.isNotEmpty) {
        byJob.putIfAbsent(w.jobId!, () => []).add(w);
      }
    }
    if (byJob.isEmpty) return resp;

    bool changed = false;
    final nowSecs = _now().millisecondsSinceEpoch ~/ 1000;
    const maxConcurrent = 3;
    final entries = byJob.entries.toList();

    for (var i = 0; i < entries.length; i += maxConcurrent) {
      final slice = entries.sublist(i, min(i + maxConcurrent, entries.length));
      final fetched = await Future.wait(slice.map((e) async => (e.value, await _jobStatusFetcher(e.key))));

      for (final (members, fetch) in fetched) {
        final jobId = members.first.jobId;
        final memberWalIds = members.map((w) => w.id).toList();
        switch (fetch.outcome) {
          case SyncJobFetchOutcome.transient:
            // Network/5xx — leave as `uploaded`, retry on the next pass.
            DebugLogManager.logEvent('reconcile_poll', {
              'jobId': jobId,
              'memberWalIds': memberWalIds,
              'outcome': 'transient',
            });
            break;
          case SyncJobFetchOutcome.notFound:
            // Job expired or unknown. Recover from the retained local file.
            for (final w in members) {
              changed = true;
              final hadJob = w.jobId;
              w.jobId = null;
              final fileExists = await _localFileExists(w);
              if (fileExists) {
                w.status = WalStatus.miss; // re-upload next sync (dedup-safe)
                w.retryCount += 1;
                w.lastRetryAt = nowSecs;
              } else {
                w.markCorrupted(); // nothing left to recover
              }
              DebugLogManager.logEvent('reconcile_revert', {
                'walId': w.id,
                'jobId': hadJob,
                'outcome': 'not_found',
                'fileExists': fileExists,
                'newStatus': w.status.name,
                'retryCount': w.retryCount,
              });
            }
            break;
          case SyncJobFetchOutcome.ok:
            final s = fetch.status!;
            final terminalPolicy = syncJobTerminalPolicy(status: s.status, isTerminal: s.isTerminal);
            if (terminalPolicy == SyncJobTerminalPolicy.wait) {
              DebugLogManager.logEvent('reconcile_poll', {
                'jobId': jobId,
                'memberWalIds': memberWalIds,
                'outcome': 'non_terminal',
                'serverStatus': s.status,
                'processedSegments': s.processedSegments,
                'totalSegments': s.totalSegments,
              });
              break; // still queued/processing — check later
            }
            if (s.result != null) {
              resp.newConversationIds.addAll(
                s.result!.newConversationIds.where((id) => !resp.newConversationIds.contains(id)),
              );
              resp.updatedConversationIds.addAll(
                s.result!.updatedConversationIds.where(
                  (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
                ),
              );
            }
            if (terminalPolicy == SyncJobTerminalPolicy.acknowledge) {
              DebugLogManager.logEvent('reconcile_poll', {
                'jobId': jobId,
                'memberWalIds': memberWalIds,
                'outcome': 'completed',
                'newConversations': s.result?.newConversationIds.length ?? 0,
                'updatedConversations': s.result?.updatedConversationIds.length ?? 0,
              });
              for (final w in members) {
                changed = true;
                w.status = WalStatus.synced;
                w.jobId = null;
                if (w.syncedAt == 0) w.syncedAt = _now().millisecondsSinceEpoch ~/ 1000;
                if (_isCurrent(generation)) listener.onWalSynced(w);
              }
            } else {
              // status='failed' with totalSegments==0 can only come from the
              // backend stale guard (mark_job_completed only sets 'failed'
              // when total>0). String hint is a fallback if the structural
              // signal ever becomes ambiguous.
              final capacityLimited = syncJobIsBackendBusy(s) || isPacedBackfillReasonCode(s.reasonCode);
              if (capacityLimited) {
                SyncRateLimiter.instance.markLimited(
                  retryAfterSeconds: s.retryAfter ?? 600,
                  reason: RateLimitReason.backendBusy,
                );
              }
              // A verdict the audio itself caused cannot change on the next pass,
              // and it cannot change for a manual retry either — the bytes are the
              // same. Spending the auto budget only made the row read "Failed — tap
              // Retry" forever: every tap re-uploaded, re-earned the same verdict,
              // and re-spent the budget, with the needs-attention banner never
              // clearing. Retire it to a terminal state instead, the way an
              // out-of-window rejection already does. The file stays on disk.
              final permanentInput = !capacityLimited && syncJobFailureIsPermanent(s);
              for (final w in members) {
                changed = true;
                final hadJob = w.jobId;
                if (permanentInput) {
                  w.markUnsupportedAudio();
                  w.lastRetryAt = nowSecs;
                } else {
                  w.status = WalStatus.miss;
                  w.jobId = null;
                  if (!capacityLimited) {
                    w.retryCount += 1;
                    w.lastRetryAt = nowSecs;
                  }
                }
                DebugLogManager.logEvent('reconcile_revert', {
                  'walId': w.id,
                  'jobId': hadJob,
                  'outcome': s.status,
                  'serverError': s.error,
                  'reasonCode': s.reasonCode,
                  'failedSegments': s.failedSegments,
                  'totalSegments': s.totalSegments,
                  'retryCount': w.retryCount,
                  'capacityLimited': capacityLimited,
                  'permanentInput': permanentInput,
                  'retryCountBumped': !capacityLimited,
                });
              }
            }
            break;
        }
      }
    }

    if (changed) {
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
    }
    return resp;
  }
}
