import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/pocket/pocket_models.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';

/// Pocket Device BLE Connection
/// Port of Python PocketClient and PocketProtocol from pocket-re library
class PocketDeviceConnection extends DeviceConnection {
  // Authentication key (fixed for all Pocket devices)
  static const List<int> authKey = [
    65, 80, 80, 38, 83, 75, 38, 101, 121, 54, 114, 66, 80, 88, 80, 80, 105, 97, 86, 67, 103, 105, 84
  ]; // "APP&SK&ey6rBPXPPiaVCgiT"

  // MP3 frame marker and size (from protocol analysis)
  static const List<int> mp3Marker = [0xFF, 0xF3, 0x48, 0xC4]; // MP3 frame marker (4 bytes)
  static const int mp3FrameSize = 144; // bytes per frame

  // Response buffers
  final List<int> _responseBuffer = [];
  final List<String> _textResponses = [];
  bool _isAuthenticated = false;
  
  // Battery polling
  Timer? _batteryPollTimer;
  void Function(int)? _onBatteryLevelChange;

  PocketDeviceConnection(super.device, super.transport);

  @override
  Future<void> connect({Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
    
    // Start listening to notifications
    await _startNotifications();
    
    // Authenticate
    final authenticated = await authenticate();
    if (!authenticated) {
      throw Exception('Failed to authenticate with Pocket device');
    }
    
    debugPrint('Pocket device authenticated successfully');
  }

  /// Start listening for BLE notifications
  Future<void> _startNotifications() async {
    try {
      // Subscribe to response characteristic
      final responseStream = transport.getCharacteristicStream(
        pocketServiceUuid,
        pocketResponseCharacteristicUuid,
      );
      
      responseStream.listen(_handleNotification);

      // Subscribe to status characteristic
      final statusStream = transport.getCharacteristicStream(
        pocketServiceUuid,
        pocketStatusCharacteristicUuid,
      );
      
      statusStream.listen(_handleNotification);
      
      debugPrint('Pocket: Started listening for notifications');
    } catch (e) {
      debugPrint('Pocket: Error starting notifications: $e');
      rethrow;
    }
  }

  /// Handle BLE notifications
  void _handleNotification(List<int> data) {
    _responseBuffer.addAll(data);
    
    // Try to decode as text
    try {
      final text = utf8.decode(data, allowMalformed: true);
      if (text.contains('MCU&')) {
        _textResponses.add(text);
        debugPrint('Pocket response: $text');
      }
    } catch (e) {
      // Not text data, probably binary (MP3)
    }
  }

  /// Send command and wait for responses
  Future<List<String>> _sendCommand(List<int> command, {Duration waitTime = const Duration(seconds: 2)}) async {
    _textResponses.clear();
    
    try {
      await transport.writeCharacteristic(
        pocketServiceUuid,
        pocketCommandCharacteristicUuid,
        command,
      );
      
      // Wait for responses
      await Future.delayed(waitTime);
      
      return List.from(_textResponses);
    } catch (e) {
      debugPrint('Pocket: Error sending command: $e');
      return [];
    }
  }

  /// Authenticate with device
  Future<bool> authenticate() async {
    if (_isAuthenticated) return true;
    
    debugPrint('Pocket: Authenticating...');
    final responses = await _sendCommand(authKey);
    
    _isAuthenticated = responses.any((r) => r.contains('SK&OK'));
    
    if (_isAuthenticated) {
      debugPrint('Pocket: Authentication successful');
    } else {
      debugPrint('Pocket: Authentication failed');
    }
    
    return _isAuthenticated;
  }

  /// Get device information
  Future<PocketDeviceInfo> getDeviceInfo() async {
    final battery = await getBattery();
    final firmware = await getFirmware();
    final storage = await getStorage();
    
    return PocketDeviceInfo(
      firmware: firmware,
      battery: battery,
      storageUsed: storage?.$1,
      storageTotal: storage?.$2,
    );
  }

  /// Get battery level (0-100)
  Future<int?> getBattery() async {
    final responses = await _sendCommand(utf8.encode('APP&BAT'));
    
    for (final resp in responses) {
      if (resp.contains('MCU&BAT&')) {
        try {
          final parts = resp.split('&');
          if (parts.length >= 3) {
            return int.parse(parts[2]);
          }
        } catch (e) {
          debugPrint('Pocket: Error parsing battery: $e');
        }
      }
    }
    return null;
  }

  /// Get firmware version
  Future<String?> getFirmware() async {
    final responses = await _sendCommand(utf8.encode('APP&FW'));
    
    for (final resp in responses) {
      if (resp.contains('MCU&FW&')) {
        final parts = resp.split('&');
        if (parts.length >= 3) {
          return parts[2];
        }
      }
    }
    return null;
  }

  /// Get storage info (used, total) - Pocket returns KB
  Future<(int, int)?> getStorage() async {
    final responses = await _sendCommand(utf8.encode('APP&SPACE'));
    
    for (final resp in responses) {
      if (resp.contains('MCU&SPA&')) {
        try {
          final parts = resp.split('&');
          if (parts.length >= 4) {
            final used = int.parse(parts[2]);
            final total = int.parse(parts[3]);
            debugPrint('Pocket: Storage response - used: $used MB, total: $total MB');
            // Convert MB to bytes
            return (used * 1024 * 1024, total * 1024 * 1024);
          }
        } catch (e) {
          debugPrint('Pocket: Error parsing storage: $e');
        }
      }
    }
    return null;
  }

  /// List all recordings on device
  Future<List<PocketRecording>> listRecordings() async {
    final recordings = <PocketRecording>[];
    
    // Get directories
    debugPrint('Pocket: Listing directories...');
    final dirResponses = await _sendCommand(utf8.encode('APP&LIST_DIRS'));
    final directories = <String>[];
    
    for (final resp in dirResponses) {
      if (resp.contains('MCU&DIRS&') && !resp.contains('MCU&DIRS_SUM')) {
        final parts = resp.split('&');
        if (parts.length >= 3) {
          directories.add(parts[2]);
        }
      }
    }
    
    debugPrint('Pocket: Found ${directories.length} directories');
    
    // List files in each directory
    for (final directory in directories) {
      debugPrint('Pocket: Listing files in $directory...');
      final cmd = utf8.encode('APP&LIST&$directory');
      final fileResponses = await _sendCommand(cmd, waitTime: const Duration(seconds: 3));
      
      for (final resp in fileResponses) {
        if (resp.contains('MCU&F&')) {
          try {
            final parts = resp.split('&');
            if (parts.length >= 4) {
              final dir = parts[2];
              final timestamp = parts[3];
              final packets = parts.length > 4 && parts[4].isNotEmpty 
                  ? int.tryParse(parts[4]) ?? 0 
                  : 0;
              
              recordings.add(PocketRecording.fromResponse(dir, timestamp, packets));
            }
          } catch (e) {
            debugPrint('Pocket: Error parsing recording: $e');
          }
        }
      }
    }
    
    debugPrint('Pocket: Found ${recordings.length} recordings');
    return recordings;
  }

  /// Download a recording
  Future<Uint8List?> downloadRecording(
    PocketRecording recording, {
    Function(PocketDownloadProgress)? onProgress,
  }) async {
    debugPrint('Pocket: Downloading ${recording.filename}...');
    
    // Clear buffers
    _responseBuffer.clear();
    _textResponses.clear();
    
    // Send download command
    final cmd = utf8.encode('APP&U&${recording.directory}&${recording.timestamp}');
    
    try {
      await transport.writeCharacteristic(
        pocketServiceUuid,
        pocketCommandCharacteristicUuid,
        cmd,
      );
      
      // Wait for download (30 seconds should be enough)
      // In a real implementation, we'd listen for completion
      await Future.delayed(const Duration(seconds: 30));
      
      // Find MP3 data in buffer
      debugPrint('Pocket: Response buffer size: ${_responseBuffer.length} bytes');
      debugPrint('Pocket: First 20 bytes of buffer: ${_responseBuffer.take(20).toList()}');
      
      final audioStart = _findMarker(_responseBuffer, mp3Marker);
      if (audioStart < 0) {
        debugPrint('Pocket: MP3 marker not found in response');
        return null;
      }
      
      debugPrint('Pocket: MP3 marker found at position $audioStart');
      final audioData = _responseBuffer.sublist(audioStart);
      debugPrint('Pocket: Audio data size: ${audioData.length} bytes');
      debugPrint('Pocket: First 20 bytes of audio data: ${audioData.take(20).toList()}');
      
      // Check if there's any non-zero data
      int nonZeroCount = 0;
      for (int i = 0; i < min(1000, audioData.length); i++) {
        if (audioData[i] != 0 && audioData[i] != 0xFF && audioData[i] != 0xF3 && audioData[i] != 0x48 && audioData[i] != 0xC4) {
          nonZeroCount++;
        }
      }
      debugPrint('Pocket: Non-zero bytes in first 1000: $nonZeroCount');
      
      // Return ALL audio data after the first marker (like Python does)
      // Python doesn't validate frame-by-frame, it just saves everything
      debugPrint('Pocket: Downloaded ${audioData.length} bytes of MP3 data');
      
      return Uint8List.fromList(audioData);
    } catch (e) {
      debugPrint('Pocket: Error downloading recording: $e');
      return null;
    }
  }

  /// Start recording on device
  Future<bool> startRecording() async {
    final responses = await _sendCommand(utf8.encode('APP&REC&SECEN'));
    return responses.any((r) => r.contains('MCU&REC&CON'));
  }

  /// Stop recording on device
  Future<bool> stopRecording() async {
    await _sendCommand(utf8.encode('APP&REC&STOP'));
    return true; // Device responds with MCU&UNKNOWN but recording stops
  }

  /// Find marker in byte list
  int _findMarker(List<int> data, List<int> marker) {
    for (int i = 0; i <= data.length - marker.length; i++) {
      if (_matchesMarker(data, i, marker)) {
        return i;
      }
    }
    return -1;
  }

  /// Check if marker matches at position
  bool _matchesMarker(List<int> data, int pos, List<int> marker) {
    if (pos + marker.length > data.length) return false;
    for (int i = 0; i < marker.length; i++) {
      if (data[pos + i] != marker[i]) return false;
    }
    return true;
  }

  // Override required DeviceConnection methods
  
  @override
  Future<int> performRetrieveBatteryLevel() async {
    final battery = await getBattery();
    return battery ?? -1;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    // Pocket doesn't support battery streaming, so we poll periodically
    _onBatteryLevelChange = onBatteryLevelChange;
    
    // Get initial battery level
    final initialBattery = await getBattery();
    if (initialBattery != null && onBatteryLevelChange != null) {
      onBatteryLevelChange(initialBattery);
    }
    
    // Poll battery every 30 seconds
    _batteryPollTimer?.cancel();
    _batteryPollTimer = Timer.periodic(const Duration(seconds: 30), (timer) async {
      final battery = await getBattery();
      if (battery != null && _onBatteryLevelChange != null) {
        _onBatteryLevelChange!(battery);
      }
    });
    
    // Return a dummy subscription that cancels the timer
    final controller = StreamController<List<int>>();
    return controller.stream.listen(null, onDone: () {
      _batteryPollTimer?.cancel();
      controller.close();
    });
  }

  @override
  Future<List<int>> performGetButtonState() async {
    // Pocket doesn't have a button
    return [];
  }

  @override
  Future<StreamSubscription?> performGetBleButtonListener({
    required void Function(List<int>) onButtonReceived,
  }) async {
    // Pocket doesn't have a button
    return null;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    // Pocket doesn't stream audio in real-time
    // Audio is downloaded as complete MP3 files
    return null;
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    // Pocket uses MP3 format, but we don't stream it
    return BleAudioCodec.pcm8;
  }

  @override
  Future<int> performGetStorageSize() async {
    final storage = await getStorage();
    return storage?.$2 ?? 0;
  }

  @override
  Future<int> performGetStorageUsed() async {
    final storage = await getStorage();
    return storage?.$1 ?? 0;
  }

  @override
  Future<List<int>> performGetStorageList() async {
    // Return empty list - Pocket uses different storage model
    return [];
  }

  @override
  Future<StreamSubscription?> performGetStorageStream({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    // Pocket doesn't support storage streaming
    return null;
  }

  @override
  Future<void> performClearStorage() async {
    // Not supported by Pocket device
    debugPrint('Pocket: Clear storage not supported');
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async {
    // Pocket doesn't support photo streaming
    return false;
  }

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage) onImageReceived,
  }) async {
    // Pocket doesn't support image streaming
    return null;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async {
    // Pocket doesn't have accelerometer
    return null;
  }

  @override
  Future<int> performGetFeatures() async {
    // Pocket doesn't have feature flags
    return 0;
  }

  @override
  Future<void> performSetLedDimRatio(int ratio) async {
    // Pocket doesn't have LED control
    debugPrint('Pocket: LED control not supported');
  }

  @override
  Future<int?> performGetLedDimRatio() async {
    // Pocket doesn't have LED control
    return null;
  }

  @override
  Future<void> performSetMicGain(int gain) async {
    // Pocket doesn't support mic gain control
    debugPrint('Pocket: Mic gain control not supported');
  }

  @override
  Future<int?> performGetMicGain() async {
    // Pocket doesn't support mic gain control
    return null;
  }

  @override
  Future<void> performCameraStartPhotoController() async {
    // Pocket doesn't have camera
    debugPrint('Pocket: Camera not supported');
  }

  @override
  Future<void> performCameraStopPhotoController() async {
    // Pocket doesn't have camera
    debugPrint('Pocket: Camera not supported');
  }

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    // Pocket doesn't support storage byte streaming
    return null;
  }
}
