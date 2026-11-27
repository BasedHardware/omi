import 'dart:async';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/ring_drain_policy.dart';
import 'package:omi/services/wals/sync_transfer_keep_alive.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';
import 'package:omi/services/wals/storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';

class WalSyncs implements IWalSync {
  late LocalWalSyncImpl _phoneSync;
  LocalWalSyncImpl get phone => _phoneSync;

  late SDCardWalSyncImpl _sdcardSync;
  SDCardWalSyncImpl get sdcard => _sdcardSync;

  late FlashPageWalSyncImpl _flashPageSync;
  FlashPageWalSyncImpl get flashPage => _flashPageSync;

  late StorageSyncImpl _storageSync;
  StorageSyncImpl get storage => _storageSync;

  late RingStorageSyncImpl _ringSync;
  RingStorageSyncImpl get ring => _ringSync;

  final IWalSyncListener listener;
  final SyncTransferKeepAlive _keepAlive;

  bool _isCancelled = false;
  BtDevice? _device;
  String? _firmwareVersion;
  static const _ringProbeInterval = Duration(seconds: 15);
  Future<bool>? _ringPass;
  Timer? _ringProbe;
  int _ringGeneration = 0;
  int? _ringPassGeneration;
  bool Function()? _shouldDrainRing;
  bool _independentDrainAllowed = true;
  bool _retryRingAfterSettlement = false;
  int _uploadCancellation = 0;
  int get uploadCancellation => _uploadCancellation;
  int get ringCancellation => _ringGeneration;
  bool _ringPausedByUser = false;

  bool get usesIndependentRingDrain =>
      ringDrainRecoveryEnabled &&
      _independentDrainAllowed &&
      _shouldDrainRing != null &&
      isRingBufferFirmware(_resolvedFirmware);

  /// SCA-4753 samples the same decision that routes the connected pendant.
  /// No cohort applies before policy is configured or for non-ring firmware.
  String? get drainCohort {
    if (_shouldDrainRing == null || !isRingBufferFirmware(_resolvedFirmware)) return null;
    return usesIndependentRingDrain ? 'on' : 'holdout';
  }

  void configureRingDrain(
    bool Function() shouldDrain, {
    bool independentDrainAllowed = true,
    void Function()? onDurableChunk,
  }) {
    _shouldDrainRing = shouldDrain;
    _independentDrainAllowed = independentDrainAllowed;
    _ringPausedByUser = false;
    ring.independentDiscovery = ringDrainRecoveryEnabled && independentDrainAllowed;
    ring.onDurableChunk = onDurableChunk;
    unawaited(wakeRingDrain());
  }

  void disableRingDrain() {
    _shouldDrainRing = null;
    ring.independentDiscovery = false;
    ring.onDurableChunk = null;
    _cancelRingDrain();
  }

  void _cancelRingDrain() {
    _ringGeneration++;
    _retryRingAfterSettlement = false;
    _ringProbe?.cancel();
    _ringProbe = null;
    ring.cancelSync();
  }

  /// Reports durable audio produced during this request, including a partial
  /// read, so the original manual sync can submit it after the last write.
  Future<bool> wakeManualRingDrain() async {
    final chunks = ring.durableChunkCount;
    await wakeRingDrain(manual: true);
    return ring.durableChunkCount != chunks;
  }

  Future<bool> wakeRingDrain({
    bool manual = false,
    String? deviceId,
    bool fromBle = false,
    bool discoveryOnly = false,
  }) {
    if (!usesIndependentRingDrain || _device == null || (_ringPass == null && ring.isSyncing)) {
      return Future.value(false);
    }
    if (deviceId != null && deviceId != _device!.id) return Future.value(false);
    if (fromBle && (_ringPausedByUser || _shouldDrainRing?.call() != true)) return Future.value(false);
    if (!fromBle && !discoveryOnly) _ringPausedByUser = false;
    final active = _ringPass;
    if (active != null) {
      final generation = _ringGeneration;
      if (manual) {
        // The active probe may have been discovery-only. Wait for it to
        // settle before taking the manual snapshot on the same connection.
        return active.then((_) async {
          if (generation != _ringGeneration) return false;
          return wakeRingDrain(manual: true);
        });
      }
      // Reconnect can arrive while STOP and writes are settling.
      if (!fromBle && !discoveryOnly && _ringPassGeneration != generation) {
        _retryRingAfterSettlement = true;
      }
      return active;
    }
    // Live marks/INFO can arrive several times per second, including in response
    // to our own commands. Let the scheduled probe cover those notifications.
    if (fromBle && _ringProbe != null) return Future.value(false);
    _ringProbe?.cancel();
    _ringProbe = null;
    final generation = _ringPassGeneration = _ringGeneration;
    final phoneGeneration = phone.sessionGeneration;
    bool current() => generation == _ringGeneration && phoneGeneration == phone.sessionGeneration;
    var completedRange = false;
    final pass = Future<bool>.microtask(() async {
      if (!current()) return false;
      await ring.refreshWalsFromDevice();
      if (!current() || discoveryOnly || !(manual || _shouldDrainRing?.call() == true)) return false;
      if ((await ring.getMissingWals()).isEmpty || !current()) return false;
      final release = await _keepAlive.acquireScoped();
      try {
        if (!current()) return false;
        DebugLogManager.logInfo('Sync Phase 0: Ring-buffer sync', {'fw': _resolvedFirmware ?? ''});
        await ring.syncAll();
        completedRange = current() && (await ring.getMissingWals()).isEmpty;
        return completedRange;
      } finally {
        await release();
      }
    }).catchError((Object error, StackTrace stack) {
      Logger.debug('WalSyncs: independent ring drain failed: $error');
      return false;
    });
    _ringPass = pass.whenComplete(() {
      _ringPass = null;
      final retry = _retryRingAfterSettlement;
      _retryRingAfterSettlement = false;
      if (retry) {
        unawaited(wakeRingDrain());
      } else if (current() && !_ringPausedByUser && _shouldDrainRing?.call() == true) {
        // Refresh immediately after a completed snapshot. Failed or empty
        // probes back off so a quiet or disk-constrained device stays quiet.
        _ringProbe = Timer(completedRange ? Duration.zero : _ringProbeInterval, () {
          _ringProbe = null;
          unawaited(wakeRingDrain());
        });
      }
    });
    return _ringPass!;
  }

  /// Called from DeviceProvider when a device connects/disconnects so the
  /// firmware-version gate in syncAll() can route to the right Phase-0 sync.
  ///
  /// [firmwareVersion] is the enriched value resolved after getDeviceInfo();
  /// prefer it over [device].firmwareRevision, which on the raw connect object
  /// is frequently still 'Unknown' and would misroute ring-buffer devices to
  /// the multi-file enumerator (so their recordings never enumerate).
  void setDevice(BtDevice? device, {String? firmwareVersion}) {
    final wasRing = usesIndependentRingDrain;
    final changedDevice = _device?.id != device?.id;
    _device = device;
    _firmwareVersion = firmwareVersion;
    if (changedDevice || (wasRing && !usesIndependentRingDrain)) _cancelRingDrain();
    _ringSync.setDevice(device?.copyWith(firmwareRevision: _resolvedFirmware));
    if (usesIndependentRingDrain && (changedDevice || !wasRing)) unawaited(wakeRingDrain());
    // Ring status shares the legacy characteristic but has a different layout.
    _sdcardSync.setDevice(_usesLegacySdcard
        ? (device?.firmwareRevision == _resolvedFirmware
            ? device
            : device?.copyWith(firmwareRevision: _resolvedFirmware))
        : null);
  }

  /// Re-route an already attached device after a device-info retry resolves it.
  void updateFirmwareVersion(String deviceId, String firmwareVersion) {
    if (_device?.id != deviceId || _firmwareVersion == firmwareVersion) return;
    setDevice(_device, firmwareVersion: firmwareVersion);
  }

  bool get _usesLegacySdcard {
    final firmware = _resolvedFirmware;
    return firmware != null && firmware.isNotEmpty && firmware != 'Unknown' && !isRingBufferFirmware(firmware);
  }

  /// Best available firmware for discovery routing: the enriched value if it
  /// resolved, otherwise whatever the raw connect object carries.
  String? get _resolvedFirmware => resolveDiscoveryFirmware(_firmwareVersion, _device?.firmwareRevision);

  /// Prefer the enriched firmware over the raw connect-object value, which is
  /// frequently still 'Unknown'. A missing/'Unknown' enriched value falls back
  /// to the raw one so behavior is never worse than before.
  static String? resolveDiscoveryFirmware(String? enriched, String? raw) {
    if (enriched != null && enriched.isNotEmpty && enriched != 'Unknown') return enriched;
    return raw;
  }

  /// Firmware >= 3.0.20 speaks the ring-buffer protocol; older multi-file
  /// firmware (3.0.17–3.0.19) keeps using StorageSync.
  static bool isRingBufferFirmware(String? version) => RingProtocol.isRingBufferFirmware(version);

  WalSyncs(
    this.listener, {
    SDCardWalSyncImpl? sdcardSync,
    LocalWalSyncImpl? phoneSync,
    StorageSyncImpl? storageSync,
    RingStorageSyncImpl? ringSync,
    FlashPageWalSyncImpl? flashPageSync,
    SyncUploadGate? phoneUploadGate,
    DateTime Function()? phoneNow,
    Timer Function(Duration, void Function(Timer))? phonePeriodic,
    Future<SyncJobFetch> Function(String jobId)? phoneJobStatusFetcher,
    WalCoverageTelemetryEmitter? phoneCoverageTelemetry,
    Future<int?> Function()? phoneFreeDiskBytes,
    Future<void> Function(List<Wal>)? phonePersistWals,
    SyncTransferKeepAlive? keepAlive,
  }) : _keepAlive = keepAlive ?? SyncTransferKeepAlive.instance {
    _phoneSync = phoneSync ??
        LocalWalSyncImpl(
          listener,
          uploadGate: phoneUploadGate,
          now: phoneNow,
          periodic: phonePeriodic,
          freeDiskBytes: phoneFreeDiskBytes,
          persistWals: phonePersistWals,
          jobStatusFetcher: phoneJobStatusFetcher,
          coverageTelemetry: phoneCoverageTelemetry,
        );
    _sdcardSync = sdcardSync ?? SDCardWalSyncImpl(listener);
    _flashPageSync = flashPageSync ?? FlashPageWalSyncImpl(listener);
    _storageSync = storageSync ?? StorageSyncImpl(listener);
    _ringSync = ringSync ?? RingStorageSyncImpl(listener);

    _sdcardSync.setLocalSync(_phoneSync);
    _flashPageSync.setLocalSync(_phoneSync);
    _storageSync.setLocalSync(_phoneSync);
    _ringSync.setLocalSync(_phoneSync);
  }

  @override
  Future deleteWal(Wal wal) async {
    await _phoneSync.deleteWal(wal);
    await _sdcardSync.deleteWal(wal);
    await _flashPageSync.deleteWal(wal);
    await _storageSync.deleteWal(wal);
    await _ringSync.deleteWal(wal);
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    List<Wal> wals = [];
    wals.addAll(await _ringSync.getMissingWals());
    wals.addAll(await _storageSync.getMissingWals());
    if (_usesLegacySdcard) wals.addAll(await _sdcardSync.getMissingWals());
    wals.addAll(await _phoneSync.getMissingWals());
    wals.addAll(await _flashPageSync.getMissingWals());
    return wals;
  }

  List<Wal>? _cachedPhoneWals;
  List<Wal> _cachedDeviceWals = const [];
  List<Wal>? _cachedAllWals;

  Future<List<Wal>> getAllWals() async {
    final devices = <Wal>[
      ...await _ringSync.getMissingWals(),
      ...await _storageSync.getMissingWals(),
      if (_usesLegacySdcard) ...await _sdcardSync.getMissingWals(),
    ];
    final phone = await _phoneSync.getAllWals();
    final flash = await _flashPageSync.getMissingWals();
    final allDevices = [...devices, ...flash];
    var unchanged = identical(phone, _cachedPhoneWals) && allDevices.length == _cachedDeviceWals.length;
    if (unchanged) {
      for (var i = 0; i < allDevices.length; i++) {
        if (!identical(allDevices[i], _cachedDeviceWals[i])) {
          unchanged = false;
          break;
        }
      }
    }
    if (_cachedAllWals == null || !unchanged) {
      _cachedPhoneWals = phone;
      _cachedDeviceWals = allDevices;
      _cachedAllWals = List.unmodifiable([...devices, ...phone, ...flash]);
    }
    return _cachedAllWals!;
  }

  /// Enumerate offline recordings from the connected device WITHOUT downloading
  /// them, so they can be listed (e.g. on the Auto Sync page) even when the user
  /// has turned auto-sync off. Mirrors the per-firmware device discovery that
  /// [syncAll] runs in Phase 0/1b, minus the download. SD-card WALs are already
  /// enumerated on legacy-device connect via [setDevice], so they're not repeated here.
  /// Safe no-op when no device is set; each sub-sync guards against running
  /// while a sync is in progress.
  Future<void> refreshWalsFromDevice({String? firmwareVersion}) async {
    if (_device == null) return;
    // Prefer the caller-supplied firmware, then the enriched value stored at
    // setDevice — the raw connect object's firmwareRevision can still be
    // 'Unknown', which would misroute ring-buffer discovery.
    final fw = (firmwareVersion != null && firmwareVersion.isNotEmpty && firmwareVersion != 'Unknown')
        ? firmwareVersion
        : _resolvedFirmware;
    if (isRingBufferFirmware(fw)) {
      if (usesIndependentRingDrain) {
        if (_ringPass == null && !ring.isSyncing) await wakeRingDrain(discoveryOnly: true);
        return;
      }
      await _ringSync.refreshWalsFromDevice();
    } else {
      await _storageSync.refreshWalsFromDevice();
    }
    await _flashPageSync.refreshWalsFromDevice();
  }

  Future<WalStats> getWalStats() async {
    final allWals = await getAllWals();
    int phoneFiles = 0;
    int sdcardFiles = 0;
    int fromSdcardFiles = 0;
    int limitlessFiles = 0;
    int fromFlashPageFiles = 0;
    int phoneSize = 0;
    int sdcardSize = 0;
    int syncedFiles = 0;
    int missedFiles = 0;

    for (final wal in allWals) {
      if (wal.storage == WalStorage.sdcard) {
        sdcardFiles++;
        sdcardSize += _estimateWalSize(wal);
      } else if (wal.storage == WalStorage.flashPage) {
        limitlessFiles++;
      } else {
        if (wal.originalStorage == WalStorage.sdcard) {
          fromSdcardFiles++;
        } else if (wal.originalStorage == WalStorage.flashPage) {
          fromFlashPageFiles++;
        } else {
          phoneFiles++;
        }
        phoneSize += _estimateWalSize(wal);
      }

      if (wal.status == WalStatus.synced) {
        syncedFiles++;
      } else if (wal.status == WalStatus.miss) {
        missedFiles++;
      }
    }

    return WalStats(
      totalFiles: allWals.length,
      phoneFiles: phoneFiles,
      sdcardFiles: sdcardFiles,
      fromSdcardFiles: fromSdcardFiles,
      limitlessFiles: limitlessFiles,
      fromFlashPageFiles: fromFlashPageFiles,
      phoneSize: phoneSize,
      sdcardSize: sdcardSize,
      syncedFiles: syncedFiles,
      missedFiles: missedFiles,
    );
  }

  int _estimateWalSize(Wal wal) {
    return wal.codec.estimatedRecordingBytes(seconds: wal.seconds, sampleRate: wal.sampleRate, channels: wal.channel);
  }

  Future<void> deleteAllSyncedWals() async {
    await _runDeleteOperations([
      _phoneSync.deleteAllSyncedWals,
      _sdcardSync.deleteAllSyncedWals,
      _flashPageSync.deleteAllSyncedWals,
      _storageSync.deleteAllSyncedWals,
      _ringSync.deleteAllSyncedWals,
    ]);
  }

  Future<void> deleteAllPendingWals() async {
    await _runDeleteOperations([
      _phoneSync.deleteAllPendingWals,
      _sdcardSync.deleteAllPendingWals,
      _flashPageSync.deleteAllPendingWals,
      _storageSync.deleteAllPendingWals,
      _ringSync.deleteAllPendingWals,
    ]);
  }

  Future<void> _runDeleteOperations(List<Future<void> Function()> deleteOperations) async {
    Object? firstError;
    StackTrace? firstStackTrace;
    for (final delete in deleteOperations) {
      try {
        await delete();
      } catch (error, stackTrace) {
        firstError ??= error;
        firstStackTrace ??= stackTrace;
      }
    }
    if (firstError != null) Error.throwWithStackTrace(firstError, firstStackTrace!);
  }

  /// Terminal corruption is produced by the phone-local WAL owner. Device
  /// stores keep their existing pending-deletion semantics.
  Future<void> deleteAllCorruptedWals() => _phoneSync.deleteAllCorruptedWals();

  /// Bounded phone-only drain used while iOS/Android grants background time.
  Future<SyncLocalFilesResponse?> syncLiveCaptureOnly({IWalSyncProgressListener? progress}) =>
      _phoneSync.syncLiveCaptureOnly(progress: progress);

  @override
  void start() {
    _phoneSync.start();
    if (_usesLegacySdcard) _sdcardSync.start();
    _flashPageSync.start();
    _storageSync.start();
    _ringSync.start();
  }

  @override
  Future stop() async {
    disableRingDrain();
    await _phoneSync.stop();
    await _sdcardSync.stop();
    await _flashPageSync.stop();
    await _storageSync.stop();
    await _ringSync.stop();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    _isCancelled = false;
    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    final allMissing = await getMissingWals();
    DebugLogManager.logEvent('sync_started', {
      'totalMissingWals': allMissing.length,
      'sdcard': allMissing.where((w) => w.storage == WalStorage.sdcard).length,
      'flashPage': allMissing.where((w) => w.storage == WalStorage.flashPage).length,
      'phone': allMissing.where((w) => w.storage == WalStorage.disk || w.storage == WalStorage.mem).length,
    });

    if (_isCancelled) return resp;
    // Give recent capture files first claim on the upload pass.
    Logger.debug("WalSyncs: Phase -1 - Uploading already-local live-capture recordings");
    DebugLogManager.logInfo('Sync Phase -1: Uploading live-capture phone files first');
    progress?.onWalSyncedProgress(0.0, phase: SyncPhase.uploadingToCloud);
    final preDrainResult = await _phoneSync.syncLiveCaptureOnly(progress: progress);
    if (preDrainResult != null) {
      resp.newConversationIds.addAll(
        preDrainResult.newConversationIds.where((id) => !resp.newConversationIds.contains(id)),
      );
      resp.updatedConversationIds.addAll(
        preDrainResult.updatedConversationIds.where(
          (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
        ),
      );
      resp.localUploadFailures += preDrainResult.localUploadFailures;
      resp.localUploadPermanentFailures += preDrainResult.localUploadPermanentFailures;
      resp.localUploadPermanentError ??= preDrainResult.localUploadPermanentError;
    }

    if (_isCancelled) return resp;
    Object? deviceError;
    StackTrace? deviceStack;
    try {
      if (!usesIndependentRingDrain) {
        await _downloadDeviceSources(progress: progress);
      }
    } catch (error, stack) {
      // Device protocols own their bounded first-data/idle deadlines and settle
      // their reader before returning/throwing. Do not race a timed-out future
      // against another device reader. A failed device source must still give
      // the independent, already-durable phone backlog its upload turn.
      if (const bool.fromEnvironment('OMI_PHONE_AFTER_DEVICE_FAILURE_OFF')) rethrow;
      deviceError = error;
      deviceStack = stack;
      DebugLogManager.logWarning('Device download incomplete; attempting phone backlog', {'error': '$error'});
    }
    if (_isCancelled) return resp;

    // Phase 2: Upload all phone files to cloud (includes SD card and flash page downloads)
    Logger.debug("WalSyncs: Phase 2 - Uploading phone files to cloud");
    DebugLogManager.logInfo('Sync Phase 2: Uploading phone files to cloud');
    progress?.onWalSyncedProgress(0.0, phase: SyncPhase.uploadingToCloud);
    var partialRes = await _phoneSync.syncAll(progress: progress);
    if (partialRes != null) {
      resp.newConversationIds.addAll(
        partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)),
      );
      resp.updatedConversationIds.addAll(
        partialRes.updatedConversationIds.where(
          (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
        ),
      );
      resp.localUploadFailures += partialRes.localUploadFailures;
      resp.localUploadPermanentFailures += partialRes.localUploadPermanentFailures;
      resp.localUploadPermanentError ??= partialRes.localUploadPermanentError;
    }

    // Keep the device failure visible after the phone ledger has had its turn.
    // The original device record is still pending; this is not a completed sync.
    if (deviceError != null) Error.throwWithStackTrace(deviceError, deviceStack!);

    DebugLogManager.logEvent('sync_completed', {
      'newConversations': resp.newConversationIds.length,
      'updatedConversations': resp.updatedConversationIds.length,
    });

    return resp;
  }

  Future<void> _downloadDeviceSources({IWalSyncProgressListener? progress}) async {
    // Phase 0: New offline storage sync, gated by firmware version.
    //   fw >= 3.0.20  -> ring-buffer protocol (RingStorageSync)
    //   fw 3.0.17–.19 -> multi-file LittleFS protocol (StorageSync)
    //   fw < 3.0.17   -> falls through to Phase 1a legacy SD-card path
    final fwVersion = _resolvedFirmware;
    final useRing = isRingBufferFirmware(fwVersion);
    if (useRing) {
      await _ringSync.refreshWalsFromDevice();
      final ringMissing = await _ringSync.getMissingWals();
      if (_isCancelled) return;
      if (ringMissing.isNotEmpty) {
        Logger.debug("WalSyncs: Phase 0 - Ring-buffer sync (fw=$fwVersion)");
        DebugLogManager.logInfo('Sync Phase 0: Ring-buffer sync', {'fw': fwVersion ?? ''});
        progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
        await _ringSync.syncAll(progress: progress);
      }
    } else {
      await _storageSync.refreshWalsFromDevice();
      final storageMissing = await _storageSync.getMissingWals();
      if (_isCancelled) return;
      if (storageMissing.isNotEmpty) {
        Logger.debug("WalSyncs: Phase 0 - Downloading ${storageMissing.length} multi-file storage files to phone");
        DebugLogManager.logInfo('Sync Phase 0: Multi-file storage sync', {'fw': fwVersion ?? ''});
        progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
        await _storageSync.syncAll(progress: progress);
      }
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after storage sync phase");
      return;
    }

    // Phase 1a: Download SD card data to phone (legacy firmware)
    if (_usesLegacySdcard) {
      Logger.debug("WalSyncs: Phase 1a - Downloading SD card data to phone");
      DebugLogManager.logInfo('Sync Phase 1a: Downloading SD card data to phone');
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
      final missingSDCardWals = (await _sdcardSync.getMissingWals()).where((w) => w.status == WalStatus.miss).toList();

      if (_isCancelled) return;
      if (missingSDCardWals.isNotEmpty) {
        DebugLogManager.logInfo('SD card sync over BLE', {'walCount': missingSDCardWals.length});
        await _sdcardSync.syncAll(progress: progress);
      }
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after SD card phase");
      DebugLogManager.logWarning('Sync cancelled after SD card phase');
      return;
    }

    // Phase 1b: Download flash page data to phone
    Logger.debug("WalSyncs: Phase 1b - Downloading flash page data to phone");
    DebugLogManager.logInfo('Sync Phase 1b: Downloading flash page data to phone');
    // Re-enumerate from the device first (mirrors the ring/storage phases
    // above) so a repeat Sync tap resumes from the device's current flash-page
    // pointer instead of a stale cached WAL — no app relaunch needed.
    await _flashPageSync.refreshWalsFromDevice();
    final flashMissing = (await _flashPageSync.getMissingWals()).where((w) => w.status == WalStatus.miss).toList();
    if (_isCancelled) return;
    if (flashMissing.isNotEmpty) {
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
      await _flashPageSync.syncAll(progress: progress);
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after flash page phase");
      DebugLogManager.logWarning('Sync cancelled after flash page phase');
      return;
    }
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    if (wal.storage == WalStorage.sdcard) {
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
      if (wal.fileNum == -1) {
        final generation = _ringGeneration;
        final active = _ringPass;
        if (active != null) {
          final completed = await active;
          if (generation != _ringGeneration) throw StateError('Ring transfer cancelled');
          if (completed) return null;
        }
        try {
          return await _ringSync.syncWal(wal: wal, progress: progress);
        } finally {
          if (usesIndependentRingDrain && generation == _ringGeneration && _shouldDrainRing?.call() == true) {
            unawaited(wakeRingDrain());
          }
        }
      }
      if (_storageSync.owns(wal)) {
        return _storageSync.syncWal(wal: wal, progress: progress);
      }
      if (!_usesLegacySdcard) {
        throw StateError('Legacy SD read unavailable on ring-buffer firmware');
      }
      return _sdcardSync.syncWal(wal: wal, progress: progress);
    } else if (wal.storage == WalStorage.flashPage) {
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
      return _flashPageSync.syncWal(wal: wal, progress: progress);
    } else {
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.uploadingToCloud);
      return _phoneSync.syncWal(wal: wal, progress: progress);
    }
  }

  @override
  void cancelSync() {
    _ringPausedByUser = true;
    _cancelRingDrain();
    cancelUploadPass();
  }

  /// Upload deadlines own legacy device phases, but never the independent ring.
  void cancelUploadPass() {
    _uploadCancellation++;
    _isCancelled = true;
    if (!usesIndependentRingDrain) _ringSync.cancelSync();
    _storageSync.cancelSync();
    _sdcardSync.cancelSync();
    _flashPageSync.cancelSync();
    _phoneSync.cancelSync();
  }

  void clearUserData() {
    setDevice(null);
    _phoneSync.clearUserData();
    cancelSync();
  }

  bool get isLegacyStorageSyncing => _storageSync.isSyncing || (!usesIndependentRingDrain && _ringSync.isSyncing);

  bool get isStorageSyncing => _storageSync.isSyncing || _ringSync.isSyncing;

  double get storageSpeedKBps => _ringSync.isSyncing ? _ringSync.currentSpeedKBps : _storageSync.currentSpeedKBps;

  bool get isSdCardSyncing => _sdcardSync.isSyncing;

  double get sdCardSpeedKBps => _sdcardSync.currentSpeedKBps;

  bool get isFlashPageSyncing => _flashPageSync.isSyncing;

  /// Why the last flash-page drain pass stopped early (reset at the start of
  /// each flash sync). Lets the UI distinguish "pendant is recording" from a
  /// plain transfer lull instead of reporting silent success.
  FlashSyncStallReason get flashStallReason => _flashPageSync.lastStallReason;

  /// Get conversation IDs accumulated so far from completed upload batches.
  /// Returns null if no sync is in progress or no batches have completed.
  SyncLocalFilesResponse? get accumulatedResponse => _phoneSync.accumulatedResponse;
}
