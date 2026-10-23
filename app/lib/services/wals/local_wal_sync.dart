import 'package:omi/services/capture/local_stt_custody.dart';
import 'dart:async';
import 'native_custody_diagnostics.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
import 'package:omi/services/wals/watch_live_coverage.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/capture/native_batch_geolocation.dart';
import 'dart:io';
import 'dart:math';

import 'package:disk_space_2/disk_space_2.dart';
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
import 'package:omi/services/wals/wal_frame_encoder.dart';
import 'package:omi/services/telemetry/client_telemetry.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/deleted_account_uids.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_job_policy.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/on_device/on_device_overflow_intake.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal_evidence_runs.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/wal_file_manager.dart';

import 'capture_committed_journal.dart';
import 'package:omi/backend/schema/capture_committed_event.dart';
import 'package:omi/services/experiments/client_refactor_flags.dart';

part 'capture_committed_custody.dart';
part 'on_device_prepared_upload.dart';
part 'wal_policy.dart';
part 'wal_job_reconciliation.dart';
part 'device_chunk_persistence.dart';
part 'wal_account_purge.dart';

class LocalWalSyncImpl with WidgetsBindingObserver implements LocalWalSync {
  /// A cheap view invalidation signal: unrelated live/device sync changes do
  /// not make Home walk the complete WAL index and stat its manual files.
  final ValueNotifier<int> heldRevision = ValueNotifier(0);
  final ValueNotifier<SyncLocalFilesResponse?> conversationCompletions = ValueNotifier(null);
  DeviceType? sourceDeviceType;
  Future<void> configureDeviceAudio(BleAudioCodec codec, String deviceId, BtDevice device) async {
    sourceDeviceType = device.type;
    await onAudioCodecChanged(codec, deviceInfo: (id: deviceId, model: device.modelNumber));
  }

  DeviceType? _bufferDeviceType;
  late final CaptureCommittedJournal captureCommits = CaptureCommittedJournal(getApplicationDocumentsDirectory);
  late final WatchLiveCoverage watchCoverage = WatchLiveCoverage(getApplicationDocumentsDirectory, now: _now);
  late final NativeRecordingIntake nativeIntake = NativeRecordingIntake(this, coverage: watchCoverage);
  Future<void> intakeNativeRecordings() async {
    await walReady;
    await intakeOnDeviceOverflow(this);
    await nativeIntake.scan();
  }

  /// A minute recovery receipt can arrive before the normal flush timer. Seal
  /// its live tail first, keeping the active session identity and capture route.
  Future<void> checkpointWatchAudio() {
    final generation = _sessionGeneration;
    return _enqueueBuffer(() async {
      if (!_isCurrent(generation) || _bufferDeviceType != DeviceType.appleWatch) return;
      await _finalizeCurrentSession(generation);
      await _flush(generation);
    });
  }

  void _onNativeRecordingFinalized(String _) => _runNativeIntake();
  void _runNativeIntake() {
    unawaited(intakeNativeRecordings().then((_) async {
      await RecordingTransferCoordinator.instance.wake(WakeTrigger.cooldownElapsed);
    }).catchError((e) {
      Logger.debug('Native recording intake deferred: $e');
    }));
  }

  List<Wal> _wals = [];

  bool _pendingPhoneOnly = false;
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
  BleAudioCodec get currentCodec => _codec;
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
    heldRevision.value++;
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
    conversationCompletions.value = null;
    _lastStaleWalReportAt = null;
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
    _pendingPhoneOnly = false;
    _frameSynced = [];
    _captureEvidenceRoot = null;
    _captureEvidenceGeneration++;
    _nextSourceFramePosition = 0;
    _sourceClockEpoch = 0;
    _admissionReservations.clear();
    _liveProofPendingWalIds.clear();
    _pendantBlockedByStorage = false;
    heldRevision.value++;
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
  final WalCoverageTelemetryEmitter? _staleWalTelemetry;
  DateTime? _lastStaleWalReportAt;
  final Future<int?> Function()? _freeDiskBytesOverride;
  final PendantRingCustody _custody;
  final Future<DeviceConnection?> Function(String deviceId)? _connectionResolver;

  DateTime _now() => _nowOverride?.call() ?? DateTime.now();

  Timer Function(Duration, void Function(Timer)) get _periodic => _periodicOverride ?? Timer.periodic;

  final SyncJobPoller? _jobPollerOverride;
  late final SyncJobPoller _jobPoller = _jobPollerOverride ??
      (_jobStatusFetcherOverride == null
          ? (SyncJobPoller.instance..persistMissingWith(PreferencesSyncJobMissingStore()))
          : SyncJobPoller(clock: _now));
  Future<SyncJobFetch> _jobStatusFetcher(String jobId) =>
      _jobPoller.fetch(jobId, _jobStatusFetcherOverride ?? fetchSyncJobStatus);
  Future<SyncLocalFilesResponse>? _reconcileInFlight;

  LocalWalSyncImpl(
    this.listener, {
    SyncUploadGate? uploadGate,
    SyncJobPoller? jobPoller,
    DateTime Function()? now,
    Timer Function(Duration, void Function(Timer))? periodic,
    Future<SyncJobFetch> Function(String jobId)? jobStatusFetcher,
    Future<void> Function(List<Wal> wals)? persistWals,
    Future<List<Wal>> Function()? loadWals,
    WalCoverageTelemetryEmitter? coverageTelemetry,
    WalCoverageTelemetryEmitter? staleWalTelemetry,
    Future<int?> Function()? freeDiskBytes,
    PendantRingCustody? custody,
    Future<DeviceConnection?> Function(String deviceId)? connectionResolver,
  })  : _jobPollerOverride = jobPoller,
        _uploadGateOverride = uploadGate,
        _nowOverride = now,
        _periodicOverride = periodic,
        _jobStatusFetcherOverride = jobStatusFetcher,
        _persistWalsOverride = persistWals,
        _loadWalsOverride = loadWals,
        _coverageTelemetryOverride = coverageTelemetry,
        _staleWalTelemetry = staleWalTelemetry,
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
    wal.repairLegacyImportedCustody();
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
    if (_walAdmittedAtLoad(wal)) {
      _wals.add(wal);
    } else {
      _foreignWals.add(wal);
    }
    final reservedBytes = await _walFileLength(wal);
    if (reservedBytes != null) _consumeAdmission(reservedBytes);
    await _evaluateRetentionPressure();
    await _saveWalsToFile(admittedGeneration);
    _notifyUpdated(admittedGeneration);
    if (_isCurrent(admittedGeneration) && wal.holdForUser && _wals.contains(wal)) heldRevision.value++;
    Logger.debug("LocalWalSync: Added external WAL ${wal.id} (${wal.seconds}s)");
  }

  @override
  void start() {
    _initializeWals();
    BleBridge.instance.addBatchRecordingFinalizedListener(_onNativeRecordingFinalized);
    _runNativeIntake();
    _chunkingTimer = _periodic(const Duration(seconds: chunkSizeInSeconds + newFrameSyncDelaySeconds), (t) async {
      final generation = _sessionGeneration;
      await _enqueueBuffer(() async => _chunk(generation));
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
    if (state == AppLifecycleState.resumed) {
      _runNativeIntake();
      final generation = _sessionGeneration;
      unawaited(_reportStaleWalsWhenReady(generation));
    }
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

  Future<void> _reportStaleWalsWhenReady(int generation) async {
    await _walReady.future;
    if (_isCurrent(generation)) reportStaleMissingWals(trigger: 'foreground');
  }

  /// Reports durable local backlog separately from retry attempts. Age starts
  /// at the WAL's end, so a long current recording cannot look stuck early.
  /// A successful upload of one file never hides another stale recording.
  void reportStaleMissingWals({required String trigger}) {
    final now = _now();
    final cutoff = now.subtract(const Duration(minutes: 15)).millisecondsSinceEpoch ~/ 1000;
    final stale = _wals
        .where(
          (w) =>
              !w.holdForUser &&
              w.status == WalStatus.miss &&
              w.storage == WalStorage.disk &&
              walAudioSeconds(w) > 0 &&
              w.timerStart > 0 &&
              w.timerStart + w.seconds <= cutoff,
        )
        .toList();
    if (stale.isEmpty) {
      _lastStaleWalReportAt = null;
      return;
    }
    if (_lastStaleWalReportAt != null && now.difference(_lastStaleWalReportAt!) < const Duration(minutes: 5)) return;
    _lastStaleWalReportAt = now;
    final oldestEnd = stale.map((w) => w.timerStart + w.seconds).reduce(min);
    final fields = <String, Object?>{
      'trigger': trigger,
      'pending_wal_count': stale.length,
      'pending_audio_seconds': stale.fold<double>(0.0, (total, w) => total + walAudioSeconds(w)),
      'oldest_pending_age_seconds': now.millisecondsSinceEpoch ~/ 1000 - oldestEnd,
      'exhausted_retry_count': stale.where((w) => w.retryCount >= walMaxAutoRetries).length,
    };
    try {
      if (_staleWalTelemetry != null) {
        _staleWalTelemetry!(fields);
      } else {
        DebugLogManager.logEvent('wal_stale_missing', fields);
        AnalyticsManager().track('Local WAL Stuck', properties: fields);
      }
    } catch (_) {
      // Reporting cannot change custody or prevent retry.
    }
  }

  /// Headless transcription loads custody without starting cloud-audio timers or migrations.
  Future<void> loadForOnDeviceWorker() async {
    final generation = _sessionGeneration;
    await WalFileManager.init();
    final loaded = await WalFileManager.loadWals();
    if (!_isCurrent(generation)) return;
    _admitLoadedWals(loaded);
    if (!_walReady.isCompleted) _walReady.complete();
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
    if (!await _purgeDeletedAccountWalsAtLoad(generation)) return;

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
    if (_isCurrent(generation)) reportStaleMissingWals(trigger: 'startup');
    _notifyUpdated(generation);
  }

  @override
  Future stop() async {
    final generation = _sessionGeneration;
    BleBridge.instance.removeBatchRecordingFinalizedListener(_onNativeRecordingFinalized);
    _chunkingTimer?.cancel();
    _flushingTimer?.cancel();
    _pendantTimer?.cancel();
    try {
      WidgetsBinding.instance.removeObserver(this);
    } catch (_) {}

    await _drainPendantTail(generation);
    await _enqueueBuffer(() async => _chunk(generation));
    await _enqueueBuffer(() => _flush(generation));

    _frames = [];
    _pendingPhoneOnly = false;
    _frameSynced = [];
  }

  @override
  Future onAudioCodecChanged(BleAudioCodec codec, {({String id, String model})? deviceInfo}) async {
    final generation = _sessionGeneration;
    await _enqueueBuffer(() async {
      if (!_isCurrent(generation)) return;
      // Seal the old pendant tail and advance the boundary without yielding.
      // Native BLE can deliver orphan frames during the fsync below, even on
      // a same-codec reconnect. Those must stay in the new buffer.
      _sealPendantTail(generation);
      _chunk(generation);
      _frames = [];
      _pendingPhoneOnly = false;
      _frameSynced = [];
      _bufferDeviceType = sourceDeviceType;
      if (deviceInfo != null) setDeviceInfo(deviceInfo.id, deviceInfo.model);
      _framesPerSecond = codec.getFramesPerSecond();
      _codec = codec;
      _sourceClockEpoch++;
      _nextSourceFramePosition = 0;
      _captureEvidenceGeneration++;
      await _flush(generation);
    });
  }

  @override
  void setDeviceInfo(String? deviceId, String? deviceModel) {
    if (deviceId == 'phone-mic') sourceDeviceType = null;
    _bufferDeviceType = sourceDeviceType;
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

  void _chunk(int generation) {
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

    if (partitionsEvidenceRuns(true, _codec, evidenceFrames)) {
      _storeSelectedRuns(
        evidenceFrames,
        _frameSynced.sublist(low, high),
        captureSelectionStartSeconds(
          now.subtract(const Duration(seconds: newFrameSyncDelaySeconds)),
          chunkFrameCount,
          _framesPerSecond,
        ),
        generation,
        extendMemWal: true,
        legacySelectionTimerStart: timerStart,
      );
    } else {
      final live = _liveEvidenceFor(evidenceFrames);

      bool shouldStored =
          _bufferDeviceType == DeviceType.appleWatch || SharedPreferencesUtil().unlimitedLocalStorageEnabled;
      if (!shouldStored) {
        shouldStored = _frameSynced.sublist(low, high).any((synced) => !synced);
      }

      if (shouldStored) {
        final syncedOffset = syncedPrefixCount(_frameSynced.sublist(low, high));
        Logger.debug("$low - $high - $syncedOffset - $chunkFrameCount - $_framesPerSecond");

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
            onDeviceOnly: _pendingPhoneOnly,
            capturedOnDeviceOnly: _pendingPhoneOnly,
            status: syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss,
            device: _deviceId ?? "omi",
            deviceModel: _deviceModel ?? "Omi",
            deviceType: _bufferDeviceType,
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
      final shouldStored = _bufferDeviceType == DeviceType.appleWatch ||
          SharedPreferencesUtil().unlimitedLocalStorageEnabled ||
          runSynced.any((synced) => !synced);
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
          onDeviceOnly: _pendingPhoneOnly,
          capturedOnDeviceOnly: _pendingPhoneOnly,
          status: syncedOffset == frameCount ? WalStatus.synced : WalStatus.miss,
          device: _deviceId ?? "omi",
          deviceModel: _deviceModel ?? "Omi",
          deviceType: _bufferDeviceType,
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
        if (_sealPendantTail(generation)) await _flush(generation);
      });

  /// Move the complete pendant tail into WAL custody before any I/O yields.
  bool _sealPendantTail(int generation) {
    if (!_isCurrent(generation)) return false;
    final indices = <int>[];
    for (var i = 0; i < _frames.length; i++) {
      if (_isPendantFrame(_frames[i])) indices.add(i);
    }
    if (indices.isEmpty) return false;
    final frames = indices.map((i) => _frames[i]).toList();
    final synced = indices.map((i) => _frameSynced[i]).toList();

    var shouldStore = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    if (!shouldStore) shouldStore = synced.any((s) => !s);
    if (!shouldStore) {
      _removeFrameIndices(indices);
      return false;
    }
    final syncedOffset = syncedPrefixCount(synced);

    final frameCount = frames.length;
    final now = _now();
    var timerEnd = now.millisecondsSinceEpoch ~/ 1000;
    var timerStart = timerEnd - frameCount ~/ _framesPerSecond;
    final evidence = stableCaptureEvidence(frames);
    final live = _liveEvidenceFor(frames);

    if (partitionsEvidenceRuns(true, _codec, frames)) {
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
        onDeviceOnly: _pendingPhoneOnly,
        capturedOnDeviceOnly: _pendingPhoneOnly,
        status: syncedOffset == frameCount ? WalStatus.synced : WalStatus.miss,
        device: _deviceId ?? "omi",
        deviceModel: _deviceModel ?? "Omi",
        deviceType: _bufferDeviceType,
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
    return true;
  }

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
        // A policy edge may share a partially filled chunk with previously sent
        // frames. Conservatively retain the whole chunk; never upload its local tail.
        // Custody was latched when these frames were captured.
        final fileName = await _uniqueStorageFileName(wal);
        String? filePath = await Wal.getFilePath(fileName);
        if (filePath == null) {
          DebugLogManager.logError('LocalWalSync flush error: Flush failed: cannot get file path', null, null, {
            'walId': wal.id,
            'timerStart': wal.timerStart,
          });
          throw Exception('Flushing to storage failed. Cannot get file path.');
        }

        final data = _isPendantWal(wal) ? encodeWalFrames(wal.data) : encodeLegacyWalFrames(wal.data);
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

    await _persistCaptureCommits(generation, onlyIfReleased: true);
    await _evaluateRetentionPressure();
    final indexSaved = await _saveWalsToFile(generation);
    if (indexSaved && flushedCount > 0) _pendantBlockedByStorage = false;

    if (indexSaved) {
      for (final wal in durableWals) {
        if (wal.deviceType == DeviceType.appleWatch && wal.ownerUid != null && _isCurrent(generation)) {
          try {
            await watchCoverage.record(wal.ownerUid!, wal.timerStart.toDouble(),
                wal.timerStart + wal.totalFrames * wal.frameSize / wal.sampleRate,
                serverReachable: watchWalWillReachServer(wal));
          } catch (e) {
            Logger.debug('Watch coverage journal unavailable: $e');
          }
        }
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

  // Foreign-owner audio is another account's: it never counts as this account's pressure.
  int get _pendingDiskWalCount => [
        ..._retiredWals,
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

  @override
  Future<int> purgeAccountWals(String uid) => _purgeAccountWals(uid);

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

  String _uploadTelemetrySource(List<Wal> wals) => ClientTelemetry.uploadSourceForBatch([
        for (final wal in wals)
          (storage: wal.storage.name, originalStorage: wal.originalStorage?.name, device: wal.device),
      ]);

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
  }

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
            final sidecar = File(nativeBatchGeolocationSidecarPath(fullPath));
            if (await sidecar.exists()) await sidecar.delete();
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
    if (removed && wal.holdForUser && _isCurrent(generation)) heldRevision.value++;
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
    bool shouldStored =
        _bufferDeviceType == DeviceType.appleWatch || SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    if (!shouldStored) {
      shouldStored = _frameSynced.sublist(0, high).any((synced) => !synced);
    }

    if (shouldStored) {
      if (partitionsEvidenceRuns(true, _codec, evidenceFrames)) {
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
          onDeviceOnly: _pendingPhoneOnly,
          capturedOnDeviceOnly: _pendingPhoneOnly,
          status: syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss,
          device: _deviceId ?? "omi",
          deviceModel: _deviceModel ?? "Omi",
          deviceType: _bufferDeviceType,
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
    _pendingPhoneOnly = false;
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
      final unboundWatch =
          wal.deviceType == DeviceType.appleWatch && wal.status == WalStatus.synced && wal.syncedAt == 0;
      if ((wal.status != WalStatus.miss && !unboundWatch) || wal.conversationId != null) continue;
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
      if (await _saveWalsToFile(generation)) {
        try {
          await refreshWatchCoverage(watchCoverage);
        } catch (e) {
          Logger.debug('Watch journal promotion deferred: $e');
        }
      }
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
      if (wal.holdForUser ||
          wal.status != WalStatus.miss ||
          wal.storage != WalStorage.disk ||
          wal.retryCount < walMaxAutoRetries) {
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

  /// Commit result before publishing it; stale-account work cannot rewrite the index.
  Future<bool> persistOnDeviceConversation(Wal wal, Map<String, dynamic> conversation, int generation) async {
    if (!_isCurrent(generation) || !_wals.contains(wal) || !wal.onDeviceOnly) return false;
    wal.onDeviceConversation = conversation;
    wal.onDevicePreparedUpload = null;
    wal.conversationId = conversation['id'] as String?;
    await _saveWalsToFile(generation);
    _notifyUpdated(generation);
    return true;
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
    final pendingWals =
        _wals.where((w) => w.status == WalStatus.miss || (w.status == WalStatus.uploaded && w.syncedAt == 0)).toList();
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
    if (LocalSttCustody.keepsPhoneAudio || OnDeviceTranscriptionController.instance.shouldKeepAudioLocal) {
      _pendingPhoneOnly = true;
      for (final wal in _wals.where((w) => w.storage == WalStorage.mem)) {
        wal.onDeviceOnly = true;
        wal.capturedOnDeviceOnly = true;
      }
    }
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
    if (_pendingPhoneOnly || LocalSttCustody.keepsPhoneAudio) return;
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
          telemetrySource: _uploadTelemetrySource(batchWals),
        );

        _observeNativeUpload(batchWals);
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
          _jobPoller.defer(result.jobId!, result.pollAfterMs);
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
        Logger.debug('Local WAL upload batch failed: $e, continuing with remaining files');
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
    if (wal.isSyncing || wal.status == WalStatus.uploaded || wal.status == WalStatus.synced) return null;
    final held = wal.holdForUser;
    final generation = _sessionGeneration;
    wal.isSyncing = true;
    if (held) heldRevision.value++;
    try {
      return await _syncWal(wal: wal, progress: progress);
    } finally {
      wal.isSyncing = false;
      if (held && _isCurrent(generation)) heldRevision.value++;
    }
  }

  Future<SyncLocalFilesResponse?> _syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    if (wal.onDeviceOnly) return null;
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
        Logger.debug(e.toString());
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
        telemetrySource: _uploadTelemetrySource([walToSync]),
      );

      _observeNativeUpload([walToSync]);
      if (result.completed != null) {
        walToSync.holdForUser = false;
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
        _jobPoller.defer(result.jobId!, result.pollAfterMs);
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
      if (walToSync.holdForUser) rethrow;
      return resp;
    } on SyncOfflineQueueQuarantinedException {
      DebugLogManager.logEvent('single_wal_cutover_quarantined', {'walId': wal.id});
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
      if (walToSync.holdForUser) rethrow;
      return resp;
    } on SyncRecoveryWindowExceededException {
      // Terminal: older than the server's automatic-recovery window. A manual
      // retry cannot succeed either, so stop presenting it as retryable work.
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      walToSync.markOutsideRecoveryWindow();
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
      walToSync.retryCount++;
      Logger.debug('Single WAL upload failed: $e');
      DebugLogManager.logError(e, null, 'Single WAL upload failed: ${e.toString()}', {'walId': wal.id});
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
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
        .where((w) =>
            !w.holdForUser &&
            w.status == WalStatus.miss &&
            w.storage == WalStorage.disk &&
            w.timerStart <= provenTooOld)
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
  Future<SyncLocalFilesResponse> reconcileUploadedWals() {
    final active = _reconcileInFlight;
    if (active != null) return active;
    if (!_jobPoller.beginPass()) {
      return Future.value(SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []));
    }
    final pass = _reconcileUploadedWals();
    _reconcileInFlight = pass;
    return pass.whenComplete(() {
      if (identical(_reconcileInFlight, pass)) _reconcileInFlight = null;
      _jobPoller.endPass();
    });
  }

  /// A row read before an await may have changed by the time the pass writes
  /// it: an upload may have claimed it under a new job, retention may have
  /// released it, or another path may have finished it. Only a row this sync
  /// still owns, still `uploaded` under the same job handle (blank = none),
  /// may be moved.
  bool _stillUploadedUnder(Wal wal, String? jobId) =>
      wal.status == WalStatus.uploaded &&
      (wal.jobId?.trim() ?? '') == (jobId?.trim() ?? '') &&
      _wals.any((w) => identical(w, wal));
}
