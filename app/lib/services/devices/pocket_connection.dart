import 'dart:async';
import 'dart:convert';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/logger.dart';

// BLE Characteristic UUIDs discovered via BLE packet analysis of HeyPocket device
// Service UUID is in models.dart as pocketServiceUuid
const String pocketAudioCharacteristicUuid = '001120a1-2233-4455-6677-889912345678';
const String pocketCommandCharacteristicUuid = '001120a2-2233-4455-6677-889912345678';
// Secondary write channel — reserved for future use (e.g. firmware OTA, WiFi config)
const String pocketCommandWriteCharacteristicUuid = '001120a3-2233-4455-6677-889912345678';

/// Device connection for HeyPocket (Pocket) wearable devices.
///
/// The Pocket device uses a text-based BLE command protocol:
/// - APP→MCU: Commands sent as ASCII strings (e.g. "APP&STA" to start recording)
/// - MCU→APP: Responses as ASCII strings (e.g. "MCU&BAT&85" for battery level)
/// - Audio: Streamed via a dedicated notify characteristic (likely Opus encoded)
///
/// Commands are serialized through a Completer-based lock to prevent concurrent
/// commands from consuming each other's responses on the shared broadcast stream.
class PocketDeviceConnection extends DeviceConnection {
  final _audioController = StreamController<List<int>>.broadcast();
  final _commandResponseController = StreamController<String>.broadcast();

  StreamSubscription? _commandNotifySub;
  StreamSubscription? _audioNotifySub;
  bool _isRecording = false;
  Timer? _batteryTimer;

  /// Lock to serialize BLE commands — prevents concurrent commands from
  /// consuming each other's responses on the shared broadcast stream.
  Completer<void>? _commandLock;

  PocketDeviceConnection(super.device, super.transport);

  // --- Connection Lifecycle ---

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
    await Future.delayed(const Duration(milliseconds: 500));

    // Subscribe to command responses (MCU→APP)
    _commandNotifySub = transport
        .getCharacteristicStream(pocketServiceUuid, pocketCommandCharacteristicUuid)
        .listen((data) {
      try {
        final response = utf8.decode(data, allowMalformed: true);
        Logger.debug('[Pocket] MCU response: $response');
        _commandResponseController.add(response);
      } catch (e) {
        Logger.error('[Pocket] Error decoding command response: $e');
      }
    });

    // Subscribe to audio stream
    _audioNotifySub = transport
        .getCharacteristicStream(pocketServiceUuid, pocketAudioCharacteristicUuid)
        .listen((data) {
      if (data.isNotEmpty) {
        _audioController.add(data);
      }
    });

    // Set device time on connect
    await _setDeviceTime();

    Logger.debug('[Pocket] Connected and subscribed to characteristics');
  }

  @override
  Future<void> disconnect() async {
    // Stop recording if active
    if (_isRecording) {
      try {
        await _sendCommand('APP&STO');
      } catch (_) {}
      _isRecording = false;
    }

    // Cancel battery polling timer
    _batteryTimer?.cancel();
    _batteryTimer = null;

    await _commandNotifySub?.cancel();
    await _audioNotifySub?.cancel();
    await _audioController.close();
    await _commandResponseController.close();
    await super.disconnect();
  }

  // --- Command Protocol ---

  /// Send a text command to the Pocket MCU via BLE write.
  /// Throws on write failure so callers can handle immediately
  /// instead of waiting for a response timeout.
  Future<void> _sendCommand(String command) async {
    await transport.writeCharacteristic(
      pocketServiceUuid,
      pocketCommandCharacteristicUuid,
      utf8.encode(command),
    );
    Logger.debug('[Pocket] Sent: $command');
  }

  /// Send a command and wait for a response starting with the given prefix.
  /// Commands are serialized via a lock to prevent concurrent commands from
  /// consuming each other's responses on the shared broadcast stream.
  /// Returns null if the write fails or no matching response arrives within timeout.
  Future<String?> _sendCommandWithResponse(
    String command, {
    required String expectPrefix,
    Duration timeout = const Duration(seconds: 5),
  }) async {
    // Wait for any in-flight command to complete
    while (_commandLock != null) {
      await _commandLock!.future;
    }
    _commandLock = Completer<void>();

    try {
      await _sendCommand(command);
      final response = await _commandResponseController.stream
          .where((r) => r.startsWith(expectPrefix))
          .first
          .timeout(timeout, onTimeout: () => '');
      return response;
    } catch (e) {
      Logger.error('[Pocket] Command "$command" failed: $e');
      return null;
    } finally {
      final lock = _commandLock;
      _commandLock = null;
      lock?.complete();
    }
  }

  /// Set device time to current time.
  Future<void> _setDeviceTime() async {
    final now = DateTime.now();
    final timeStr =
        '${now.year}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}'
        '${now.hour.toString().padLeft(2, '0')}${now.minute.toString().padLeft(2, '0')}${now.second.toString().padLeft(2, '0')}';
    await _sendCommandWithResponse('APP&T&$timeStr', expectPrefix: 'MCU&T&');
  }

  /// Stop recording on the device and reset state.
  Future<void> _stopRecording() async {
    if (!_isRecording) return;
    try {
      await _sendCommand('APP&STO');
    } catch (_) {}
    _isRecording = false;
    Logger.debug('[Pocket] Recording stopped');
  }

  // --- Audio ---

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    // Pocket device stores .opus files and streams audio for Deepgram transcription.
    // Most likely Opus at 16kHz mono.
    return BleAudioCodec.opus;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    // Start recording on the device
    final response = await _sendCommandWithResponse('APP&STA', expectPrefix: 'MCU&REC&');
    if (response != null && response.isNotEmpty) {
      _isRecording = true;
      Logger.debug('[Pocket] Recording started: $response');
    } else {
      Logger.warning('[Pocket] No confirmation for start recording, proceeding anyway');
      _isRecording = true;
    }

    // When the last listener is cancelled (e.g. app backgrounded, capture stopped),
    // send stop recording command to the device to prevent battery drain.
    // onCancel on a broadcast StreamController fires when listener count drops to zero.
    _audioController.onCancel = () => _stopRecording();

    return _audioController.stream.listen(onAudioBytesReceived);
  }

  // --- Battery ---

  @override
  Future<int> performRetrieveBatteryLevel() async {
    final response = await _sendCommandWithResponse('APP&BAT', expectPrefix: 'MCU&BAT&');
    if (response != null && response.startsWith('MCU&BAT&')) {
      final levelStr = response.substring('MCU&BAT&'.length).trim();
      return int.tryParse(levelStr) ?? -1;
    }
    return -1;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    if (onBatteryLevelChange == null) return null;

    // Pocket uses polling for battery (no standard BLE Battery Service).
    // Store timer reference so disconnect() can cancel it.
    final controller = StreamController<List<int>>();
    int? lastLevel;

    _batteryTimer?.cancel();
    _batteryTimer = Timer.periodic(const Duration(minutes: 5), (timer) async {
      try {
        final level = await performRetrieveBatteryLevel();
        if (level >= 0 && level != lastLevel) {
          lastLevel = level;
          onBatteryLevelChange(level);
        }
      } catch (e) {
        Logger.debug('[Pocket] Battery poll failed (device may be disconnected): $e');
      }
    });

    controller.onCancel = () {
      _batteryTimer?.cancel();
      _batteryTimer = null;
      controller.close();
    };

    // Read initial battery level
    final initialLevel = await performRetrieveBatteryLevel();
    if (initialLevel >= 0) {
      lastLevel = initialLevel;
      onBatteryLevelChange(initialLevel);
    }

    return controller.stream.listen(null);
  }

  // --- Device Info ---

  Future<Map<String, String>> getDeviceInfo() async {
    String firmwareVersion = 'Unknown';
    try {
      final fwResponse = await _sendCommandWithResponse('APP&FW', expectPrefix: 'MCU&FW&');
      if (fwResponse != null && fwResponse.startsWith('MCU&FW&')) {
        firmwareVersion = fwResponse.substring('MCU&FW&'.length).trim();
      }
    } catch (e) {
      Logger.error('[Pocket] Error getting firmware version: $e');
    }

    return {
      'modelNumber': 'Pocket',
      'firmwareRevision': firmwareVersion,
      'hardwareRevision': 'HeyPocket Hardware',
      'manufacturerName': 'HeyPocket',
    };
  }

  // --- Storage Info ---

  /// Query device storage space.
  /// Returns (total, free) in bytes, or null on failure.
  Future<(int, int)?> getStorageInfo() async {
    final response = await _sendCommandWithResponse('APP&SPACE', expectPrefix: 'MCU&SPA&');
    if (response != null && response.startsWith('MCU&SPA&')) {
      final parts = response.substring('MCU&SPA&'.length).split('&');
      if (parts.length >= 2) {
        final total = int.tryParse(parts[0]);
        final free = int.tryParse(parts[1]);
        if (total != null && free != null) return (total, free);
      }
    }
    return null;
  }

  // --- Stubs for unsupported features ---

  @override
  Future<List<int>> performGetButtonState() async => [];

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async => null;

  @override
  Future performCameraStartPhotoController() async {}

  @override
  Future performCameraStopPhotoController() async {}

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async => false;

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async => null;

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async => null;

  @override
  Future<int> performGetFeatures() async => 0;

  @override
  Future<void> performSetLedDimRatio(int ratio) async {}

  @override
  Future<int?> performGetLedDimRatio() async => null;

  @override
  Future<void> performSetMicGain(int gain) async {}

  @override
  Future<int?> performGetMicGain() async => null;
}
