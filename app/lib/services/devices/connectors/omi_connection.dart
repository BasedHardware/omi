import 'dart:async';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

import 'package:version/version.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';

class OmiDeviceConnection extends DeviceConnection {
  static const String settingsServiceUuid = '19b10010-e8f2-537e-4f6c-d104768a1214';
  static const String settingsDimRatioCharacteristicUuid = '19b10011-e8f2-537e-4f6c-d104768a1214';
  static const String settingsMicGainCharacteristicUuid = '19b10012-e8f2-537e-4f6c-d104768a1214';
  static const String settingsChargingStatusCharacteristicUuid = '19b10013-e8f2-537e-4f6c-d104768a1214';
  static const String featuresServiceUuid = '19b10020-e8f2-537e-4f6c-d104768a1214';
  static const String featuresCharacteristicUuid = '19b10021-e8f2-537e-4f6c-d104768a1214';

  final PendantRingCustody _custody;

  RingInfo? _lastRingInfo;
  bool _livePersistEnabled = false;
  int _ringEffectiveCaps = 0;
  Object? _custodyToken;
  int _custodyEpoch = 0;
  static int _custodyEpochAlloc = 0;
  Future<void>? _probeFuture;
  bool _custodyProbeResolved = false;
  bool _optInAttempted = false;

  Future<void> _storageCmdQueue = Future.value();

  StreamSubscription? _custodyNotifySub;

  @override
  RingInfo? get lastRingInfo => _lastRingInfo;

  @override
  int get ringEffectiveCaps => _ringEffectiveCaps;

  @override
  int get ringCustodyEpoch => _custodyEpoch;

  @override
  Future<void> get ringCustodyReady => _probeFuture ?? Future.value();

  @override
  bool get ringLivePersistEnabled => _livePersistEnabled;

  Future<T> _enqueueStorageCommand<T>(Future<T> Function() op) {
    final prev = _storageCmdQueue;
    final completer = Completer<T>();
    _storageCmdQueue = prev.then((_) async {
      try {
        completer.complete(await op());
      } catch (e, st) {
        completer.completeError(e, st);
      }
    });
    return completer.future;
  }

  OmiDeviceConnection(super.device, super.transport, {PendantRingCustody? custody})
      : _custody = custody ?? PendantRingCustody.shared {
    final t = transport;
    if (t is NativeBleTransport) {
      t.beforeAudioResubscribe = (_) => _audioResubscribeGate();
    }
  }

  int _audioSubscribers = 0;
  Completer<void>? _physicalReady = Completer<void>();
  Future<void>? _enableFuture;

  Future<void> _audioResubscribeGate() async {
    await _physicalReady?.future;
    await _enableAfterProbe();
  }

  get deviceId => device.id;

  @override
  void onPhysicalConnectionEstablished() {
    _lastRingInfo = null;
    _livePersistEnabled = false;
    _ringEffectiveCaps = 0;
    _custodyToken = Object();
    _custodyEpoch = ++_custodyEpochAlloc;
    _custodyProbeResolved = false;
    _optInAttempted = false;
    _probeFuture = null;
    _enableFuture = null;
    final ready = _physicalReady;
    final epoch = _custodyEpoch;
    final token = _custodyToken;
    unawaited(() async {
      try {
        await _probeRingCustody();
        if (_audioSubscribers > 0 && epoch == _custodyEpoch && identical(token, _custodyToken)) {
          await _enableAfterProbe();
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: custody readiness failed: $e');
      } finally {
        if (ready != null && !ready.isCompleted) ready.complete();
      }
    }());
  }

  @override
  void onPhysicalConnectionLost() {
    _endCustodySession();
    _physicalReady = Completer<void>();
  }

  void _endCustodySession() {
    final token = _custodyToken;
    _livePersistEnabled = false;
    _ringEffectiveCaps = 0;
    _lastRingInfo = null;
    _custodyToken = null;
    unawaited(_custodyNotifySub?.cancel());
    _custodyNotifySub = null;
    _custody.endConnection(device.id, _custodyEpoch, sessionToken: token);
  }

  Future<void> _probeRingCustody() {
    final existing = _probeFuture;
    if (existing != null) return existing;
    final future = _runRingCustodyProbe();
    _probeFuture = future;
    future.whenComplete(() {
      if (identical(_probeFuture, future)) _probeFuture = null;
    });
    return future;
  }

  Future<void> _runRingCustodyProbe() async {
    await _runRingCustodyProbeInner();
  }

  Future<void> _runRingCustodyProbeInner() async {
    final epoch = _custodyEpoch;
    final token = _custodyToken;
    if (token == null || _custodyProbeResolved) return;
    if (!RingProtocol.isRingBufferFirmware(device.firmwareRevision)) return;

    try {
      _custodyNotifySub = await getBleStorageBytesListener(
        onStorageBytesReceived: (value) {
          if (epoch != _custodyEpoch || token != _custodyToken || value.isEmpty) return;
          if (value[0] == RingProtocol.notifyLiveMark) {
            final mark = RingProtocol.parseLiveMarkNotification(value);
            if (mark != null) {
              _custody.observeLiveMark(device.id, epoch, mark);
            }
          } else if (value[0] == RingProtocol.notifyInfo) {
            final info = RingProtocol.parseInfoNotification(value);
            if (info != null) {
              _lastRingInfo = info;
              _noteInfoDropped(info);
              _custody.noteInfo(device.id, epoch, info);
            }
          }
        },
      );
    } catch (e) {
      Logger.debug('OmiDeviceConnection: custody notify subscribe failed: $e');
    }

    final info = await getRingInfo();
    if (epoch != _custodyEpoch || token != _custodyToken || info == null) return;
    _lastRingInfo = info;
    _noteInfoDropped(info);

    final effective = info.effectiveCaps;
    _ringEffectiveCaps = effective;
    _custodyProbeResolved = true;

    final scopedRingId = (effective & RingProtocol.capRingId) != 0 ? info.ringId : null;

    await _custody.beginConnection(
      device.id,
      epoch,
      info,
      sessionToken: token,
      effectiveCaps: effective,
      replayAdvance: (seq) async {
        if (scopedRingId == null) return null;
        final ack = await advanceRingCustody(seq, expectedEpoch: epoch, expectedRingId: scopedRingId);
        return ack?.status;
      },
      onAdvanceReady: (seq) async {
        final ack = await advanceRingCustody(seq, expectedEpoch: epoch, expectedRingId: scopedRingId);
        return ack?.status;
      },
    );
  }

  Future<void> _enableLiveCustody() async {
    await _probeRingCustody();
    await _enableAfterProbe();
  }

  Future<void> _enableAfterProbe() {
    final existing = _enableFuture;
    if (existing != null) return existing;
    final epoch = _custodyEpoch;
    final token = _custodyToken;
    if (token == null || _optInAttempted) return Future.value();
    final future = _runEnableAfterProbe(epoch, token);
    _enableFuture = future;
    unawaited(() async {
      try {
        await future;
      } catch (_) {
      } finally {
        if (identical(_enableFuture, future)) _enableFuture = null;
      }
    }());
    return future;
  }

  Future<void> _runEnableAfterProbe(int epoch, Object token) async {
    if (epoch != _custodyEpoch || token != _custodyToken || _optInAttempted) return;
    final info = _lastRingInfo;
    if (info == null || !info.capLivePersist) return;
    _optInAttempted = true;

    final ack = await enableRingCustody(info.effectiveCaps);
    if (epoch != _custodyEpoch || token != _custodyToken) return;
    if (ack == null || !ack.isOk) {
      final legacy = ack != null && ack.status == RingProtocol.ackInvalidCommand;
      Logger.debug(
        'OmiDeviceConnection: custody opt-in ${ack == null ? "unacknowledged" : "rejected (status=${ack.status})"} — ${legacy ? "staying legacy" : "live custody off, ring-id custody retained"}',
      );
      _ringEffectiveCaps = legacy ? 0 : (info.effectiveCaps & ~RingProtocol.capLivePersist);
      _livePersistEnabled = false;
      _custody.setLivePersistEnabled(device.id, epoch, false);
      _emitCustodyTelemetry('custody_enable_rejected', info);
      return;
    }
    var granted = ack.grantedCaps;
    if (granted == null) {
      final confirm = await getRingInfo();
      if (epoch != _custodyEpoch || token != _custodyToken) return;
      if (confirm != null) {
        _lastRingInfo = confirm;
        _noteInfoDropped(confirm);
        _custody.noteInfo(device.id, epoch, confirm);
      }
      granted = confirm?.effectiveCaps ?? 0;
    }
    _ringEffectiveCaps = granted;
    _livePersistEnabled = granted & RingProtocol.capLivePersist != 0;
    _custody.setLivePersistEnabled(device.id, epoch, _livePersistEnabled);
    _emitCustodyTelemetry('custody_enable', info);
  }

  Future<void> retryRingCustodyProbe() async {
    if (_custodyToken == null || _custodyProbeResolved) return;
    await _probeRingCustody();
  }

  final Map<String, int> _droppedSeen = {};

  void _noteInfoDropped(RingInfo info) {
    final key = '${device.id}:${info.ringId}';
    final last = _droppedSeen[key];
    _droppedSeen[key] = info.droppedPackets;
    if (last == null) return;
    final delta = info.droppedPackets - last;
    if (delta <= 0) return;
    DebugLogManager.logEvent('pendant_custody', {
      'action': 'dropped_delta',
      'device': device.id,
      'ring_id': info.ringId,
      'dropped_delta': delta,
      'used': info.unreadPackets,
      'capacity': info.capacityPackets,
    });
  }

  void _emitCustodyTelemetry(String action, RingInfo info) {
    DebugLogManager.logEvent('pendant_custody', {
      'action': action,
      'caps': _ringEffectiveCaps,
      'advertised_caps': info.advertisedCaps,
      'contract_version': info.contractVersion,
      'ring_id': info.ringId,
      'enabled': _livePersistEnabled,
      'residual_legacy_risk': _ringEffectiveCaps == 0,
    });
  }

  @override
  Future<void> connect({Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
    await retryRingCustodyProbe();

    await performSyncTime();
  }

  Future<bool> performSyncTime() async {
    try {
      final epochSeconds = DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000;
      final byteData = ByteData(4)..setUint32(0, epochSeconds, Endian.little);

      await transport.writeCharacteristic(
        timeSyncServiceUuid,
        timeSyncWriteCharacteristicUuid,
        byteData.buffer.asUint8List(),
      );
      Logger.debug('OmiDeviceConnection: Time synced to device: $epochSeconds');
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error syncing time: $e');
      return false;
    }
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final data = await transport.readCharacteristic(batteryServiceUuid, batteryLevelCharacteristicUuid);
      if (data.isNotEmpty) return data[0];
      return -1;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading battery level: $e');
      return -1;
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(batteryServiceUuid, batteryLevelCharacteristicUuid);

      final subscription = stream.listen((value) {
        if (value.isNotEmpty && onBatteryLevelChange != null) {
          Logger.debug('Battery level changed: ${value[0]}');
          onBatteryLevelChange(value[0]);
        }
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up battery listener: $e');
      return null;
    }
  }

  @override
  Future<List<int>> performGetButtonState() async {
    Logger.debug('perform button state called');
    try {
      return await transport.readCharacteristic(buttonServiceUuid, buttonTriggerCharacteristicUuid);
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading button state: $e');
      return <int>[];
    }
  }

  @override
  Future<StreamSubscription?> performGetBleButtonListener({required void Function(List<int>) onButtonReceived}) async {
    try {
      final stream = transport.getCharacteristicStream(buttonServiceUuid, buttonTriggerCharacteristicUuid);

      Logger.debug('Subscribed to button stream from Omi Device');
      final subscription = stream.listen((value) {
        Logger.debug("new button value $value");
        if (value.isNotEmpty) onButtonReceived(value);
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up button listener: $e');
      return null;
    }
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    try {
      await _enableLiveCustody();
      final stream = transport.getCharacteristicStream(omiServiceUuid, audioDataStreamCharacteristicUuid);

      Logger.debug('Subscribed to audioBytes stream from Omi Device');
      final subscription = stream.listen((value) {
        if (value.isNotEmpty) onAudioBytesReceived(value);
      });
      _audioSubscribers++;
      return _CountedSubscription<List<int>>(subscription, () {
        if (_audioSubscribers > 0) _audioSubscribers--;
      });
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up audio listener: $e');
      return null;
    }
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    try {
      final codecValue = await transport.readCharacteristic(omiServiceUuid, audioCodecCharacteristicUuid);

      var codecId = 1;
      if (codecValue.isNotEmpty) {
        codecId = codecValue[0];
      }

      switch (codecId) {
        case 1:
          return BleAudioCodec.pcm8;
        case 20:
          return BleAudioCodec.opus;
        case 21:
          return BleAudioCodec.opusFS320;
        default:
          Logger.debug('OmiDeviceConnection: Unknown codec id: $codecId');
          return BleAudioCodec.pcm8;
      }
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading audio codec: $e');
      return BleAudioCodec.pcm8;
    }
  }

  @override
  Future<List<int>> getStorageList() async {
    if (await isConnected()) {
      Logger.debug('storage list called');
      return await performGetStorageList();
    }
    Logger.debug('storage list error');
    return Future.value(<int>[]);
  }

  @override
  Future<List<int>> performGetStorageList() async {
    Logger.debug('perform storage list called');
    try {
      final storageValue = await transport.readCharacteristic(
        storageDataStreamServiceUuid,
        storageReadControlCharacteristicUuid,
      );

      List<int> storageLengths = [];
      if (storageValue.isNotEmpty) {
        int totalEntries = (storageValue.length / 4).toInt();
        Logger.debug('Storage list: $totalEntries items');

        for (int i = 0; i < totalEntries; i++) {
          int baseIndex = i * 4;
          var result = ((storageValue[baseIndex] |
                      (storageValue[baseIndex + 1] << 8) |
                      (storageValue[baseIndex + 2] << 16) |
                      (storageValue[baseIndex + 3] << 24)) &
                  0xFFFFFFFF)
              .toSigned(32);
          storageLengths.add(result);
        }
      }
      Logger.debug('Storage lengths: ${storageLengths.length} items: ${storageLengths.join(', ')}');
      return storageLengths;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading storage list: $e');
      return <int>[];
    }
  }

  // --- New multi-file storage protocol (CMD_LIST_FILES 0x10, CMD_READ_FILE 0x11, CMD_DELETE_FILE 0x12) ---

  @override
  Future<StorageStatus?> performGetStorageFileStats() async {
    try {
      // Reuse existing performGetStorageList() which reads storageReadControlCharacteristicUuid
      // and parses as array of LE uint32s.
      // New firmware format: [0]=totalBytes, [1]=fileCount (was offset in old firmware)
      final storageFiles = await performGetStorageList();
      if (storageFiles.isEmpty) return null;

      final totalBytes = storageFiles[0];
      final fileCount = storageFiles.length >= 2 ? storageFiles[1] : 0;

      // Distinguish new firmware from old: old firmware returns [totalBytes, offset]
      // where offset is a byte position (large number). New firmware returns
      // [totalBytes, fileCount] where fileCount is small (typically 0-100).
      // A value > 1000 in field[1] is almost certainly an old-firmware byte offset.
      if (fileCount > 1000) {
        Logger.debug('OmiDeviceConnection: Looks like old firmware (field[1]=$fileCount too large for file count)');
        return null;
      }

      final status = StorageStatus(totalUsedBytes: totalBytes, fileCount: fileCount, freeBytes: 0, statusFlags: 0);
      Logger.debug('OmiDeviceConnection: $status');
      return status;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading storage status: $e');
      return null;
    }
  }

  /// Send CMD_LIST_FILES (0x10) and wait for the file list notification response.
  /// Response format: [count:1][ts1:4 BE][sz1:4 BE][ts2:4 BE][sz2:4 BE]...
  /// Caller is responsible for sending STOP command beforehand and retries.
  @override
  Future<List<StorageFileInfo>> performListStorageFiles() async {
    try {
      final completer = Completer<List<StorageFileInfo>>();
      StreamSubscription? sub;

      final stream = transport.getCharacteristicStream(
        storageDataStreamServiceUuid,
        storageDataStreamCharacteristicUuid,
      );

      sub = stream.listen((value) {
        if (completer.isCompleted) return;
        if (value.isEmpty) return;

        int count = value[0];
        int expectedLen = 1 + count * 8;

        // Empty file list
        if (count == 0 && value.length == 1) {
          completer.complete([]);
          return;
        }

        // Validate this looks like a file list response (not a data packet or status byte)
        if (value.length >= expectedLen && count > 0 && count <= 128) {
          List<StorageFileInfo> files = [];
          for (int i = 0; i < count; i++) {
            int base = 1 + i * 8;
            if (base + 8 > value.length) break;
            int timestamp = (value[base] << 24) | (value[base + 1] << 16) | (value[base + 2] << 8) | value[base + 3];
            int size = (value[base + 4] << 24) | (value[base + 5] << 16) | (value[base + 6] << 8) | value[base + 7];
            files.add(StorageFileInfo(index: i, timestamp: timestamp, sizeBytes: size));
          }
          Logger.debug('OmiDeviceConnection: Listed ${files.length} storage files');
          completer.complete(files);
        }
      });

      // Send CMD_LIST_FILES
      try {
        await transport.writeCharacteristic(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid, [0x10]);

        final result = await completer.future.timeout(
          const Duration(seconds: 10),
          onTimeout: () {
            Logger.debug('OmiDeviceConnection: listFiles timeout');
            return <StorageFileInfo>[];
          },
        );
        return result;
      } finally {
        await sub.cancel();
      }
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error listing storage files: $e');
      return [];
    }
  }

  @override
  Future<bool> performDeleteStorageFile(int fileIndex) async {
    try {
      final completer = Completer<bool>();

      final stream = transport.getCharacteristicStream(
        storageDataStreamServiceUuid,
        storageDataStreamCharacteristicUuid,
      );

      StreamSubscription? subscription;
      Timer? timeout;

      subscription = stream.listen((value) {
        if (completer.isCompleted) return;
        timeout?.cancel();
        // Single-byte result: 0 = success
        final result = value.isNotEmpty ? value[0] : 0xFF;
        Logger.debug('OmiDeviceConnection: deleteStorageFile result=$result');
        completer.complete(result == 0);
      });

      timeout = Timer(const Duration(seconds: 5), () {
        if (!completer.isCompleted) {
          Logger.debug('OmiDeviceConnection: deleteStorageFile timeout');
          completer.complete(false);
        }
      });

      // Send CMD_DELETE_FILE command
      try {
        await transport.writeCharacteristic(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid, [
          0x12,
          fileIndex & 0xFF,
        ]);

        final result = await completer.future;
        return result;
      } finally {
        await subscription.cancel();
        timeout.cancel();
      }
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error deleting storage file: $e');
      return false;
    }
  }

  @override
  Future<bool> performStopStorageSync() async {
    try {
      await transport.writeCharacteristic(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid, [0x03]);
      Logger.debug('OmiDeviceConnection: Sent STOP_SYNC command');
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error sending stop command: $e');
      return false;
    }
  }

  // --- Ring-buffer storage protocol (firmware 3.0.20+) ---

  @override
  Future<RingStatus?> performGetRingStatus() async {
    try {
      final value = await transport.readCharacteristic(
        storageDataStreamServiceUuid,
        storageReadControlCharacteristicUuid,
      );
      final status = RingProtocol.parseStatus(value);
      if (status == null) {
        Logger.debug('OmiDeviceConnection: Ring status too short (${value.length} bytes)');
      } else {
        Logger.debug('OmiDeviceConnection: $status');
      }
      return status;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading ring status: $e');
      return null;
    }
  }

  @override
  Future<RingInfo?> performGetRingInfo() async {
    final info = await _enqueueStorageCommand(() => _getRingInfoLocked());
    if (info != null) _lastRingInfo = info;
    return info;
  }

  Future<RingInfo?> _getRingInfoLocked() async {
    StreamSubscription? sub;
    try {
      final completer = Completer<RingInfo?>();
      final stream = transport.getCharacteristicStream(
        storageDataStreamServiceUuid,
        storageDataStreamCharacteristicUuid,
      );

      sub = stream.listen((value) {
        if (completer.isCompleted) return;
        final info = RingProtocol.parseInfoNotification(value);
        if (info == null) return;
        Logger.debug('OmiDeviceConnection: $info');
        completer.complete(info);
      });

      await transport.writeCharacteristic(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid, [
        RingProtocol.cmdInfo,
      ]);

      return await completer.future.timeout(
        const Duration(seconds: 5),
        onTimeout: () {
          Logger.debug('OmiDeviceConnection: getRingInfo timeout');
          return null;
        },
      );
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error getting ring info: $e');
      return null;
    } finally {
      await sub?.cancel();
    }
  }

  @override
  Future<bool> performReadRingFromSeq(int startSeq, {int? packetCount}) async {
    try {
      await transport.writeCharacteristic(
        storageDataStreamServiceUuid,
        storageDataStreamCharacteristicUuid,
        RingProtocol.encodeReadCommand(startSeq, packetCount: packetCount),
      );
      Logger.debug('OmiDeviceConnection: CMD_RING_READ start_seq=$startSeq count=${packetCount ?? "all"}');
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error sending CMD_RING_READ: $e');
      return false;
    }
  }

  @override
  Future<bool> performAdvanceRing(int newReadSeq) async {
    final ack = await performAdvanceRingCustody(newReadSeq, expectedEpoch: _custodyEpoch, expectedRingId: null);
    return ack?.isOk ?? false;
  }

  @override
  Future<RingCommandAck?> performAdvanceRingCustody(
    int newReadSeq, {
    required int expectedEpoch,
    required int? expectedRingId,
  }) async {
    return _enqueueStorageCommand(() async {
      int? currentRingId() => (_ringEffectiveCaps & RingProtocol.capRingId) != 0 ? _lastRingInfo?.ringId : null;
      if (expectedEpoch != _custodyEpoch || expectedRingId != currentRingId()) {
        Logger.debug(
          'OmiDeviceConnection: stale advance fenced seq=$newReadSeq epoch=$expectedEpoch/$_custodyEpoch ring=$expectedRingId/${currentRingId()}',
        );
        return const RingCommandAck(status: RingProtocol.ackRingIdMismatch);
      }
      StreamSubscription? sub;
      try {
        final completer = Completer<RingCommandAck?>();
        final stream = transport.getCharacteristicStream(
          storageDataStreamServiceUuid,
          storageDataStreamCharacteristicUuid,
        );

        sub = stream.listen((value) {
          if (completer.isCompleted) return;
          if (value.length < 2 || value[0] != RingProtocol.notifyAck) return;
          final ack = RingCommandAck(status: value[1], grantedCaps: value.length >= 3 ? value[2] : null);
          Logger.debug('OmiDeviceConnection: ADVANCE ack status=${ack.status}');
          completer.complete(ack);
        });

        final ringId = expectedRingId;
        final payload = ringId != null
            ? RingProtocol.encodeAdvanceIdCommand(ringId, newReadSeq)
            : RingProtocol.encodeAdvanceCommand(newReadSeq);
        await transport.writeCharacteristic(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid, payload);
        Logger.debug(
          'OmiDeviceConnection: ${ringId != null ? "CMD_RING_ADVANCE_ID" : "CMD_RING_ADVANCE"} seq=$newReadSeq ring=${ringId ?? "none"}',
        );

        final result = await completer.future.timeout(
          const Duration(seconds: 5),
          onTimeout: () {
            Logger.debug('OmiDeviceConnection: advanceRing timeout');
            return null;
          },
        );
        if (expectedEpoch != _custodyEpoch || expectedRingId != currentRingId()) {
          return const RingCommandAck(status: RingProtocol.ackRingIdMismatch);
        }
        var ack = result;
        if (ack != null && ack.status == RingProtocol.ackSeqOutOfRange) {
          final fresh = await _getRingInfoLocked();
          if (expectedEpoch != _custodyEpoch || expectedRingId != currentRingId()) {
            return const RingCommandAck(status: RingProtocol.ackRingIdMismatch);
          }
          if (fresh != null &&
              (expectedRingId == null || fresh.ringId == expectedRingId) &&
              newReadSeq <= fresh.readSeq) {
            return const RingCommandAck(status: RingProtocol.ackOk);
          }
        }
        return ack;
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error advancing ring: $e');
        return null;
      } finally {
        await sub?.cancel();
      }
    });
  }

  @override
  Future<RingCommandAck?> performEnableRingCustody(int requestedCaps) async {
    return _enqueueStorageCommand(() async {
      StreamSubscription? sub;
      try {
        final completer = Completer<RingCommandAck?>();
        final stream = transport.getCharacteristicStream(
          storageDataStreamServiceUuid,
          storageDataStreamCharacteristicUuid,
        );

        sub = stream.listen((value) {
          if (completer.isCompleted) return;
          if (value.length < 2 || value[0] != RingProtocol.notifyAck) return;
          completer.complete(RingCommandAck(status: value[1], grantedCaps: value.length >= 3 ? value[2] : null));
        });

        await transport.writeCharacteristic(
          storageDataStreamServiceUuid,
          storageDataStreamCharacteristicUuid,
          RingProtocol.encodeCustodyEnableCommand(requestedCaps),
        );
        Logger.debug('OmiDeviceConnection: CMD_CUSTODY_ENABLE caps=0x${requestedCaps.toRadixString(16)}');

        return await completer.future.timeout(
          const Duration(seconds: 5),
          onTimeout: () {
            Logger.debug('OmiDeviceConnection: custody enable timeout');
            return null;
          },
        );
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error enabling ring custody: $e');
        return null;
      } finally {
        await sub?.cancel();
      }
    });
  }

  @override
  Future<bool> performClearRing() => _enqueueStorageCommand(_clearRingLocked);

  Future<bool> _clearRingLocked() async {
    StreamSubscription? sub;
    try {
      final completer = Completer<bool>();
      final stream = transport.getCharacteristicStream(
        storageDataStreamServiceUuid,
        storageDataStreamCharacteristicUuid,
      );

      sub = stream.listen((value) {
        if (completer.isCompleted) return;
        if (value.length < 2 || value[0] != RingProtocol.notifyAck) return;
        final status = value[1];
        Logger.debug('OmiDeviceConnection: CLEAR ack status=$status');
        completer.complete(status == 0);
      });

      await transport.writeCharacteristic(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid, [
        RingProtocol.cmdClear,
      ]);
      Logger.debug('OmiDeviceConnection: CMD_RING_CLEAR');

      return await completer.future.timeout(
        const Duration(seconds: 5),
        onTimeout: () {
          Logger.debug('OmiDeviceConnection: clearRing timeout');
          return false;
        },
      );
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error clearing ring: $e');
      return false;
    } finally {
      await sub?.cancel();
    }
  }

  // --- Legacy storage protocol ---

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(
        storageDataStreamServiceUuid,
        storageDataStreamCharacteristicUuid,
      );

      final subscription = stream.listen((value) {
        if (value.isNotEmpty) onStorageBytesReceived(value);
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up storage listener: $e');
      return null;
    }
  }

  // level
  //   1 - play 20ms
  //   2 - play 50ms
  //   3 - play 500ms
  @override
  Future<bool> performPlayToSpeakerHaptic(int level) async {
    try {
      Logger.debug('About to play to speaker haptic');
      await transport.writeCharacteristic(speakerDataStreamServiceUuid, speakerDataStreamCharacteristicUuid, [
        level & 0xFF,
      ]);
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error playing haptic: $e');
      return false;
    }
  }

  @override
  Future<bool> performWriteToStorage(int numFile, int command, int offset) async {
    try {
      Logger.debug('About to write to storage bytes');
      Logger.debug('about to send $numFile');
      Logger.debug('about to send $command');
      Logger.debug('about to send offset$offset');

      var offsetBytes = [(offset >> 24) & 0xFF, (offset >> 16) & 0xFF, (offset >> 8) & 0xFF, offset & 0xFF];

      await transport.writeCharacteristic(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid, [
        command & 0xFF,
        numFile & 0xFF,
        offsetBytes[0],
        offsetBytes[1],
        offsetBytes[2],
        offsetBytes[3],
      ]);
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error writing to storage: $e');
      return false;
    }
  }

  @override
  Future performCameraStartPhotoController() async {
    try {
      // Capture photo once every 5s
      await transport.writeCharacteristic(omiServiceUuid, imageCaptureControlCharacteristicUuid, [0x05]);
      print('cameraStartPhotoController');
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error starting photo capture: $e');
    }
  }

  @override
  Future performCameraStopPhotoController() async {
    try {
      await transport.writeCharacteristic(omiServiceUuid, imageCaptureControlCharacteristicUuid, [0x00]);
      print('cameraStopPhotoController');
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error stopping photo capture: $e');
    }
  }

  Future performCameraTakePhoto() async {
    try {
      // -1 tells the firmware to take a single photo
      await transport.writeCharacteristic(omiServiceUuid, imageCaptureControlCharacteristicUuid, [-1]);
      print('cameraTakePhoto');
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error taking photo: $e');
    }
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async {
    try {
      // Try to read from the image data stream characteristic to see if it exists
      await transport.readCharacteristic(omiServiceUuid, imageDataStreamCharacteristicUuid);
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Photo streaming characteristic not available: $e');
      return false;
    }
  }

  Future<StreamSubscription?> _getBleImageBytesListener({
    required void Function(List<int>) onImageBytesReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(omiServiceUuid, imageDataStreamCharacteristicUuid);

      Logger.debug('Subscribed to imageBytes stream from Omi Device');
      final subscription = stream.listen((value) {
        if (value.isNotEmpty) onImageBytesReceived(value);
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up image listener: $e');
      return null;
    }
  }

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async {
    if (!await hasPhotoStreamingCharacteristic()) {
      return null;
    }
    print("OpenGlassDevice getImageListener called");

    var buffer = BytesBuilder();
    var nextExpectedFrame = 0;
    var isTransferring = false;
    ImageOrientation? currentOrientation;

    Version newFirmwareVersion = Version.parse("2.1.1");
    Version deviceFirmwareVersion;
    try {
      deviceFirmwareVersion = Version.parse(device.firmwareRevision);
    } catch (e) {
      deviceFirmwareVersion = Version(0, 0, 0);
    }

    var bleBytesStream = await _getBleImageBytesListener(
      onImageBytesReceived: (List<int> value) async {
        if (value.length < 2) return;

        Uint8List chunk = Uint8List.fromList(value);
        int frameIndex = chunk[0] | (chunk[1] << 8);

        // End of image marker 0xFFFF
        if (frameIndex == 0xFFFF) {
          if (isTransferring) {
            final imageBytes = buffer.toBytes();
            if (imageBytes.isNotEmpty) {
              Logger.debug('Completed image bytes length: ${imageBytes.length}');
              try {
                onImageReceived(
                  OrientedImage(
                    imageBytes: imageBytes,
                    orientation: currentOrientation ?? ImageOrientation.orientation0,
                  ),
                );
              } catch (e) {
                Logger.debug('Error processing image: $e');
              }
            }
          }
          // Reset for next image
          buffer.clear();
          isTransferring = false;
          nextExpectedFrame = 0;
          currentOrientation = null;
          return;
        }

        // If we get frame 0, it's the start of a new image. Reset everything.
        if (frameIndex == 0) {
          buffer.clear();
          isTransferring = true;
          nextExpectedFrame = 0;
          currentOrientation = null;
        }

        // If we are not in a transfer state, ignore the packet unless it's frame 0.
        if (!isTransferring) {
          Logger.debug("Ignoring packet with frame $frameIndex, waiting for frame 0 to start transfer.");
          return;
        }

        // Check if the frame is the one we expect.
        if (frameIndex == nextExpectedFrame) {
          if (frameIndex == 0) {
            if (deviceFirmwareVersion >= newFirmwareVersion) {
              // New firmware: parse orientation from packet
              if (chunk.length > 2) {
                currentOrientation = ImageOrientation.fromValue(chunk[2]);
                if (chunk.length > 3) {
                  buffer.add(chunk.sublist(3));
                }
              } else {
                // Malformed packet, default orientation
                currentOrientation = ImageOrientation.orientation0;
              }
            } else {
              // Old firmware: default to 180 degrees and treat whole chunk as data
              currentOrientation = ImageOrientation.orientation180;
              if (chunk.length > 2) {
                buffer.add(chunk.sublist(2));
              }
            }
          } else {
            if (chunk.length > 2) {
              buffer.add(chunk.sublist(2));
            }
          }
          nextExpectedFrame++;
        } else {
          // Out of order frame. The image is now corrupt.
          // We should discard everything and wait for the next frame 0.
          Logger.debug('Frame out of order. Expected $nextExpectedFrame, got $frameIndex. Discarding image.');
          buffer.clear();
          isTransferring = false;
          nextExpectedFrame = 0;
          currentOrientation = null;
        }

        // Safety break for oversized buffer
        if (buffer.length > 200 * 1024) {
          Logger.debug("Buffer size exceeded 200KB without a complete image. Resetting.");
          buffer.clear();
          isTransferring = false;
          nextExpectedFrame = 0;
          currentOrientation = null;
        }
      },
    );
    bleBytesStream?.onDone(() {
      Logger.debug('Image listener done');
      cameraStopPhotoController();
    });
    return bleBytesStream;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({void Function(int)? onAccelChange}) async {
    try {
      final stream = transport.getCharacteristicStream(accelDataStreamServiceUuid, accelDataStreamCharacteristicUuid);

      final subscription = stream.listen((value) async {
        if (value.length > 4) {
          //for some reason, the very first reading is four bytes

          if (value.isNotEmpty) {
            List<double> accelerometerData = [];
            onAccelChange?.call(value[0]);

            for (int i = 0; i < 6; i++) {
              int baseIndex = i * 8;
              var result = ((value[baseIndex] |
                          (value[baseIndex + 1] << 8) |
                          (value[baseIndex + 2] << 16) |
                          (value[baseIndex + 3] << 24)) &
                      0xFFFFFFFF)
                  .toSigned(32);
              var temp = ((value[baseIndex + 4] |
                          (value[baseIndex + 5] << 8) |
                          (value[baseIndex + 6] << 16) |
                          (value[baseIndex + 7] << 24)) &
                      0xFFFFFFFF)
                  .toSigned(32);
              double axisValue = result + (temp / 1000000);
              accelerometerData.add(axisValue);
            }
            Logger.debug('Accelerometer x direction: ${accelerometerData[0]}');
            Logger.debug('Gyroscope x direction: ${accelerometerData[3]}\n');

            Logger.debug('Accelerometer y direction: ${accelerometerData[1]}');
            Logger.debug('Gyroscope y direction: ${accelerometerData[4]}\n');

            Logger.debug('Accelerometer z direction: ${accelerometerData[2]}');
            Logger.debug('Gyroscope z direction: ${accelerometerData[5]}\n');
            //simple threshold fall calcaultor
            var fall_number = sqrt(
              pow(accelerometerData[0], 2) + pow(accelerometerData[1], 2) + pow(accelerometerData[2], 2),
            );
            if (fall_number > 30.0) {
              await NotificationUtil.triggerFallNotification();
            }
          }
        }
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up accelerometer listener: $e');
      return null;
    }
  }

  @override
  Future<void> performSetLedDimRatio(int ratio) async {
    try {
      await transport.writeCharacteristic(settingsServiceUuid, settingsDimRatioCharacteristicUuid, [
        ratio.clamp(0, 100),
      ]);
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting LED dim ratio: $e');
    }
  }

  @override
  Future<int?> performGetLedDimRatio() async {
    try {
      final value = await transport.readCharacteristic(settingsServiceUuid, settingsDimRatioCharacteristicUuid);
      if (value.isNotEmpty) {
        return value[0];
      }
      return null;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error getting LED dim ratio: $e');
      return null;
    }
  }

  @override
  Future<int> performGetFeatures() async {
    try {
      final value = await transport.readCharacteristic(featuresServiceUuid, featuresCharacteristicUuid);
      if (value.length >= 4) {
        return ByteData.view(Uint8List.fromList(value).buffer).getUint32(0, Endian.little);
      }
      return 0;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error getting features: $e');
      return 0;
    }
  }

  @override
  Future<void> performSetMicGain(int gain) async {
    try {
      await transport.writeCharacteristic(settingsServiceUuid, settingsMicGainCharacteristicUuid, [gain.clamp(0, 100)]);
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting mic gain: $e');
    }
  }

  @override
  Future<int?> performGetMicGain() async {
    try {
      final value = await transport.readCharacteristic(settingsServiceUuid, settingsMicGainCharacteristicUuid);
      if (value.isNotEmpty) {
        return value[0];
      }
      return null;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error getting mic gain: $e');
      return null;
    }
  }

  /// Null means the charging state is unknown; it must not create a charge edge.
  Future<bool?> readChargingStatus() async {
    try {
      final value = await transport.readCharacteristic(settingsServiceUuid, settingsChargingStatusCharacteristicUuid);
      return value.isEmpty ? null : value[0] == 1;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading charging status: $e');
      return null;
    }
  }

  Future<StreamSubscription?> getChargingStatusListener({
    required void Function(bool isCharging) onChargingStatusChange,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(settingsServiceUuid, settingsChargingStatusCharacteristicUuid);
      return stream.listen((value) {
        if (value.isNotEmpty) {
          onChargingStatusChange(value[0] == 1);
        }
      });
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up charging status listener: $e');
      return null;
    }
  }

  /// CV1 publishes its nRF FICR device ID as exactly 16 hex characters.
  /// Only that shape is accepted: this connection also serves other
  /// Omi-protocol devices, and any constant or fallback serial they report
  /// (e.g. the firmware's "unknown") would merge every unit into one
  /// analytics hardware_id.
  static final RegExp _unitIdPattern = RegExp(r'^[0-9A-F]{16}$');

  /// Bounds the serial read so a missing native callback cannot stall setup.
  static const Duration _serialReadTimeout = Duration(seconds: 3);

  /// Parses a DIS Serial Number String read into a CV1 unit ID, or null when
  /// it is not a 16-hex-character ID or is a single repeated digit (unset FICR).
  @visibleForTesting
  static String? parseSerialNumber(List<int> value) {
    if (value.isEmpty) return null;
    final serial = String.fromCharCodes(value).replaceAll('\u0000', '').trim().toUpperCase();
    if (!_unitIdPattern.hasMatch(serial)) return null;
    if (serial.split('').toSet().length == 1) return null;
    return serial;
  }

  /// Get device information from Omi device
  Future<Map<String, String>> getDeviceInfo() async {
    Map<String, String> deviceInfo = {};

    try {
      // Read model number
      try {
        final modelValue = await transport.readCharacteristic(
          deviceInformationServiceUuid,
          modelNumberCharacteristicUuid,
        );
        if (modelValue.isNotEmpty) {
          deviceInfo['modelNumber'] = String.fromCharCodes(modelValue);
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error reading model number: $e');
      }

      // Read firmware revision
      try {
        final firmwareValue = await transport.readCharacteristic(
          deviceInformationServiceUuid,
          firmwareRevisionCharacteristicUuid,
        );
        if (firmwareValue.isNotEmpty) {
          deviceInfo['firmwareRevision'] = String.fromCharCodes(firmwareValue);
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error reading firmware revision: $e');
      }

      // Read hardware revision
      try {
        final hardwareValue = await transport.readCharacteristic(
          deviceInformationServiceUuid,
          hardwareRevisionCharacteristicUuid,
        );
        if (hardwareValue.isNotEmpty) {
          deviceInfo['hardwareRevision'] = String.fromCharCodes(hardwareValue);
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error reading hardware revision: $e');
      }

      // Read manufacturer name
      try {
        final manufacturerValue = await transport.readCharacteristic(
          deviceInformationServiceUuid,
          manufacturerNameCharacteristicUuid,
        );
        if (manufacturerValue.isNotEmpty) {
          deviceInfo['manufacturerName'] = String.fromCharCodes(manufacturerValue);
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error reading manufacturer name: $e');
      }

      // Read serial number (0x2A25). CV1 firmware that exposes the per-unit
      // hardware ID serves it here; older firmware has no such characteristic
      // and the transport returns an empty read, leaving serialNumber unset.
      try {
        final serialValue = await transport
            .readCharacteristic(deviceInformationServiceUuid, serialNumberCharacteristicUuid)
            .timeout(_serialReadTimeout);
        final serial = parseSerialNumber(serialValue);
        if (serial != null) {
          deviceInfo['serialNumber'] = serial;
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error reading serial number: $e');
      }

      // Check if device has image streaming capability (for OpenGlass/OmiGlass detection)
      try {
        final chars = await transport.readCharacteristic(omiServiceUuid, imageDataStreamCharacteristicUuid);
        if (chars.isNotEmpty) {
          deviceInfo['hasImageStream'] = 'true';
        }
      } catch (e) {
        deviceInfo['hasImageStream'] = 'false';
      }
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error getting device info: $e');
    }

    // Set defaults if values are empty.
    // firmwareRevision intentionally has no fallback: when the BLE read fails
    // we leave it empty rather than lying with an arbitrary version. A stale
    // default like '1.0.2' tricked the backend into recommending Omi_CV1_v3.0.5
    // (the only release whose minimum_firmware_required is 1.0.0) to users
    // whose actual firmware was 3.0.19 — see callers for the empty-check guard.
    deviceInfo['modelNumber'] ??= 'Omi Device';
    deviceInfo['firmwareRevision'] ??= '';
    deviceInfo['hardwareRevision'] ??= 'Seeed Xiao BLE Sense';
    deviceInfo['manufacturerName'] ??= 'Based Hardware';
    deviceInfo['hasImageStream'] ??= 'false';

    return deviceInfo;
  }
}

class _CountedSubscription<T> implements StreamSubscription<T> {
  _CountedSubscription(this._inner, this._onRelease);

  final StreamSubscription<T> _inner;
  final void Function() _onRelease;
  bool _released = false;

  void _release() {
    if (_released) return;
    _released = true;
    _onRelease();
  }

  @override
  Future<void> cancel() {
    _release();
    return _inner.cancel();
  }

  @override
  void onData(void Function(T)? handleData) => _inner.onData(handleData);

  @override
  void onDone(void Function()? handleDone) => _inner.onDone(() {
        _release();
        handleDone?.call();
      });

  @override
  void onError(Function? handleError) => _inner.onError(handleError);

  @override
  Future<E> asFuture<E>([E? futureValue]) => _inner.asFuture(futureValue);

  @override
  bool get isPaused => _inner.isPaused;

  @override
  void pause([Future<void>? resumeSignal]) => _inner.pause(resumeSignal);

  @override
  void resume() => _inner.resume();
}
