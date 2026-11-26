import 'package:omi/services/wals/local_wal_sync.dart';
import 'dart:async';
import 'package:omi/services/wals/ring_custody_diagnostics.dart';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/ring_drain_policy.dart' show waitForRingRead, decodeCustodyRingAudio;
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/device_capture_clock.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

/// Ring-buffer storage sync for firmware 3.0.20+ (omi PR #7216).
///
/// Wire layout (per record, packet_size = 444 bytes):
///   [timestamp:4 BE][audio_payload:440]
/// The 440-byte payload uses the same packed [size:1][frame:size]... framing
/// as the multi-file protocol, so the audio parser is reused unchanged.
///
/// Notifications on the control characteristic carry an opcode byte:
///   0x01 ACK             [0x01][status]
///   0x02 INFO            [0x02][read:u64 BE][write:u64 BE][cap:u32 BE][dropped:u64 BE][pkt_size:u16 BE]
///   0x03 DATA            [0x03][raw_bytes...]   <-- not aligned to record boundaries
///   0x04 DONE            [0x04][status][next_seq:u64 BE]
///   0x05 READ_BEGIN      [0x05][transfer_start_seq:u64 BE][packet_count:u32 BE]
///
/// Data-safety invariant: the device-side read frontier is released ONLY for
/// records proven durable on the phone — file bytes fsynced AND the WAL index
/// save completed. With CAP_APP_ACK_RECLAIM an incarnation-scoped ADVANCE_ID
/// may run incrementally per durable chunk; otherwise a single anonymous
/// ADVANCE is sent after a DONE that consumed the expected records. Legacy
/// firmware may reclaim during BLE delivery; interruption can lose its RAM
/// tail. Custody firmware preserves ONLY unadvanced records; already durable
/// chunk advances remain. Interrupted custody reads still commit their exact
/// indexed prefix; an epoch change retains receipts for the next connection.
/// Unproven records remain on the pendant. Legacy completion rules stay intact.
/// Device-clock steps between consecutive ring records above this are a real
/// recording gap (pendant off, or a clock correction), never one recording.
const ringRecordGapBreakSeconds = 60;

/// Where a ring record sits on the recording timeline.
///
/// [breaks]: the record starts a new contiguous recording, so no chunk may span
/// it. [run]: non-null when the record's time is not trustworthy (see
/// [Wal.clockRun]). A backwards step means the pendant restarted with a clock
/// restored from its last phone sync: those times are stale, so the stretch
/// gets its own run until the next discontinuity. Without a valid RTC every
/// record shares one estimated run.
({bool breaks, String? run}) ringRecordClockBoundary({
  required int? previousTs,
  required int ts,
  required bool rtcValid,
  required String? currentRun,
}) {
  if (!rtcValid || ts <= 0) {
    return (breaks: false, run: currentRun ?? Wal.newClockRun());
  }
  if (previousTs == null) return (breaks: false, run: currentRun);
  // A device-clocked record after an untimed one starts a new recording.
  if (previousTs <= 0) return (breaks: true, run: null);
  final step = ts - previousTs;
  if (step < 0) return (breaks: true, run: Wal.newClockRun());
  if (step > ringRecordGapBreakSeconds) return (breaks: true, run: null);
  return (breaks: false, run: currentRun);
}

/// Records fetched per read on firmware where the phone owns reclaim: about
/// 40 seconds of transfer and 1.2 MB in memory. Each read is stored and the
/// pendant advanced past it before the next is requested, so a dropped link
/// costs at most one of these and nothing is downloaded twice.
const int ringReadWindowRecords = 2700;

/// What the reads of one sync pass over the ring share.
class _RingPass {
  _RingPass({
    required this.wal,
    required this.progress,
    required this.connection,
    required this.epoch,
    required this.ringInfo,
    required this.rtcValid,
    required this.phoneNow,
    required this.deviceId,
    required this.effectiveCaps,
    required this.ringId,
    required this.droppedDelta,
    required this.admittedGeneration,
  });

  final Wal wal;
  final IWalSyncProgressListener? progress;
  final DeviceConnection connection;
  final int epoch;
  final RingInfo ringInfo;
  final bool rtcValid;
  final int phoneNow;
  final String deviceId;
  final int effectiveCaps;
  final int? ringId;
  final int? droppedDelta;
  final int admittedGeneration;

  /// The unread range as it stood when the pass began. The pass does not chase
  /// records written after that.
  int get startSeq => ringInfo.readSeq;
  int get endSeq => ringInfo.writeSeq;

  int recordsCredited = 0;
  int recordsDownloaded = 0;
  int recordsDeduped = 0;

  // Recording continuity across the reads of one pass. A recording that spans
  // two reads is still one recording: it keeps its clock run and, when the
  // pendant has no usable clock, one estimated start with frames counted on.
  int? lastRecordTs;
  int? lastRawRecordTs;
  String? clockRun;
  int? firstRecordTs;
  int elapsedFrames = 0;

  /// Records were released without being read, so the next read does not
  /// continue the recording the last one ended in.
  void breakContinuity() {
    lastRecordTs = null;
    lastRawRecordTs = null;
    clockRun = null;
    firstRecordTs = null;
    elapsedFrames = 0;
  }
}

class RingStorageSyncImpl implements RingStorageSync {
  static const Duration _fullReadTimeout = Duration(minutes: 30);
  static const Duration _windowReadTimeout = Duration(minutes: 5);

  /// The pendant notifies the live mark for a commit just after the INFO that
  /// reported it. How long to let it arrive before judging the live tail.
  static const Duration liveMarkSettle = Duration(milliseconds: 400);

  List<Wal> _wals = [];
  BtDevice? _device;
  bool independentDiscovery = false;
  void Function()? onDurableChunk;
  DateTime? _lastUploadWake;
  ({int epoch, BleAudioCodec codec})? _discoveryCodec;
  int _discoveryGeneration = 0;
  ({int seconds, int bytes})? _backlog;
  DateTime? _backlogObservedAt;

  ({int seconds, int bytes})? get freshBacklog {
    final observed = _backlogObservedAt;
    if (observed == null || _clock().difference(observed) >= const Duration(minutes: 2)) return null;
    return _backlog;
  }

  int _packetsOutsideLiveTail(DeviceConnection connection, String deviceId, RingInfo info) {
    final epoch = connection.ringCustodyEpoch;
    final liveFrom = _custody.liveProofStartSeq(deviceId, epoch);
    if (_custody.isIncarnationInvalid(deviceId, epoch) ||
        liveFrom == null ||
        !_custody.liveMarksReach(deviceId, epoch, info.writeSeq)) {
      return info.unreadPackets;
    }
    return (liveFrom - info.readSeq).clamp(0, info.unreadPackets);
  }

  void _publishBacklog(DeviceConnection connection, String deviceId, RingInfo info, BleAudioCodec codec,
      {required bool reading}) {
    final packets = _packetsOutsideLiveTail(connection, deviceId, info);
    final seconds = packets *
        (RingProtocol.audioPayloadBytes ~/ (codec.getFramesLengthInBytes() + 1)) ~/
        codec.getFramesPerSecond();
    _backlog = (seconds: seconds, bytes: packets * RingProtocol.recordSize);
    _backlogObservedAt = _clock();
    DebugLogManager.logEvent('pendant_custody', {
      'action': 'ring_backlog_observed',
      'device': deviceId,
      'connection_epoch': connection.ringCustodyEpoch,
      'ring_id': info.ringId,
      'firmware': _device?.firmwareRevision,
      'read_seq': info.readSeq,
      'write_seq': info.writeSeq,
      'unread_packets': info.unreadPackets,
      'capacity_packets': info.capacityPackets,
      'dropped_packets': info.droppedPackets,
      'reader_active': reading,
    });
  }

  StreamSubscription? _notifyStream;
  String? _activeSyncDeviceId;
  bool _firmwareStopRequested = false;
  static final Map<String, Object> _readOwners = {};
  Completer<void>? _activeReadDone;
  void Function()? _cancelRead;
  DeviceConnection? _sourceConnection;
  int? _sourceEpoch;
  Future<void>? _sourceStop;
  Timer? _persistenceTimer;

  IWalSyncListener listener;
  LocalWalSync? _localSync;

  bool _isCancelled = false;
  bool _isSyncing = false;
  String _syncPhase = 'connection';
  @override
  bool get isSyncing => _isSyncing;

  final Map<String, int> _droppedBaseline = {};

  int _totalBytesDownloaded = 0;
  DateTime? _downloadStartTime;
  double _currentSpeedKBps = 0.0;
  @override
  double get currentSpeedKBps => _currentSpeedKBps;

  final Timer Function(Duration, void Function()) _transferTimer;
  final Timer Function(Duration, void Function()) _persistenceDeadlineTimer;
  final Future<DeviceConnection?> Function(String)? _connectionResolver;
  final DateTime Function() _clock;

  RingStorageSyncImpl(
    this.listener, {
    Timer Function(Duration, void Function())? transferTimer,
    Timer Function(Duration, void Function())? persistenceTimer,
    Future<DeviceConnection?> Function(String)? connectionResolver,
    DateTime Function()? clock,
  })  : _transferTimer = transferTimer ?? Timer.new,
        _persistenceDeadlineTimer = persistenceTimer ?? Timer.new,
        _connectionResolver = connectionResolver,
        _clock = clock ?? DateTime.now;

  @visibleForTesting
  set testWals(List<Wal> wals) => _wals = wals;

  DeviceConnection? _testConnection;

  @visibleForTesting
  set testConnection(DeviceConnection? connection) => _testConnection = connection;

  int _windowRecords = ringReadWindowRecords;

  @visibleForTesting
  set testWindowRecords(int records) => _windowRecords = records;

  Duration _liveMarkSettle = liveMarkSettle;

  @visibleForTesting
  set testLiveMarkSettle(Duration settle) => _liveMarkSettle = settle;

  PendantRingCustody _custody = PendantRingCustody.shared;

  @visibleForTesting
  set testCustody(PendantRingCustody custody) => _custody = custody;

  @override
  void setLocalSync(LocalWalSync localSync) {
    _localSync = localSync;
  }

  @override
  void setDevice(BtDevice? device) {
    if (_device?.id != device?.id) {
      cancelSync();
      _wals = [];
      _backlogObservedAt = null;
      _discoveryCodec = null;
      _lastUploadWake = null;
    }
    _device = device;
  }

  @override
  void cancelSync() {
    _discoveryGeneration++;
    if (!_isSyncing) return;
    _isCancelled = true;
    Logger.debug('RingStorageSync: Cancel requested');

    if (ringDrainRecoveryEnabled) {
      _cancelRead?.call();
      final source = _sourceConnection;
      final epoch = _sourceEpoch;
      if (source != null && epoch != null) unawaited(_stopRingTransfer(source, epoch));
      return;
    }
    final sub = _notifyStream;
    if (sub != null) {
      unawaited(sub.cancel());
    }
    unawaited(_requestFirmwareStopSync());
  }

  Future<void> _requestFirmwareStopSync() async {
    if (_firmwareStopRequested) return;
    _firmwareStopRequested = true;

    final deviceId = _activeSyncDeviceId ?? _device?.id;
    if (deviceId == null || deviceId.isEmpty) return;

    try {
      final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection == null) return;
      // CMD_STOP_SYNC (0x03) — does not persist progress; data stays in the ring.
      await connection.stopStorageSync();
      Logger.debug('RingStorageSync: STOP command sent');
    } catch (e) {
      Logger.debug('RingStorageSync: Failed to send STOP: $e');
    }
  }

  void _resetSyncState() {
    _isCancelled = false;
    _isSyncing = false;
    _activeSyncDeviceId = null;
    _firmwareStopRequested = false;
    _sourceStop = null;
    _totalBytesDownloaded = 0;
    _downloadStartTime = null;
    _currentSpeedKBps = 0.0;
  }

  void _updateSpeed(int newBytes) {
    _totalBytesDownloaded += newBytes;
    if (_downloadStartTime != null) {
      final elapsedSeconds = DateTime.now().difference(_downloadStartTime!).inMilliseconds / 1000.0;
      if (elapsedSeconds > 0.5) {
        _currentSpeedKBps = (_totalBytesDownloaded / 1024.0) / elapsedSeconds;
      }
    }
  }

  /// Returns true if the device has unread packets in the ring.
  /// Returns false for devices on older firmware (status read returns null).
  @override
  Future<bool> hasFilesToSync() async {
    if (_device == null) return false;
    try {
      final connection = _testConnection ?? await ServiceManager.instance().device.ensureConnection(_device!.id);
      if (connection == null) return false;
      final status = await connection.getRingStatus();
      var result = status != null && status.unreadPackets > 0;
      if (result && await _unreadIsLiveTail(connection)) result = false;
      Logger.debug('RingStorageSync.hasFilesToSync: status=$status result=$result');
      return result;
    } catch (e) {
      Logger.debug('RingStorageSync.hasFilesToSync: error: $e');
      return false;
    }
  }

  /// Returns the cached virtual WAL representing the unread ring range.
  /// Safe to call during sync — never touches BLE.
  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
  }

  /// Discover unread ring data via BLE. Must be called BEFORE syncAll().
  /// Constructs ONE virtual Wal covering the entire unread range (the ring is
  /// a single logical stream, not a list of files).
  @override
  Future<void> refreshWalsFromDevice() async {
    if (_device == null) return;
    if (_isSyncing) {
      Logger.debug('RingStorageSync.refreshWalsFromDevice: skipping — sync in progress');
      return;
    }

    final device = _device!;
    final discovery = _discoveryGeneration;
    final independent = independentDiscovery;
    try {
      final connection = _testConnection ??
          await (_connectionResolver?.call(device.id) ?? ServiceManager.instance().device.ensureConnection(device.id));
      if (connection == null || discovery != _discoveryGeneration) return;
      final epoch = connection.ringCustodyEpoch;
      bool current() => discovery == _discoveryGeneration && connection.ringCustodyEpoch == epoch && !_isSyncing;

      RingInfo? info;
      int unread;
      if (independent) {
        // The independent lane has already joined its previous reader through
        // STOP and write settlement. INFO is safe without a discovery STOP.
        info = await connection.getRingInfo();
        if (!current()) return;
        if (info == null) return; // Retain the previous observation until it expires.
        if (_custody.liveProofStartSeq(device.id, epoch) != null) {
          await Future<void>.delayed(_liveMarkSettle);
          if (!current()) return;
        }
        unread = _packetsOutsideLiveTail(connection, device.id, info);
      } else {
        final status = await connection.getRingStatus();
        if (!current()) return;
        unread = status?.unreadPackets ?? 0;
        if (unread == 0 || await _unreadIsLiveTail(connection)) {
          if (current()) _wals = [];
          return;
        }
        if (!current()) return;
        await connection.stopStorageSync();
        await Future<void>.delayed(const Duration(milliseconds: 500));
        if (!current()) return;
      }

      final cachedCodec = _discoveryCodec;
      final codec = independent && cachedCodec?.epoch == epoch ? cachedCodec!.codec : await connection.getAudioCodec();
      final pd = independent ? device : await device.getDeviceInfo(connection);
      if (!current()) return;
      if (info != null) {
        _discoveryCodec = (epoch: epoch, codec: codec);
        _publishBacklog(connection, device.id, info, codec, reading: false);
      }
      final deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : 'Omi';

      final fps = codec.getFramesPerSecond();
      final frameLen = codec.getFramesLengthInBytes();
      // Estimate seconds: each 440B audio payload holds ~ floor(440 / (frameLen + 1)) frames
      // (size byte + frame). framesPerRecord rounded down for a conservative duration.
      final framesPerRecord = frameLen > 0 ? RingProtocol.audioPayloadBytes ~/ (frameLen + 1) : 0;
      final estimatedFrames = framesPerRecord * unread;
      final estimatedSecs = fps > 0 ? estimatedFrames ~/ fps : 0;

      // Skip very small rings (<10s of audio) — same threshold as the file-based path.
      if (estimatedSecs < 10) {
        Logger.debug('RingStorageSync.refreshWalsFromDevice: ring too small ($estimatedSecs s), skipping');
        final hadInventory = _wals.isNotEmpty;
        _wals = [];
        if (independent && hadInventory) listener.onWalUpdated();
        return;
      }

      final displayTimerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - estimatedSecs;
      _wals = [
        Wal(
          codec: codec,
          timerStart: displayTimerStart,
          status: WalStatus.miss,
          storage: WalStorage.sdcard,
          seconds: estimatedSecs,
          storageOffset: 0,
          storageTotalBytes: unread * RingProtocol.recordSize,
          fileNum: -1,
          device: _device!.id,
          deviceModel: deviceModel,
          totalFrames: estimatedFrames,
          syncedFrameOffset: 0,
        ),
      ];
      if (independent) listener.onWalUpdated();
      Logger.debug(
        'RingStorageSync.refreshWalsFromDevice: 1 virtual WAL ($unread pkts, ~${estimatedSecs}s)',
      );
    } catch (e) {
      Logger.debug('RingStorageSync.refreshWalsFromDevice: error: $e');
    }
  }

  /// With live persist on, the ring always holds the last seconds the phone is
  /// still proving. Downloading that tail would store a second copy of audio
  /// that arrived live a moment ago, on every sync wake, so it is left to the
  /// live proof to release. See [PendantRingCustody.liveRunCoversUnread].
  Future<bool> _unreadIsLiveTail(DeviceConnection connection) async {
    final deviceId = _device?.id;
    if (deviceId == null) return false;
    final epoch = connection.ringCustodyEpoch;
    if (_custody.liveProofStartSeq(deviceId, epoch) == null) return false;
    final info = await connection.getRingInfo();
    if (info == null) return false;
    await Future<void>.delayed(_liveMarkSettle);
    if (connection.ringCustodyEpoch != epoch) return false;
    return _custody.liveRunCoversUnread(deviceId, epoch, info);
  }

  /// Delete a wal. WalSyncs.deleteWal cascades to every sub-sync regardless
  /// of which one owns the wal, so we MUST verify membership before touching
  /// the device — clearing the ring on an unrelated phone/sdcard delete would
  /// wipe data the user didn't intend to delete.
  ///
  /// The ring is a single logical stream; deleting our virtual wal maps to
  /// clearing the entire ring on the device. The wal is removed only after
  /// the device confirms the clear — an unconfirmed clear keeps the wal so
  /// the audio cannot resurrect as a "new" recording on the next sync.
  @override
  Future deleteWal(Wal wal) async {
    if (!_wals.any((w) => w.id == wal.id)) return;
    if (_isSyncing) {
      Logger.debug('RingStorageSync.deleteWal: skipping — sync in progress');
      return;
    }
    final cleared = await _clearRingOnDevice();
    if (!cleared) {
      Logger.debug('RingStorageSync.deleteWal: ring clear not confirmed, keeping WAL');
      return;
    }
    _wals = _wals.where((w) => w.id != wal.id).toList();
    listener.onWalUpdated();
  }

  @override
  Future<void> deleteAllSyncedWals() async {
    _wals = _wals.where((w) => w.status != WalStatus.synced).toList();
    listener.onWalUpdated();
  }

  /// Cascades from WalSyncs.deleteAllPendingWals across every sub-sync.
  /// Only clear the ring when WE actually own pending wals — otherwise this
  /// runs as a no-op for users with phone/sdcard pending wals only.
  @override
  Future<void> deleteAllPendingWals() async {
    if (!_wals.any((w) => w.status == WalStatus.miss)) return;
    if (_isSyncing) {
      Logger.debug('RingStorageSync.deleteAllPendingWals: skipping — sync in progress');
      return;
    }
    final cleared = await _clearRingOnDevice();
    if (!cleared) {
      Logger.debug('RingStorageSync.deleteAllPendingWals: ring clear not confirmed, keeping WALs');
      return;
    }
    _wals = _wals.where((w) => w.status != WalStatus.miss).toList();
    listener.onWalUpdated();
  }

  /// Clear the ring on the device. Returns true only when the device
  /// confirmed the clear; absent device, missing connection, BLE errors, and
  /// a rejected command all return false (fail-closed).
  Future<bool> _clearRingOnDevice() async {
    if (_device == null) return false;
    try {
      final connection = _testConnection ?? await ServiceManager.instance().device.ensureConnection(_device!.id);
      if (connection == null) return false;
      final ok = await connection.clearRing();
      Logger.debug('RingStorageSync._clearRingOnDevice: ok=$ok');
      return ok;
    } catch (e) {
      Logger.debug('RingStorageSync._clearRingOnDevice: error: $e');
      return false;
    }
  }

  @override
  void start() {}

  @override
  Future stop() async {
    cancelSync();
    if (ringDrainRecoveryEnabled) await _activeReadDone?.future;
    await _notifyStream?.cancel();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    if (ringDrainRecoveryEnabled && _isSyncing) return null;
    if (_device == null) {
      Logger.debug('RingStorageSync.syncAll: _device is null');
      return null;
    }

    final wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    if (wals.isEmpty) return null;

    _resetSyncState();
    _isSyncing = true;
    if (independentDiscovery) listener.onWalUpdated();
    DebugLogManager.logInfo('RingStorageSync: Starting sync');

    final resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    try {
      for (final wal in wals) {
        if (_isCancelled) break;
        final complete = await _syncRing(wal, progress: progress);
        _syncPhase = 'finalize';
        if (!complete) {
          // Leave wal.status as miss so the next sync session retries it.
          // This preserves the "resume from same read_seq" guarantee — pairing
          // with the no-advance-on-failure invariant in _syncRing.
          Logger.debug(
            'RingStorageSync: Ring transfer incomplete; unadvanced records preserved, will resume next sync',
          );
          listener.onWalUpdated();
          break;
        }
        wal.status = WalStatus.synced;
        wal.deviceDownloadFraction = null;
        listener.onWalUpdated();
      }
    } catch (e, st) {
      Logger.debug('RingStorageSync.syncAll: error: $e');
      DebugLogManager.logError(e, st, 'RingStorageSync failed', {
        'device': _device?.id,
        'error': e.toString(),
        'phase': _syncPhase,
      });
    } finally {
      _isSyncing = false;
      if (independentDiscovery) listener.onWalUpdated();
      for (final w in _wals) {
        w.deviceDownloadFraction = null;
      }
    }

    progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    if (ringDrainRecoveryEnabled && _isSyncing) throw StateError('Ring read already in progress');
    _resetSyncState();
    _isSyncing = true;
    // A recording page can hold a Wal from before setDevice() rebuilt the list,
    // so mark the listed instance the sync UI reads.
    final walToSync = _wals.where((w) => w.storage == wal.storage && w.id == wal.id).firstOrNull ?? wal;
    walToSync.isSyncing = true;
    walToSync.syncStartedAt = DateTime.now();
    walToSync.syncMethod = SyncMethod.ble;
    listener.onWalUpdated();
    try {
      progress?.onWalSyncedProgress(0.0);
      final complete = await _syncRing(walToSync, progress: progress);
      if (!complete) {
        // Like an incomplete syncAll: unadvanced records stay on the device and
        // the wal stays miss, but the caller must not report a finished transfer.
        throw Exception('Device transfer incomplete; recording kept on device');
      }
      walToSync.status = WalStatus.synced;
      progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
    } catch (e) {
      Logger.debug('RingStorageSync.syncWal: error: $e');
      rethrow;
    } finally {
      _isSyncing = false;
      for (final w in _wals) {
        w.deviceDownloadFraction = null;
      }
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      walToSync.syncSpeedKBps = null;
      walToSync.deviceDownloadFraction = null;
      walToSync.syncMethod = SyncMethod.ble;
      listener.onWalUpdated();
    }
    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  /// Pull the unread ring contents from the device, parse opus frames, register
  /// chunks with LocalWalSync, and advance the ring past what was stored.
  /// Returns true if everything unread when the pass began was dealt with.
  Future<bool> _syncRing(Wal wal, {IWalSyncProgressListener? progress}) async {
    if (!ringDrainRecoveryEnabled) return _readRing(wal, progress: progress);
    final deviceId = _device?.id;
    if (deviceId == null || _readOwners.containsKey(deviceId)) return false;
    final owner = Object();
    _readOwners[deviceId] = owner;
    final done = Completer<void>();
    _activeReadDone = done;
    try {
      return await _readRing(wal, progress: progress);
    } finally {
      _persistenceTimer?.cancel();
      _persistenceTimer = null;
      _cancelRead = null;
      _sourceConnection = null;
      _sourceEpoch = null;
      _sourceStop = null;
      _activeReadDone = null;
      if (identical(_readOwners[deviceId], owner)) _readOwners.remove(deviceId);
      done.complete();
    }
  }

  Future<bool> _readRing(Wal wal, {IWalSyncProgressListener? progress}) async {
    if (_device == null) return false;
    _syncPhase = 'connection';
    final deviceId = _device!.id;
    final admittedGeneration = _localSync?.sessionGeneration ?? -1;
    final connection = _testConnection ??
        await (_connectionResolver?.call(deviceId) ?? ServiceManager.instance().device.ensureConnection(deviceId));
    if (connection == null) {
      if (!ringDrainRecoveryEnabled) throw Exception('Device not connected');
      DebugLogManager.logEvent('pendant_custody', {'action': 'read_deferred', 'reason': 'disconnected'});
      return false;
    }

    if (_isCancelled || _device?.id != deviceId || (_localSync?.sessionGeneration ?? -1) != admittedGeneration) {
      return false;
    }
    _activeSyncDeviceId = deviceId;
    _downloadStartTime = DateTime.now();
    _totalBytesDownloaded = 0;

    final epoch = connection.ringCustodyEpoch;
    _sourceConnection = connection;
    _sourceEpoch = epoch;
    bool stillEpoch() =>
        connection.ringCustodyEpoch == epoch &&
        !_isCancelled &&
        _device?.id == deviceId &&
        (_localSync?.sessionGeneration ?? -1) == admittedGeneration;

    _syncPhase = 'list-read';
    await connection.ringCustodyReady;
    if (!stillEpoch()) return false;

    // Snapshot ring state so we know what range we're consuming.
    final initialInfo = await connection.getRingInfo();
    if (!stillEpoch()) return false;
    if (initialInfo == null) {
      Logger.debug('RingStorageSync._syncRing: getRingInfo returned null');
      return false;
    }
    var ringInfo = initialInfo;
    if (ringInfo.unreadPackets <= 0) {
      Logger.debug('RingStorageSync._syncRing: nothing to read');
      return true;
    }
    if (ringInfo.droppedPackets > 0) {
      DebugLogManager.logWarning('RingStorageSync: ring overwrote ${ringInfo.droppedPackets} packets before sync', {
        'ringInfo': ringInfo.toString(),
      });
    }
    final status = await connection.getRingStatus();
    if (!stillEpoch()) return false;
    final rtcValid = status?.isRtcValid ?? false;
    final phoneNow = _clock().millisecondsSinceEpoch ~/ 1000;
    final custodyDeviceId = deviceId;
    final effectiveCaps = connection.ringEffectiveCaps;
    final ringId = (effectiveCaps & RingProtocol.capRingId) != 0 ? ringInfo.ringId : null;
    if (ringId != null && !_custody.hasConnection(custodyDeviceId, epoch)) {
      if (!stillEpoch()) return false;
      await _custody.beginConnection(
        custodyDeviceId,
        epoch,
        ringInfo,
        sessionToken: Object(),
        effectiveCaps: effectiveCaps,
        replayAdvance: (seq) async =>
            (await connection.advanceRingCustody(seq, expectedEpoch: epoch, expectedRingId: ringId))?.status,
      );
      if (!stillEpoch()) return false;
      if (ringDrainRecoveryEnabled) {
        // beginConnection can replay an ACK. Do not feed its older INFO back
        // into custody or start a READ at the pre-replay frontier.
        final afterReplay = await connection.getRingInfo();
        if (!stillEpoch() || afterReplay == null || afterReplay.ringId != ringId) return false;
        ringInfo = afterReplay;
      }
    }
    Future<void> advanceDurablePrefix(String reason) async {
      if (ringId == null || (effectiveCaps & RingProtocol.capAppAckReclaim) == 0) return;
      if (connection.ringCustodyEpoch != epoch || _localSync?.sessionGeneration != admittedGeneration) return;
      try {
        final target = await _custody.validatedAdvanceTarget(custodyDeviceId, epoch, ringId);
        if (target == null || _localSync?.sessionGeneration != admittedGeneration) {
          return;
        }
        await _custodyAdvance(connection, custodyDeviceId, epoch, target, ringId, reason: reason);
      } catch (error) {
        // The durable receipt survives a failed ACK/checkpoint write. Never
        // turn a recoverable transport failure into another audio download.
        Logger.debug('RingStorageSync: durable advance deferred: $error');
      }
    }

    if (ringDrainRecoveryEnabled && ringId != null) {
      _custody.noteInfo(custodyDeviceId, epoch, ringInfo);
      await _custody.restoreDownloadedRanges(custodyDeviceId, epoch, ringId, reportedReadSeq: ringInfo.readSeq);
      await advanceDurablePrefix('before_read');
      if (!stillEpoch()) return false;
      final fresh = await connection.getRingInfo();
      if (!stillEpoch() || fresh == null || fresh.ringId != ringId) return false;
      ringInfo = fresh;
      _custody.noteInfo(custodyDeviceId, epoch, fresh);
      if (fresh.unreadPackets <= 0) return true;
    }
    if (!stillEpoch()) return false;
    final droppedKey = '$custodyDeviceId:${ringInfo.ringId}';
    final lastDropped = _droppedBaseline[droppedKey];
    final droppedDelta = lastDropped == null ? null : (ringInfo.droppedPackets - lastDropped).clamp(0, 1 << 62);
    _droppedBaseline[droppedKey] = ringInfo.droppedPackets;

    final pass = _RingPass(
      wal: wal,
      progress: progress,
      connection: connection,
      epoch: epoch,
      ringInfo: ringInfo,
      rtcValid: rtcValid,
      phoneNow: phoneNow,
      deviceId: custodyDeviceId,
      effectiveCaps: effectiveCaps,
      ringId: ringId,
      droppedDelta: droppedDelta,
      admittedGeneration: admittedGeneration,
    );

    // Firmware that frees ring space by itself keeps the single read to the
    // write head it has always had.
    if (ringId == null || (effectiveCaps & RingProtocol.capAppAckReclaim) == 0) {
      return await _readRingRange(pass, pass.startSeq, null) != null;
    }

    // Where the phone owns reclaim, the pass is a series of bounded reads. One
    // read to the write head could be an hour of transfer with the phone falling
    // behind on storing it, and whatever was still in memory when the link
    // dropped was fetched again on the next pass.
    if (_custody.liveProofStartSeq(custodyDeviceId, epoch) != null) {
      // Let the mark for the commit this INFO reported arrive before judging.
      await Future<void>.delayed(_liveMarkSettle);
      if (!stillEpoch()) return false;
    }
    if (_custody.liveRunCoversUnread(custodyDeviceId, epoch, ringInfo)) {
      Logger.debug('RingStorageSync._syncRing: unread records are the live tail, nothing to fetch');
      return true;
    }
    final passStartedAt = DateTime.now();
    var next = pass.startSeq;
    var recordsReleasedUnread = 0;
    var recordsLeftToLiveProof = 0;
    var reads = 0;
    var complete = false;
    try {
      while (stillEpoch()) {
        final acknowledged = _custody.acknowledgedReadSeqFor(custodyDeviceId, epoch, ringId);
        if (ringDrainRecoveryEnabled && acknowledged != null && acknowledged > next) {
          recordsReleasedUnread += acknowledged - next;
          next = acknowledged;
          pass.breakContinuity();
        }
        if (next >= pass.endSeq) {
          complete = true;
          break;
        }
        // Audio the phone already holds durably (it arrived live, or an earlier
        // read stored it) is released without being transferred again.
        final proven = await _custody.validatedAdvanceTarget(custodyDeviceId, epoch, ringId);
        if (!stillEpoch() || (ringDrainRecoveryEnabled && _localSync?.sessionGeneration != admittedGeneration)) break;
        if (proven != null &&
            proven > next &&
            await _custodyAdvance(connection, custodyDeviceId, epoch, proven, ringId)) {
          recordsReleasedUnread += proven - next;
          next = proven;
          pass.breakContinuity();
          continue;
        }
        // From where this connection's live marks begin, the live proof releases
        // records as the phone stores them. Read only what lies before that.
        final liveFrom = _custody.liveProofStartSeq(custodyDeviceId, epoch);
        var readEnd = pass.endSeq;
        if (liveFrom != null && _custody.liveMarksReach(custodyDeviceId, epoch, pass.endSeq)) {
          if (next >= liveFrom) {
            recordsLeftToLiveProof = pass.endSeq - next;
            complete = true;
            break;
          }
          readEnd = math.min(readEnd, liveFrom);
        }
        if (!stillEpoch()) break;
        final after = await _readRingRange(pass, next, math.min(readEnd - next, _windowRecords));
        if (after == null || after <= next) break;
        reads++;
        next = after;
        if (independentDiscovery && stillEpoch()) {
          final snapshot = await connection.getRingInfo();
          if (stillEpoch() && snapshot?.ringId == ringId) {
            _publishBacklog(connection, deviceId, snapshot!, wal.codec, reading: true);
          }
        }
      }
    } finally {
      DebugLogManager.logEvent('pendant_custody', {
        'action': 'sync_pass',
        'ring_id': ringId,
        'start_seq': pass.startSeq,
        'end_seq': pass.endSeq,
        'reached_seq': next,
        'complete': complete,
        'reads': reads,
        'records_downloaded': pass.recordsDownloaded,
        'records_credited': pass.recordsCredited,
        'records_deduped': pass.recordsDeduped,
        'records_released_unread': recordsReleasedUnread,
        'records_left_to_live_proof': recordsLeftToLiveProof,
        'duration_ms': DateTime.now().difference(passStartedAt).inMilliseconds,
      });
    }
    return complete;
  }

  /// Reads [readStart, readStart + packetCount), or to the write head when
  /// [packetCount] is null, stores it and advances the pendant past it.
  /// Returns the next unread sequence, or null when the range did not complete
  /// (the records already stored stay stored; the pendant keeps the rest).
  Future<int?> _readRingRange(_RingPass pass, int readStart, int? packetCount) async {
    final wal = pass.wal;
    final progress = pass.progress;
    final connection = pass.connection;
    final epoch = pass.epoch;
    bool stillEpoch() =>
        connection.ringCustodyEpoch == epoch &&
        !_isCancelled &&
        _device?.id == pass.deviceId &&
        (_localSync?.sessionGeneration ?? -1) == pass.admittedGeneration;
    if (!stillEpoch()) return null;
    final ringInfo = pass.ringInfo;
    final rtcValid = pass.rtcValid;
    final custodyDeviceId = pass.deviceId;
    final effectiveCaps = pass.effectiveCaps;
    final ringId = pass.ringId;
    final droppedDelta = pass.droppedDelta;
    final admittedGeneration = pass.admittedGeneration;
    // One read's worth of live-proof checks; see [CustodyProofMemo].
    final proofMemo = CustodyProofMemo();
    final phoneNow = pass.phoneNow;
    bool useRecordTime(int ts) => rtcValid && useDeviceCaptureTime(ts, phoneNow);
    _persistenceTimer?.cancel();
    _persistenceTimer = null;
    _sourceStop = null;
    CustodyReadValidation? readValidator;
    Future<void> advanceDurablePrefix(String reason) async {
      if (ringId == null || (effectiveCaps & RingProtocol.capAppAckReclaim) == 0) return;
      if (connection.ringCustodyEpoch != epoch || _localSync?.sessionGeneration != admittedGeneration) return;
      try {
        final target =
            await _custody.validatedAdvanceTarget(custodyDeviceId, epoch, ringId, readValidator: readValidator);
        if (target == null ||
            (readValidator != null && !readValidator!.isCurrent) ||
            _localSync?.sessionGeneration != admittedGeneration) {
          return;
        }
        await _custodyAdvance(connection, custodyDeviceId, epoch, target, ringId, reason: reason);
      } catch (error) {
        // The durable receipt survives a failed ACK/checkpoint write. Never
        // turn a recoverable transport failure into another audio download.
        Logger.debug('RingStorageSync: durable advance deferred: $error');
      }
    }

    if (ringDrainRecoveryEnabled && ringId != null) readValidator = await _custody.createReadValidator();

    final completer = Completer<bool>();
    _cancelRead = () {
      if (!completer.isCompleted) completer.complete(false);
    };
    final reassembler = RingRecordReassembler();
    final List<List<int>> bytesData = []; // parsed opus frames awaiting flush
    final recordSeqs = <int>[];
    final recordFrameCounts = <int>[];
    final recordTimestamps = <int>[];
    // Per record: whether it starts a new contiguous recording (a chunk never
    // spans one), and the estimated-clock run it belongs to (null = device clock).
    final recordBreaks = <bool>[];
    final recordRuns = <String?>[];
    bool clockWarningReported = false;
    int? lastRecordTs = pass.lastRecordTs;
    int? lastRawRecordTs = pass.lastRawRecordTs;
    String? currentRun = pass.clockRun;
    int provenSeq = readStart;
    int skippedDuplicates = 0;
    bool skippedProofGap = false;
    int recordsConsumed = 0;
    int? firstRecordTs = pass.firstRecordTs;
    int elapsedTotal = pass.elapsedFrames;
    int bufferBaseElapsed = pass.elapsedFrames;
    final fps = wal.codec.getFramesPerSecond();
    final chunkFrames = sdcardChunkSizeSecs * fps;
    int? doneNextSeq;
    bool doneOk = false;
    int? beginStartSeq;
    int? beginPacketCount;
    bool flushError = false;
    Future<void>? inFlightFlush;
    Timer? firstDataTimer;
    Timer? idleTimer;
    bool idleExpired = false;
    bool acceptingNotifications = true;
    bool firstDataReceived = false;
    int radioBytes = 0;
    int queuedNotifications = 0;
    DateTime lastRadioReport = DateTime.now();
    DateTime lastProgressUpdate = DateTime.now();
    const progressInterval = Duration(milliseconds: 200);

    // Independent from radio DATA/DONE. Once storage work is outstanding,
    // only a completed queue operation / indexed chunk renews this deadline.
    // Timeout stops admission and BLE; an uncancellable OS write keeps the
    // owner fenced until it actually settles, never a second overlapping read.
    void persistenceProgress({bool startOnly = false}) {
      if (!ringDrainRecoveryEnabled || _isCancelled) return;
      if (startOnly && _persistenceTimer != null) return;
      _persistenceTimer?.cancel();
      _persistenceTimer = _persistenceDeadlineTimer(const Duration(seconds: 45), () {
        DebugLogManager.logEvent('pendant_custody', {'action': 'persistence_timeout', 'ring_id': ringId});
        cancelSync();
      });
    }

    void receivedTransferData() {
      firstDataReceived = true;
      firstDataTimer?.cancel();
      idleTimer?.cancel();
      idleTimer = _transferTimer(const Duration(seconds: 15), () {
        if (!completer.isCompleted) {
          Logger.debug('RingStorageSync: no transfer data within 15s; stopping incomplete read');
          idleExpired = true;
          completer.complete(false);
        }
      });
    }

    List<(int, int)> contiguousRanges(List<int> seqs) {
      final ranges = <(int, int)>[];
      var start = seqs.first, prev = seqs.first;
      for (var i = 1; i < seqs.length; i++) {
        if (seqs[i] != prev + 1) {
          ranges.add((start, prev + 1));
          start = seqs[i];
        }
        prev = seqs[i];
      }
      ranges.add((start, prev + 1));
      return ranges;
    }

    // Flush exactly [chunkFrames] frames at a time; on DONE, flush whatever is left.
    Future<void> flushChunks({required bool finalFlush}) async {
      while (recordFrameCounts.isNotEmpty) {
        var framesToTake = 0;
        var recordsToTake = 0;
        for (var i = 0; i < recordFrameCounts.length; i++) {
          if (framesToTake >= chunkFrames && recordsToTake > 0) break;
          if (recordsToTake > 0 && recordBreaks[i]) break;
          framesToTake += recordFrameCounts[i];
          recordsToTake++;
        }
        final endsAtBreak = recordsToTake < recordBreaks.length && recordBreaks[recordsToTake];
        if (!finalFlush && framesToTake < chunkFrames && !endsAtBreak) break;
        if (finalFlush && recordsToTake == 0 && bytesData.isEmpty) break;

        final chunkSeqs = recordSeqs.sublist(0, recordsToTake);
        final chunk = bytesData.sublist(0, framesToTake);
        var chunkTimerStart = (recordTimestamps.isNotEmpty && useRecordTime(recordTimestamps.first))
            ? recordTimestamps.first
            : !deviceCaptureClockRepairOff && firstRecordTs == 0
                ? 0
                : (firstRecordTs ?? DateTime.now().millisecondsSinceEpoch ~/ 1000) +
                    bufferBaseElapsed ~/ (fps > 0 ? fps : 1);
        final chunkClockRun = recordRuns.isNotEmpty ? recordRuns.first : null;
        final flushStartedAt = DateTime.now().millisecondsSinceEpoch;
        try {
          // An empty record still needs durable, indexed accounting. Leave
          // ambiguous/legacy zero-frame ranges unproven when receipts are OFF.
          if (chunk.isEmpty && (!ringDrainRecoveryEnabled || ringId == null)) {
            throw StateError('Empty ring records require indexed markers');
          }
          // Capture time is metadata, never admission to phone custody. If
          // estimation fails, preserve every decoded byte with explicit unknown
          // time (zero + clock-run), without manufacturing a calendar date.
          if (!deviceCaptureClockRepairOff &&
              chunkClockRun != null &&
              (!phoneCaptureClockPlausible(phoneNow) || !deviceCaptureTimePlausible(chunkTimerStart, phoneNow))) {
            chunkTimerStart = 0;
          }
          final localSync = _localSync;
          if (localSync == null) throw StateError('LocalWalSync unavailable; refusing release');
          try {
            final indexedRing = ringDrainRecoveryEnabled ? ringId : null;
            if (indexedRing != null && chunkSeqs.last - chunkSeqs.first + 1 != chunkSeqs.length) {
              throw StateError('Ring chunk crosses an unproven sequence gap');
            }
            final localWal = chunk.isEmpty
                ? await localSync.persistEmptyRingRecords(
                    source: wal,
                    ringId: ringId!,
                    start: chunkSeqs.first,
                    end: chunkSeqs.last + 1,
                    admittedGeneration: admittedGeneration)
                : await localSync.persistDeviceChunk(
                    source: wal,
                    frames: chunk,
                    timerStart: chunkTimerStart,
                    admittedGeneration: admittedGeneration,
                    clockRun: chunkClockRun,
                    downloadRingId: indexedRing,
                    downloadSeqStart: indexedRing != null ? chunkSeqs.first : null,
                    downloadSeqEnd: indexedRing != null ? chunkSeqs.last + 1 : null,
                    nextCollisionSequence: () => _storageFileSeq++);
            if (ringDrainRecoveryEnabled && ringId != null) {
              readValidator = await _custody.createReadValidator();
            }
            final file = File((await Wal.getFilePath(localWal.filePath))!);
            final fileBytes = await file.length();
            if (ringDrainRecoveryEnabled && localSync.sessionGeneration != admittedGeneration) {
              throw StateError('Ring chunk belongs to a retired account session');
            }
            for (final s in chunkSeqs) {
              if (s == provenSeq) provenSeq = s + 1;
            }
            if (ringId != null && (ringDrainRecoveryEnabled || connection.ringCustodyEpoch == epoch)) {
              for (final range in contiguousRanges(chunkSeqs)) {
                await _custody.recordDurableRingRange(custodyDeviceId, epoch, ringId, range.$1, range.$2, [
                  CustodyWalRef(
                    fileName: file.path.split('/').last,
                    bytes: fileBytes,
                    frames: chunk.length,
                    fileSha256: localWal.fileSha256,
                    ownerUid: ringDrainRecoveryEnabled ? localWal.ownerUid : null,
                    downloadRingId: indexedRing,
                    downloadSeqStart: indexedRing != null ? chunkSeqs.first : null,
                    downloadSeqEnd: indexedRing != null ? chunkSeqs.last + 1 : null,
                    downloadDeviceId: indexedRing != null ? custodyDeviceId : null,
                  ),
                ]);
              }
            }
            persistenceProgress();
            if (independentDiscovery && stillEpoch() && chunk.isNotEmpty) {
              final wake = onDurableChunk;
              final now = _clock();
              final last = _lastUploadWake;
              if (wake != null && (last == null || now.difference(last) >= const Duration(seconds: 30))) {
                _lastUploadWake = now;
                wake();
              }
            } else if (!independentDiscovery) {
              RecordingTransferCoordinator.instance.noteDeviceProgress();
            }
            DebugLogManager.logEvent('pendant_custody', {
              'action': 'chunk_durable',
              'device': custodyDeviceId,
              'ring_id': ringId,
              'start_seq': chunkSeqs.first,
              'end_seq': chunkSeqs.last + 1,
              'durable_flush_latency_ms': DateTime.now().millisecondsSinceEpoch - flushStartedAt,
            });
            recordSeqs.removeRange(0, recordsToTake);
            recordFrameCounts.removeRange(0, recordsToTake);
            recordTimestamps.removeRange(0, recordsToTake);
            recordBreaks.removeRange(0, recordsToTake);
            recordRuns.removeRange(0, recordsToTake);
            bytesData.removeRange(0, framesToTake);
            bufferBaseElapsed = elapsedTotal - bytesData.length;
            final managerFrontier = ringId != null ? _custody.durableFrontierFor(custodyDeviceId, epoch) : null;
            if (managerFrontier != null && managerFrontier > provenSeq) provenSeq = managerFrontier;
            if (ringId != null && (effectiveCaps & RingProtocol.capAppAckReclaim) != 0) {
              if (ringDrainRecoveryEnabled) {
                await advanceDurablePrefix('chunk');
              } else {
                final target = await _custody.validatedAdvanceTarget(custodyDeviceId, epoch, ringId);
                if (target != null) await _custodyAdvance(connection, custodyDeviceId, epoch, target, ringId);
              }
            }
          } catch (e) {
            rethrow;
          }
        } catch (e) {
          Logger.debug('RingStorageSync._syncRing: flush error: $e');
          flushError = true;
          rethrow;
        }
        if (finalFlush && recordFrameCounts.isEmpty) break;
      }
    }

    await _notifyStream?.cancel();

    Future<void> notifyQueue = Future.value();
    bool beginAborted = false;

    Future<void> handleNotification(List<int> value) async {
      // An idle timeout stops new admission, not the queue of bytes already
      // received from BLE. Those bytes may be waiting behind a durable flush.
      if (completer.isCompleted && !idleExpired) return;
      if (_isCancelled) {
        if (!completer.isCompleted) completer.complete(false);
        return;
      }
      if (value.isEmpty) return;

      final opcode = value[0];
      if (opcode == RingProtocol.notifyAck) {
        // ACK from a CMD we didn't initiate here (e.g. CLEAR/STOP). Ignore.
        return;
      }
      if (opcode == RingProtocol.notifyInfo) {
        // Late INFO response; we already have ringInfo. Ignore.
        return;
      }
      if (opcode == RingProtocol.notifyReadBegin) {
        final begin = RingProtocol.parseReadBeginNotification(value);
        if (begin != null) {
          Logger.debug('RingStorageSync: NOTIFY_READ_BEGIN start=${begin.transferStartSeq} count=${begin.packetCount}');
          beginStartSeq = begin.transferStartSeq;
          beginPacketCount = begin.packetCount;
          if (beginStartSeq != readStart) {
            Logger.debug('RingStorageSync: READ_BEGIN start $beginStartSeq != requested $readStart — aborting');
            beginAborted = true;
            if (!completer.isCompleted) completer.complete(false);
          }
        }
        return;
      }
      if (opcode == RingProtocol.notifyDone) {
        final done = RingProtocol.parseDoneNotification(value);
        if (done == null) {
          Logger.debug('RingStorageSync: NOTIFY_DONE truncated (${value.length} bytes)');
          if (!completer.isCompleted) completer.complete(false);
          return;
        }
        doneNextSeq = done.nextSeq;
        doneOk = done.isOk;
        Logger.debug('RingStorageSync: NOTIFY_DONE status=${done.status} next_seq=$doneNextSeq');
        if (!completer.isCompleted) completer.complete(true);
        return;
      }
      if (opcode == RingProtocol.notifyLiveMark) {
        return;
      }
      if (opcode != RingProtocol.notifyData) {
        Logger.debug('RingStorageSync: unknown notification opcode 0x${opcode.toRadixString(16)}');
        return;
      }

      // NOTIFY_DATA: append payload (skip the leading opcode byte) to the
      // reassembler. The firmware does NOT align chunks to record boundaries.
      final payload = value.sublist(1);
      if (payload.isEmpty) return;
      reassembler.append(payload);
      _updateSpeed(payload.length);

      final records = reassembler.drainRecords();
      final intervalStart = readStart + recordsConsumed;
      final durableNow = ringDrainRecoveryEnabled && ringId != null && records.isNotEmpty
          ? await _custody.validatedRecordRanges(custodyDeviceId, epoch, ringId,
              startSeq: intervalStart, endSeq: intervalStart + records.length, readValidator: readValidator)
          : const <(int, int)>[];
      for (final record in records) {
        final seq = readStart + recordsConsumed;
        recordsConsumed += 1;
        final rawTs = RingProtocol.readRecordTimestamp(record);
        // Normalize only presentation time. seq/ringId and every durability
        // proof below continue to come from the untouched ring coordinates.
        final ts = deviceCaptureClockRepairOff || useRecordTime(rawTs) ? rawTs : 0;
        if (rawTs > 0 && ts == 0 && !clockWarningReported) {
          clockWarningReported = true;
          DebugLogManager.logWarning('Implausible ring timestamp; capture date estimated, byte integrity unverified', {
            'device_time_seconds': rawTs,
            'phone_time_seconds': phoneNow,
            'ring_id': ringId,
            'seq': seq,
          });
        }
        final audio = record.sublist(RingProtocol.timestampBytes);
        final frames = ringDrainRecoveryEnabled ? decodeCustodyRingAudio(audio) : RingProtocol.parseAudioPayload(audio);
        RingCustodyDiagnostics.shared.record(custodyDeviceId,
            epoch: epoch,
            ringId: ringId,
            ordinal: seq,
            record: record,
            timestamp: rawTs,
            frames: frames.length,
            phoneSeconds: phoneNow);
        elapsedTotal += frames.length;

        // Anchor timerStart on the first usable timestamp.
        if (firstRecordTs == null) {
          if (useRecordTime(ts)) {
            firstRecordTs = ts;
          } else {
            // Fallback: now - estimated duration of the unread region.
            final passRecords = math.max(1, pass.endSeq - pass.startSeq);
            final aheadRecords = (pass.endSeq - readStart).clamp(0, passRecords);
            final estSecs = (wal.totalFrames * aheadRecords ~/ passRecords) ~/ (fps == 0 ? 1 : fps);
            try {
              firstRecordTs = !deviceCaptureClockRepairOff && estSecs <= 0
                  ? 0
                  : estimatedDeviceStart(
                      deviceCaptureClockRepairOff ? _clock().millisecondsSinceEpoch ~/ 1000 : phoneNow, estSecs);
            } on StateError {
              firstRecordTs = 0; // Unknown capture time must never discard decoded audio.
            }
          }
        }

        if (durableNow.any((r) => r.$1 <= seq && seq < r.$2) ||
            ((!ringDrainRecoveryEnabled || ringId == null) &&
                await _custody.isDurableLiveRecord(custodyDeviceId, ringId, seq, memo: proofMemo))) {
          skippedDuplicates++;
          skippedProofGap = true;
          if (seq == provenSeq) provenSeq = seq + 1;
          continue;
        }

        final lastUsableRecordTs = lastRecordTs;
        final boundary = ringRecordClockBoundary(
          previousTs: lastRecordTs,
          ts: ts,
          rtcValid: rtcValid,
          currentRun: currentRun,
        );
        // Invalid wall time cannot place audio on a calendar, but a reset or
        // jump still forbids claiming that two stretches share one clock run.
        final rawStep = lastRawRecordTs == null ? null : rawTs - lastRawRecordTs!;
        final untrustedBreak = !deviceCaptureClockRepairOff &&
            ts == 0 &&
            ((lastUsableRecordTs != null && lastUsableRecordTs > 0) ||
                (rtcValid &&
                    rawTs > 0 &&
                    lastRawRecordTs != null &&
                    lastRawRecordTs! > 0 &&
                    (rawStep! < 0 || rawStep > ringRecordGapBreakSeconds)));
        currentRun = untrustedBreak ? Wal.newClockRun() : boundary.run;
        lastRecordTs = ts;
        lastRawRecordTs = rawTs;

        recordSeqs.add(seq);
        recordTimestamps.add(ts);
        recordFrameCounts.add(frames.length);
        recordBreaks.add(boundary.breaks || untrustedBreak || (ringDrainRecoveryEnabled && skippedProofGap));
        skippedProofGap = false;
        recordRuns.add(currentRun);
        bytesData.addAll(frames);
      }

      // Throttled progress update.
      final now = DateTime.now();
      if (now.difference(lastProgressUpdate) >= progressInterval) {
        lastProgressUpdate = now;
        if (wal.storageTotalBytes > 0) {
          final consumedBytes = (pass.recordsCredited + recordsConsumed) * RingProtocol.recordSize;
          final pct = (consumedBytes / wal.storageTotalBytes).clamp(0.0, 1.0);
          wal.deviceDownloadFraction = pct;
          wal.syncSpeedKBps = _currentSpeedKBps;
          final remainingBytes = wal.storageTotalBytes - consumedBytes;
          wal.syncEtaSeconds = _currentSpeedKBps > 0 ? (remainingBytes / 1024 / _currentSpeedKBps).round() : null;
          progress?.onWalSyncedProgress(pct, speedKBps: _currentSpeedKBps, phase: SyncPhase.downloadingFromDevice);
          listener.onWalUpdated();
        }
      }

      // Flush full chunks as we go (data safety: even if BLE drops mid-stream,
      // already-flushed chunks land in LocalWalSync and reach the cloud).
      //
      // Single in-flight flush at a time. flushChunks loops while bytesData
      // has >= chunkFrames, so additional NOTIFY_DATA arriving during a flush
      // are absorbed by the in-flight task's next iteration. Without this
      // guard, two concurrent flush closures would both read chunkTimerStart
      // before either updated it, producing overlapping timestamps in
      // LocalWalSync. We hold the Future so the post-DONE final flush can
      // await any flush still in flight before draining the tail.
      if (inFlightFlush == null && bytesData.length >= chunkFrames) {
        inFlightFlush = () async {
          try {
            await flushChunks(finalFlush: false);
          } catch (_) {
            if (!completer.isCompleted) completer.complete(false);
          } finally {
            inFlightFlush = null;
          }
        }();
      }
    }

    if (!stillEpoch()) return null;
    _syncPhase = 'transfer';
    _notifyStream = await connection.getBleStorageBytesListener(
      onStorageBytesReceived: (List<int> value) {
        if (!acceptingNotifications || completer.isCompleted) return;
        if (ringDrainRecoveryEnabled &&
            (connection.ringCustodyEpoch != epoch || _localSync?.sessionGeneration != admittedGeneration)) {
          if (!completer.isCompleted) completer.complete(false);
          return;
        }
        final snapshot = List<int>.of(value);
        final opcode = snapshot.isEmpty ? null : snapshot.first;
        final begin = opcode == RingProtocol.notifyReadBegin ? RingProtocol.parseReadBeginNotification(snapshot) : null;
        if (ringDrainRecoveryEnabled && opcode == RingProtocol.notifyData && snapshot.length > 1) {
          radioBytes += snapshot.length - 1;
          final now = DateTime.now();
          if (now.difference(lastRadioReport) >= const Duration(seconds: 30)) {
            lastRadioReport = now;
            DebugLogManager.logEvent('pendant_custody', {
              'action': 'read_progress',
              'ring_id': ringId,
              'radio_data_bytes': radioBytes,
              'processed_records': recordsConsumed,
              'queued_notifications': queuedNotifications,
              'buffered_frames': bytesData.length,
              'elapsed_ms': now.difference(_downloadStartTime!).inMilliseconds,
            });
          }
        }
        // Observe radio progress before queueing disk/custody work: a slow
        // flush must not masquerade as a silent peripheral. Control chatter
        // and empty DATA cannot extend the transfer's lifetime.
        if ((opcode == RingProtocol.notifyData && snapshot.length > 1) ||
            (!firstDataReceived && begin?.transferStartSeq == readStart)) {
          receivedTransferData();
        } else if (opcode == RingProtocol.notifyDone && RingProtocol.parseDoneNotification(snapshot) != null) {
          // Radio delivery has ended; validating DONE may still be queued
          // behind custody I/O. Ownership remains held while that work settles.
          idleTimer?.cancel();
        }
        persistenceProgress(startOnly: true);
        queuedNotifications++;
        notifyQueue = notifyQueue.then((_) => handleNotification(snapshot)).whenComplete(() {
          queuedNotifications--;
          if (inFlightFlush == null) {
            if (queuedNotifications == 0) {
              _persistenceTimer?.cancel();
              _persistenceTimer = null;
            } else {
              persistenceProgress();
            }
          }
        }).catchError((e) {
          Logger.debug('RingStorageSync: notification handler error: $e');
          if (!completer.isCompleted) completer.complete(false);
        });
      },
    );

    if (_notifyStream == null) {
      throw Exception('Failed to set up storage listener');
    }
    _notifyStream!.onDone(() {
      if (!completer.isCompleted) {
        Logger.debug('RingStorageSync: BLE stream closed mid-transfer');
        completer.complete(false);
      }
    });

    firstDataTimer = Timer(const Duration(seconds: 5), () {
      if (!firstDataReceived && !completer.isCompleted) {
        Logger.debug('RingStorageSync: no data within 5s');
        if (ringDrainRecoveryEnabled) {
          completer.complete(false);
        } else {
          completer.completeError(TimeoutException('No data from device'));
        }
      }
    });

    // Kick off the read. No packet_count = stream everything from read_seq.
    if (!stillEpoch()) {
      acceptingNotifications = false;
      firstDataTimer.cancel();
      idleTimer?.cancel();
      await _notifyStream?.cancel();
      _notifyStream = null;
      return null;
    }
    bool reachedDone = false;
    bool stopSent = false;
    try {
      if (independentDiscovery) {
        DebugLogManager.logEvent('pendant_custody', {
          'action': 'ring_reader_started',
          'device': custodyDeviceId,
          'ring_id': ringId,
          'connection_epoch': epoch,
          'start_seq': readStart,
        });
      }
      final readOk = await connection.readRingFromSeq(readStart, packetCount: packetCount, canStart: stillEpoch);
      if (!readOk) throw StateError('Failed to send CMD_RING_READ');
      Logger.debug(
        'RingStorageSync: reading from seq=$readStart count=${packetCount ?? "all"} (write=${ringInfo.writeSeq}, unread=${ringInfo.unreadPackets})',
      );
      reachedDone = ringDrainRecoveryEnabled
          ? await waitForRingRead(completer.future)
          : await completer.future.timeout(packetCount == null ? _fullReadTimeout : _windowReadTimeout);
    } catch (e, st) {
      Logger.debug('RingStorageSync: transfer error: $e');
      DebugLogManager.logError(e, st, 'RingStorageSync failed', {
        'device': custodyDeviceId,
        'error': e.toString(),
        'phase': _syncPhase,
      });
    } finally {
      acceptingNotifications = false;
      firstDataTimer.cancel();
      idleTimer?.cancel();
      if (_isCancelled || !(reachedDone && doneOk)) {
        await _stopRingTransfer(connection, epoch);
        stopSent = true;
      }
      await _notifyStream?.cancel();
      _notifyStream = null;
    }

    try {
      await notifyQueue;
    } catch (_) {}

    // Wait for any flush still in flight from the streaming phase before
    // draining the tail — otherwise the final flush could race the in-flight
    // one on bytesData and recordTimestamps.
    _syncPhase = 'finalize';
    final pendingFlush = inFlightFlush;
    if (pendingFlush != null) {
      try {
        await pendingFlush;
      } catch (e) {
        Logger.debug('RingStorageSync: in-flight flush error during settle: $e');
      }
    }

    // Flush whatever frames are buffered, even on partial failure — those frames
    // are safe to upload to cloud regardless. ADVANCE is gated separately.
    persistenceProgress(startOnly: true);
    try {
      await flushChunks(finalFlush: true);
    } catch (e) {
      Logger.debug('RingStorageSync: final flush error: $e');
    }
    if (ringDrainRecoveryEnabled) await advanceDurablePrefix('read_exit');
    if (ringDrainRecoveryEnabled) {
      DebugLogManager.logEvent('pendant_custody', {
        'action': 'read_exit',
        'device': custodyDeviceId,
        'connection_epoch': epoch,
        'start_seq': readStart,
        'ring_id': ringId,
        'radio_data_bytes': radioBytes,
        'processed_records': recordsConsumed,
        'deduped': skippedDuplicates,
        'reached_done': reachedDone,
        'cancelled': _isCancelled,
        'idle_expired': idleExpired,
      });
    }

    final beginConsistent = !beginAborted &&
        (beginStartSeq == null ||
            (beginStartSeq == readStart && (beginPacketCount == null || beginPacketCount == recordsConsumed)));
    final doneConsistent = doneNextSeq != null &&
        doneNextSeq == readStart + recordsConsumed &&
        reassembler.pendingBytes == 0 &&
        beginConsistent;
    final fullyProven = doneNextSeq != null && provenSeq >= doneNextSeq!;
    final advancedOk = reachedDone &&
        doneOk &&
        !flushError &&
        !_isCancelled &&
        doneConsistent &&
        fullyProven &&
        (!ringDrainRecoveryEnabled || _localSync?.sessionGeneration == admittedGeneration);
    pass.recordsDownloaded += recordsConsumed;
    pass.recordsDeduped += skippedDuplicates;
    if (advancedOk) {
      final bool ok;
      if (ringDrainRecoveryEnabled && ringId != null && (effectiveCaps & RingProtocol.capAppAckReclaim) != 0) {
        ok = await _confirmWindowReclaim(pass, ringId, doneNextSeq!);
      } else {
        ok = await _custodyAdvance(connection, custodyDeviceId, epoch, doneNextSeq!, ringId);
      }
      Logger.debug('RingStorageSync: advance(seq=$doneNextSeq) -> $ok (records=$recordsConsumed)');
      DebugLogManager.logEvent('pendant_custody', {
        'action': 'sync_advance',
        'caps': effectiveCaps,
        'contract_version': ringInfo.contractVersion,
        'ring_id': ringId,
        'advance_lag_records': ringInfo.writeSeq - doneNextSeq!,
        'dropped_delta': droppedDelta,
        'records': recordsConsumed,
        'deduped': skippedDuplicates,
        'advance_ok': ok,
        'residual_legacy_risk': ringId == null,
      });
      if (!ok) return null;
      pass.recordsCredited += recordsConsumed;
      pass.lastRecordTs = lastRecordTs;
      pass.lastRawRecordTs = lastRawRecordTs;
      pass.clockRun = currentRun;
      pass.firstRecordTs = firstRecordTs;
      pass.elapsedFrames = elapsedTotal;
      return doneNextSeq;
    } else {
      Logger.debug(
        'RingStorageSync: skipping advance (reachedDone=$reachedDone doneOk=$doneOk flushError=$flushError cancelled=$_isCancelled records=$recordsConsumed doneConsistent=$doneConsistent fullyProven=$fullyProven)',
      );
      if (!stopSent) await _stopRingTransfer(connection, epoch);
      return null;
    }
  }

  Future<bool> _confirmWindowReclaim(_RingPass pass, int ringId, int endSeq) async {
    final connection = pass.connection;
    final deviceId = pass.deviceId;
    final epoch = pass.epoch;
    bool current() =>
        !_isCancelled &&
        _device?.id == deviceId &&
        connection.ringCustodyEpoch == epoch &&
        _localSync?.sessionGeneration == pass.admittedGeneration &&
        !_custody.isIncarnationInvalid(deviceId, epoch);
    bool confirmed() => (_custody.acknowledgedReadSeqFor(deviceId, epoch, ringId) ?? -1) >= endSeq;

    if (!current()) return false;
    if (confirmed()) return true;

    // A concurrent live WAL write can invalidate the READ's index snapshot.
    // Retry once with fresh proof and release only this completed window.
    try {
      final validator = await _custody.createReadValidator();
      if (!current()) return false;
      final target = await _custody.validatedAdvanceTarget(deviceId, epoch, ringId, readValidator: validator);
      if (current() && !confirmed() && validator.isCurrent && target != null && target >= endSeq) {
        await _custodyAdvance(connection, deviceId, epoch, endSeq, ringId, reason: 'window_confirm');
      }
    } catch (error) {
      Logger.debug('RingStorageSync: retrying reclaim confirmation: $error');
    }

    // A concurrent live ADVANCE can settle the window while we wait. Observe
    // its acknowledged position without repeatedly sending BLE commands.
    for (var check = 0; check < 8 && current() && !confirmed(); check++) {
      final wait = Completer<void>();
      _transferTimer(const Duration(seconds: 1), wait.complete);
      await wait.future;
    }
    if (!current()) return false;
    if (confirmed()) return true;

    try {
      final info = await connection.getRingInfo();
      if (!current() || info == null || info.ringId != ringId) return false;
      if (confirmed()) return true;
      if (info.readSeq < endSeq) return false;
      _custody.noteInfo(deviceId, epoch, info);
      return true;
    } catch (error) {
      Logger.debug('RingStorageSync: could not read reclaim position: $error');
      return false;
    }
  }

  Future<void> _stopRingTransfer(DeviceConnection connection, int epoch) {
    if (!ringDrainRecoveryEnabled) return _sendRingStop(connection, epoch);
    return _sourceStop ??= _sendRingStop(connection, epoch);
  }

  Future<void> _sendRingStop(DeviceConnection connection, int epoch) async {
    try {
      if (connection.ringCustodyEpoch != epoch) return;
      await connection.stopStorageSync();
      Logger.debug('RingStorageSync: STOP sent on the source connection');
    } catch (e) {
      Logger.debug('RingStorageSync: STOP failed: $e');
    }
  }

  Future<bool> _custodyAdvance(DeviceConnection connection, String deviceId, int epoch, int seq, int? ringId,
      {String reason = 'done'}) async {
    if (connection.ringCustodyEpoch != epoch) return false;
    if (_custody.isIncarnationInvalid(deviceId, epoch)) return false;
    final ack = await connection.advanceRingCustody(seq, expectedEpoch: epoch, expectedRingId: ringId);
    if (ringDrainRecoveryEnabled) {
      DebugLogManager.logEvent('pendant_custody', {
        'action': 'ring_advance',
        'ring_id': ringId,
        'seq': seq,
        'reason': reason,
        'ack_status': ack?.status,
      });
    }
    if (ack == null) {
      // The pendant commits an advance before acknowledging it, and the
      // acknowledgement shares the link with audio. Losing it must not cost a
      // second download of the range, so ask where the read pointer is. Only on
      // firmware whose ring id makes that answer unambiguous.
      if (ringId == null) return false;
      final info = await connection.getRingInfo();
      if (connection.ringCustodyEpoch != epoch || info == null || info.ringId != ringId) return false;
      _custody.noteInfo(deviceId, epoch, info);
      if (seq > info.readSeq) return false;
      await _custody.markAdvanced(deviceId, epoch, seq);
      return true;
    }
    if (ack.isOk) {
      await _custody.markAdvanced(deviceId, epoch, seq);
      return true;
    }
    if (ack.isSeqOutOfRange) {
      final info = await connection.getRingInfo();
      if (connection.ringCustodyEpoch != epoch || info == null) return false;
      _custody.noteInfo(deviceId, epoch, info);
      if ((ringId == null || info.ringId == ringId) && seq <= info.readSeq) {
        await _custody.markAdvanced(deviceId, epoch, seq);
        return true;
      }
      return false;
    }
    if (ack.isRingIdMismatch) {
      _custody.noteMismatch(deviceId, epoch);
      DebugLogManager.logWarning('pendant_custody ring_id mismatch; refusing release', {
        'action': 'advance_mismatch',
        'device': deviceId,
        'ring_id': ringIdOf(connection),
      });
    }
    return false;
  }

  static int? ringIdOf(DeviceConnection connection) => connection.lastRingInfo?.ringId;

  int _storageFileSeq = 0;
}
