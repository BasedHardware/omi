import 'dart:async';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/services/wals/device_storage_routing.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';
import 'package:omi/services/wals/storage_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';

class WalSyncs implements IWalSync {
  late LocalWalSyncImpl _phoneSync;
  LocalWalSyncImpl get phone => _phoneSync;

  late SDCardWalSyncImpl _sdcardSync;

  late FlashPageWalSyncImpl _flashPageSync;

  late StorageSyncImpl _storageSync;

  late RingStorageSyncImpl _ringSync;
  late DeviceStorageRouter _deviceStorageRouter;

  final IWalSyncListener listener;

  bool _isCancelled = false;
  BtDevice? _device;
  String? _firmwareVersion;
  final Map<String, RingBacklogDrainReceipt> _automaticRingBacklogReceipts = {};

  /// Called from DeviceProvider when a device connects/disconnects so the
  /// firmware-version gate in syncAll() can route to the right Phase-0 sync.
  ///
  /// [firmwareVersion] is the enriched value resolved after getDeviceInfo();
  /// prefer it over [device].firmwareRevision, which on the raw connect object
  /// is frequently still 'Unknown' and would misroute ring-buffer devices to
  /// the multi-file enumerator (so their recordings never enumerate).
  void setDevice(BtDevice? device, {String? firmwareVersion}) {
    _device = device;
    _firmwareVersion = firmwareVersion;
    _deviceStorageRouter.bind(device, firmwareVersion: firmwareVersion);
  }

  /// Best available firmware for discovery routing: the enriched value if it
  /// resolved, otherwise whatever the raw connect object carries.
  String? get _resolvedFirmware => DeviceStorageProtocolPolicy.resolveFirmware(
        _firmwareVersion,
        _device?.firmwareRevision,
      );

  bool get usesStorageAuthoritativeAudio => DeviceStorageProtocolPolicy.usesStorageAuthoritativeAudio(
        _resolvedFirmware,
      );

  Future<RingAudioTailSession?> startStorageAuthoritativeAudioTail({
    required RingLiveFramesHandler onLiveFrames,
    bool resumeLiveContinuity = false,
  }) {
    if (!usesStorageAuthoritativeAudio || _deviceStorageRouter.protocol != DeviceStorageProtocol.ringBuffer) {
      return Future.value(null);
    }
    return _ringSync.startAudioTail(
      onLiveFrames: onLiveFrames,
      resumeLiveContinuity: resumeLiveContinuity,
    );
  }

  /// The storage-authoritative live scheduler is a long-lived capture owner,
  /// not a conflicting user-visible sync.
  bool get isRingAudioTailActive => _ringSync.isAudioTailActive;

  /// Latch one manual backlog snapshot onto the active live scheduler.
  ///
  /// Returns null when no live scheduler owns the ring, in which case the
  /// caller should use the ordinary device-storage sync path.
  Future<RingBacklogDrainReceipt?>? requestActiveRingBacklogDrain() => _ringSync.requestAudioTailBacklogDrain();

  RingBacklogDrainReceipt? get pendingAutomaticRingBacklogReceipt =>
      _automaticRingBacklogReceipts.isEmpty ? null : _automaticRingBacklogReceipts.values.first;

  void completeAutomaticRingBacklogReceipt(
    RingBacklogDrainReceipt receipt,
  ) {
    final current = _automaticRingBacklogReceipts[receipt.deviceId];
    if (current?.targetWriteSeq != receipt.targetWriteSeq) return;
    _automaticRingBacklogReceipts.remove(receipt.deviceId);
    if (_automaticRingBacklogReceipts.isNotEmpty) {
      unawaited(
        RecordingTransferCoordinator.instance.wake(
          WakeTrigger.ringBacklogSnapshotCompleted,
        ),
      );
    }
  }

  /// Upload WALs that are already durable on the phone without starting a
  /// second device-storage reader. LocalWalSync's mutex keeps fresh upload
  /// wakes and this explicit drain idempotent.
  Future<SyncLocalFilesResponse?> syncPhoneWals({
    IWalSyncProgressListener? progress,
    bool includeBackfill = false,
  }) =>
      includeBackfill ? _phoneSync.syncAll(progress: progress) : _phoneSync.syncFreshOnly(progress: progress);

  Future<AuthorizedRecoverySyncResult> syncAuthorizedRingRecovery({
    required RingBacklogDrainReceipt receipt,
    IWalSyncProgressListener? progress,
  }) =>
      _phoneSync.syncAuthorizedRecovery(
        deviceId: receipt.deviceId,
        targetWriteSeq: receipt.targetWriteSeq,
        progress: progress,
      );

  WalSyncs(this.listener) {
    _phoneSync = LocalWalSyncImpl(listener);
    _sdcardSync = SDCardWalSyncImpl(listener);
    _flashPageSync = FlashPageWalSyncImpl(listener);
    _storageSync = StorageSyncImpl(listener);
    _ringSync = RingStorageSyncImpl(
      listener,
      deepBacklogPolicy: () => ringShouldDrainDeepBacklog(
        autoSyncEnabled: SharedPreferencesUtil().autoSyncOfflineRecordings,
      ),
      onBacklogSnapshotCompleted: (receipt) {
        final preferences = SharedPreferencesUtil();
        if (!preferences.autoSyncOfflineRecordings || preferences.useCustomStt) {
          return;
        }
        final current = _automaticRingBacklogReceipts[receipt.deviceId];
        if (current == null || receipt.targetWriteSeq > current.targetWriteSeq) {
          _automaticRingBacklogReceipts[receipt.deviceId] = receipt;
        }
        unawaited(
          RecordingTransferCoordinator.instance.wake(
            WakeTrigger.ringBacklogSnapshotCompleted,
          ),
        );
      },
    );
    _deviceStorageRouter = DeviceStorageRouter(
      bindLegacySdCard: _sdcardSync.setDevice,
      bindMultiFile: _storageSync.setDevice,
      bindRingBuffer: _ringSync.setDevice,
      bindLimitlessFlash: _flashPageSync.setDevice,
    );

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
    wals.addAll(await _sdcardSync.getMissingWals());
    wals.addAll(await _phoneSync.getMissingWals());
    wals.addAll(await _flashPageSync.getMissingWals());
    return wals;
  }

  Future<List<Wal>> getAllWals() async {
    List<Wal> wals = [];
    wals.addAll(await _ringSync.getMissingWals());
    wals.addAll(await _storageSync.getMissingWals());
    wals.addAll(await _sdcardSync.getMissingWals());
    wals.addAll(await _phoneSync.getAllWals());
    wals.addAll(await _flashPageSync.getMissingWals());
    return wals;
  }

  /// Enumerate offline recordings from the connected device WITHOUT downloading
  /// them, so they can be listed (e.g. on the Auto Sync page) even when the user
  /// has turned auto-sync off. Mirrors the per-firmware device discovery that
  /// [syncAll] runs in Phase 0/1b, minus the download. SD-card WALs are already
  /// enumerated on connect via [sdcard.setDevice], so they're not repeated here.
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
    switch (DeviceStorageProtocolPolicy.classify(
      _device,
      firmwareVersion: fw,
    )) {
      case DeviceStorageProtocol.ringBuffer:
        await _ringSync.refreshWalsFromDevice();
      case DeviceStorageProtocol.multiFile:
        await _storageSync.refreshWalsFromDevice();
      case DeviceStorageProtocol.none:
      case DeviceStorageProtocol.legacySdCard:
      case DeviceStorageProtocol.limitlessFlash:
        break;
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
    int bytesPerSecond;
    switch (wal.codec) {
      case BleAudioCodec.opusFS320:
        bytesPerSecond = 16000;
      case BleAudioCodec.opus:
        bytesPerSecond = 8000;
        break;
      case BleAudioCodec.pcm16:
        bytesPerSecond = wal.sampleRate * 2 * wal.channel;
        break;
      case BleAudioCodec.pcm8:
        bytesPerSecond = wal.sampleRate * 1 * wal.channel;
        break;
      default:
        bytesPerSecond = 8000;
    }
    return bytesPerSecond * wal.seconds;
  }

  Future<void> deleteAllSyncedWals() async {
    await _phoneSync.deleteAllSyncedWals();
    await _sdcardSync.deleteAllSyncedWals();
    await _flashPageSync.deleteAllSyncedWals();
    await _storageSync.deleteAllSyncedWals();
    await _ringSync.deleteAllSyncedWals();
  }

  Future<void> deleteAllPendingWals() async {
    await _phoneSync.deleteAllPendingWals();
    await _sdcardSync.deleteAllPendingWals();
    await _flashPageSync.deleteAllPendingWals();
    await _storageSync.deleteAllPendingWals();
    await _ringSync.deleteAllPendingWals();
  }

  /// Terminal corruption is produced by the phone-local WAL owner. Device
  /// stores keep their existing pending-deletion semantics.
  Future<void> deleteAllCorruptedWals() => _phoneSync.deleteAllCorruptedWals();

  @override
  void start() {
    _phoneSync.start();
    _sdcardSync.start();
    _flashPageSync.start();
    _storageSync.start();
    _ringSync.start();
  }

  @override
  Future stop() async {
    await _phoneSync.stop();
    await _sdcardSync.stop();
    await _flashPageSync.stop();
    await _storageSync.stop();
    await _ringSync.stop();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
  }) async {
    _isCancelled = false;
    var resp = SyncLocalFilesResponse(
      newConversationIds: [],
      updatedConversationIds: [],
    );

    final allMissing = await getMissingWals();
    DebugLogManager.logEvent('sync_started', {
      'totalMissingWals': allMissing.length,
      'sdcard': allMissing.where((w) => w.storage == WalStorage.sdcard).length,
      'flashPage': allMissing.where((w) => w.storage == WalStorage.flashPage).length,
      'phone': allMissing
          .where(
            (w) => w.storage == WalStorage.disk || w.storage == WalStorage.mem,
          )
          .length,
    });

    // Protect the live path before a potentially multi-hour device drain. The
    // phone scheduler is lane-aware and sends recent WALs first; its one-job
    // backfill window prevents this pass from flooding historical work.
    Logger.debug(
      "WalSyncs: Phase -1 - Uploading already-local fresh recordings",
    );
    DebugLogManager.logInfo('Sync Phase -1: Uploading fresh phone files first');
    progress?.onWalSyncedProgress(0.0, phase: SyncPhase.uploadingToCloud);
    final preDrainResult = await _phoneSync.syncFreshOnly(progress: progress);
    if (preDrainResult != null) {
      resp.newConversationIds.addAll(
        preDrainResult.newConversationIds.where(
          (id) => !resp.newConversationIds.contains(id),
        ),
      );
      resp.updatedConversationIds.addAll(
        preDrainResult.updatedConversationIds.where(
          (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
        ),
      );
      resp.localUploadFailures += preDrainResult.localUploadFailures;
    }

    // Phase 0: New offline storage sync, gated by firmware version.
    //   fw >= 3.0.20  -> ring-buffer protocol (RingStorageSync)
    //   fw 3.0.17–.19 -> multi-file LittleFS protocol (StorageSync)
    //   fw < 3.0.17   -> falls through to Phase 1a legacy SD-card path
    final fwVersion = _resolvedFirmware;
    final storageProtocol = _deviceStorageRouter.protocol;
    switch (storageProtocol) {
      case DeviceStorageProtocol.ringBuffer:
        await _ringSync.refreshWalsFromDevice();
        final ringMissing = await _ringSync.getMissingWals();
        if (ringMissing.isNotEmpty) {
          Logger.debug("WalSyncs: Phase 0 - Ring-buffer sync (fw=$fwVersion)");
          DebugLogManager.logInfo('Sync Phase 0: Ring-buffer sync', {
            'fw': fwVersion ?? '',
          });
          progress?.onWalSyncedProgress(
            0.0,
            phase: SyncPhase.downloadingFromDevice,
          );
          await _ringSync.syncAll(progress: progress);
        }
      case DeviceStorageProtocol.multiFile:
        await _storageSync.refreshWalsFromDevice();
        final storageMissing = await _storageSync.getMissingWals();
        if (storageMissing.isNotEmpty) {
          Logger.debug(
            "WalSyncs: Phase 0 - Downloading ${storageMissing.length} multi-file storage files to phone",
          );
          DebugLogManager.logInfo('Sync Phase 0: Multi-file storage sync', {
            'fw': fwVersion ?? '',
          });
          progress?.onWalSyncedProgress(
            0.0,
            phase: SyncPhase.downloadingFromDevice,
          );
          await _storageSync.syncAll(progress: progress);
        }
      case DeviceStorageProtocol.none:
      case DeviceStorageProtocol.legacySdCard:
      case DeviceStorageProtocol.limitlessFlash:
        break;
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after storage sync phase");
      return resp;
    }

    // Phase 1a is exclusive to legacy firmware. Ring and multi-file firmware
    // reuse these characteristics with incompatible framing.
    if (storageProtocol == DeviceStorageProtocol.legacySdCard) {
      Logger.debug("WalSyncs: Phase 1a - Downloading SD card data to phone");
      DebugLogManager.logInfo(
        'Sync Phase 1a: Downloading SD card data to phone',
      );
      progress?.onWalSyncedProgress(
        0.0,
        phase: SyncPhase.downloadingFromDevice,
      );
      final missingSDCardWals = (await _sdcardSync.getMissingWals()).where((w) => w.status == WalStatus.miss).toList();

      if (missingSDCardWals.isNotEmpty) {
        DebugLogManager.logInfo('SD card sync over BLE', {
          'walCount': missingSDCardWals.length,
        });
        await _sdcardSync.syncAll(progress: progress);
      }
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after SD card phase");
      DebugLogManager.logWarning('Sync cancelled after SD card phase');
      return resp;
    }

    // Phase 1b: Download flash page data to phone
    Logger.debug("WalSyncs: Phase 1b - Downloading flash page data to phone");
    DebugLogManager.logInfo(
      'Sync Phase 1b: Downloading flash page data to phone',
    );
    // Re-enumerate from the device first (mirrors the ring/storage phases
    // above) so a repeat Sync tap resumes from the device's current flash-page
    // pointer instead of a stale cached WAL — no app relaunch needed.
    await _flashPageSync.refreshWalsFromDevice();
    final flashMissing = (await _flashPageSync.getMissingWals()).where((w) => w.status == WalStatus.miss).toList();
    if (flashMissing.isNotEmpty) {
      progress?.onWalSyncedProgress(
        0.0,
        phase: SyncPhase.downloadingFromDevice,
      );
      await _flashPageSync.syncAll(progress: progress);
    }

    if (_isCancelled) {
      Logger.debug("WalSyncs: Cancelled after flash page phase");
      DebugLogManager.logWarning('Sync cancelled after flash page phase');
      return resp;
    }

    // Phase 2: Upload all phone files to cloud (includes SD card and flash page downloads)
    Logger.debug("WalSyncs: Phase 2 - Uploading phone files to cloud");
    DebugLogManager.logInfo('Sync Phase 2: Uploading phone files to cloud');
    progress?.onWalSyncedProgress(0.0, phase: SyncPhase.uploadingToCloud);
    var partialRes = await _phoneSync.syncAll(progress: progress);
    if (partialRes != null) {
      resp.newConversationIds.addAll(
        partialRes.newConversationIds.where(
          (id) => !resp.newConversationIds.contains(id),
        ),
      );
      resp.updatedConversationIds.addAll(
        partialRes.updatedConversationIds.where(
          (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
        ),
      );
      resp.localUploadFailures += partialRes.localUploadFailures;
    }

    DebugLogManager.logEvent('sync_completed', {
      'newConversations': resp.newConversationIds.length,
      'updatedConversations': resp.updatedConversationIds.length,
    });

    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
  }) async {
    if (wal.storage == WalStorage.sdcard) {
      progress?.onWalSyncedProgress(
        0.0,
        phase: SyncPhase.downloadingFromDevice,
      );
      if (wal.fileNum == -1) {
        return _ringSync.syncWal(wal: wal, progress: progress);
      }
      return _sdcardSync.syncWal(wal: wal, progress: progress);
    } else if (wal.storage == WalStorage.flashPage) {
      progress?.onWalSyncedProgress(
        0.0,
        phase: SyncPhase.downloadingFromDevice,
      );
      return _flashPageSync.syncWal(wal: wal, progress: progress);
    } else {
      progress?.onWalSyncedProgress(0.0, phase: SyncPhase.uploadingToCloud);
      return _phoneSync.syncWal(wal: wal, progress: progress);
    }
  }

  @override
  void cancelSync() {
    _isCancelled = true;
    final ringTailWasActive = _ringSync.isAudioTailActive;
    // The manual request can outlive a disconnected tail. Explicit user
    // cancellation must always resolve its Future even when no BLE owner is
    // currently attached.
    _ringSync.cancelRequestedAudioTailBacklogDrain();
    if (!ringTailWasActive) {
      _ringSync.cancelSync();
    }
    _storageSync.cancelSync();
    _sdcardSync.cancelSync();
    _flashPageSync.cancelSync();
    _phoneSync.cancelSync();
  }

  bool get isStorageSyncing => _storageSync.isSyncing || _ringSync.isSyncing;

  double get storageSpeedKBps => _ringSync.isSyncing ? _ringSync.currentSpeedKBps : _storageSync.currentSpeedKBps;

  bool get isSdCardSyncing => _sdcardSync.isSyncing;

  double get sdCardSpeedKBps => _sdcardSync.currentSpeedKBps;

  bool get isFlashPageSyncing => _flashPageSync.isSyncing;

  /// Get conversation IDs accumulated so far from completed upload batches.
  /// Returns null if no sync is in progress or no batches have completed.
  SyncLocalFilesResponse? get accumulatedResponse => _phoneSync.accumulatedResponse;
}
