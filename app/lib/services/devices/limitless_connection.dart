import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';

class LimitlessDeviceConnection extends DeviceConnection {
  int _messageIndex = 0;
  int _requestId = 0;

  final _audioController = StreamController<List<int>>.broadcast();
  final _rawDataBuffer = <int>[];

  StreamSubscription? _rxSubscription;
  bool _isInitialized = false;

  int _highestReceivedIndex = -1;
  int _lastAcknowledgedIndex = -1;

  LimitlessDeviceConnection(super.device, super.transport);

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);

    await Future.delayed(const Duration(seconds: 1));

    _rxSubscription =
        transport.getCharacteristicStream(limitlessServiceUuid, limitlessRxCharUuid).listen(_handleNotification);

    await Future.delayed(const Duration(seconds: 1));

    await _initialize();
  }

  @override
  Future<void> disconnect() async {
    await _rxSubscription?.cancel();
    await _audioController.close();
    await super.disconnect();
  }

  Future<void> _initialize() async {
    // Command 1: Time sync
    final timeSyncCmd = _encodeSetCurrentTime(DateTime.now().millisecondsSinceEpoch);
    await transport.writeCharacteristic(limitlessServiceUuid, limitlessTxCharUuid, timeSyncCmd);
    await Future.delayed(const Duration(seconds: 1));

    // Command 2: Enable data streaming
    final dataStreamCmd = _encodeEnableDataStream();
    await transport.writeCharacteristic(limitlessServiceUuid, limitlessTxCharUuid, dataStreamCmd);
    await Future.delayed(const Duration(seconds: 1));

    _isInitialized = true;
  }

  void _handleNotification(List<int> data) {
    if (data.isEmpty) return;

    if (data.length > 2 && data[0] == 0x08) {
      final indexResult = _decodeVarint(data, 1);
      final packetIndex = indexResult[0] as int;
      if (packetIndex > _highestReceivedIndex) {
        _highestReceivedIndex = packetIndex;
      }
    }

    // Accumulate all received data
    _rawDataBuffer.addAll(data);
  }

  /// Observed pattern in BLE data:
  /// - 0x22 (marker)
  /// - Length byte(s) (varint)
  /// - Opus frame starting with TOC byte
  ///
  /// Returns: (extracted_frames, remaining_buffer_start_position)
  /// The remaining buffer contains any partial frame that spans packet boundaries
  List<dynamic> _extractOpusFrames(List<int> data) {
    final frames = <List<int>>[];
    int pos = 0;
    int lastCompleteFrameEnd = 0;

    while (pos < data.length - 3) {
      // Look for 0x22 marker
      if (data[pos] == 0x22) {
        final markerPos = pos;
        pos++;

        if (pos >= data.length) {
          // Incomplete frame - marker found but no length byte yet
          break;
        }

        // Decode length
        final lengthResult = _decodeVarint(data, pos);
        final length = lengthResult[0] as int;
        final lengthEndPos = lengthResult[1] as int;

        // Check if we have enough data for the complete frame
        if (length >= 10 && length <= 200) {
          final frameStartPos = lengthEndPos;
          final frameEndPos = frameStartPos + length;

          if (frameEndPos <= data.length) {
            // Complete frame available
            final frame = data.sublist(frameStartPos, frameEndPos);

            // Check if first byte is valid Opus TOC
            if (frame.isNotEmpty && _isValidOpusToc(frame[0])) {
              frames.add(frame);
              lastCompleteFrameEnd = frameEndPos;
              pos = frameEndPos;
              continue;
            } else {
              // Invalid TOC, skip this marker and continue searching
              pos = markerPos + 1;
              continue;
            }
          } else {
            // Incomplete frame - we have marker and length but not the full frame data
            // Keep everything from marker position onwards for next extraction
            break;
          }
        } else {
          // Invalid length, skip this marker
          pos = markerPos + 1;
          continue;
        }
      }

      pos++;
    }

    // Return frames and the position where remaining buffer should start
    return [frames, lastCompleteFrameEnd];
  }

  /// Check if byte is a valid Opus TOC byte for pendant audio
  bool _isValidOpusToc(int byte) {
    return byte == 0xb8 || byte == 0x78 || byte == 0xf8 || byte == 0xb0 || byte == 0x70 || byte == 0xf0;
  }

  /// Encode variable-length integer
  List<int> _encodeVarint(int value) {
    final result = <int>[];
    while (value > 0x7f) {
      result.add((value & 0x7f) | 0x80);
      value >>= 7;
    }
    result.add(value & 0x7f);
    return result.isNotEmpty ? result : [0];
  }

  /// Decode variable-length integer
  List<dynamic> _decodeVarint(List<int> data, int pos) {
    int result = 0;
    int shift = 0;
    while (pos < data.length) {
      final byte = data[pos];
      pos++;
      result |= (byte & 0x7f) << shift;
      if ((byte & 0x80) == 0) {
        break;
      }
      shift += 7;
    }
    return [result, pos];
  }

  List<int> _encodeField(int fieldNum, int wireType, List<int> value) {
    final tag = (fieldNum << 3) | wireType;
    return [..._encodeVarint(tag), ...value];
  }

  List<int> _encodeBytesField(int fieldNum, List<int> data) {
    final length = _encodeVarint(data.length);
    return _encodeField(fieldNum, 2, [...length, ...data]);
  }

  List<int> _encodeMessage(int fieldNum, List<int> msgBytes) {
    return _encodeBytesField(fieldNum, msgBytes);
  }

  List<int> _encodeInt64Field(int fieldNum, int value) {
    return _encodeField(fieldNum, 0, _encodeVarint(value));
  }

  List<int> _encodeInt32Field(int fieldNum, int value) {
    return _encodeField(fieldNum, 0, _encodeVarint(value));
  }

  List<int> _encodeBleWrapper(List<int> payload) {
    final msg = <int>[];
    msg.addAll(_encodeInt32Field(1, _messageIndex));
    msg.addAll(_encodeInt32Field(2, 0));
    msg.addAll(_encodeInt32Field(3, 1));
    msg.addAll(_encodeBytesField(4, payload));
    _messageIndex++;
    return msg;
  }

  List<int> _encodeRequestData() {
    _requestId++;
    final msg = <int>[];
    msg.addAll(_encodeInt64Field(1, _requestId));
    msg.addAll(_encodeField(2, 0, [0x00]));
    return _encodeMessage(30, msg);
  }

  /// Pattern: 0x32 (marker), payload contains current time in milliseconds
  List<int> _encodeSetCurrentTime(int timestampMs) {
    final timeMsg = _encodeInt64Field(1, timestampMs);
    final cmd = [..._encodeMessage(6, timeMsg), ..._encodeRequestData()];
    return _encodeBleWrapper(cmd);
  }

  /// Encode data stream enable command
  ///
  /// Observed pattern: 0x42 triggers audio data flow
  /// Field 1: 0x01 (enable) or 0x00 (disable)
  /// Field 2: 0x00 (mode flag)
  List<int> _encodeEnableDataStream({bool enable = true}) {
    final msg = <int>[];
    msg.addAll(_encodeField(1, 0, [enable ? 0x01 : 0x00]));
    msg.addAll(_encodeField(2, 0, [0x00]));
    final cmd = [..._encodeMessage(8, msg), ..._encodeRequestData()];
    return _encodeBleWrapper(cmd);
  }

  List<int> _encodeAcknowledgeProcessedData(int upToIndex) {
    final ackMsg = _encodeInt32Field(1, upToIndex);
    final cmd = [..._encodeMessage(7, ackMsg), ..._encodeRequestData()];
    return _encodeBleWrapper(cmd);
  }

  Future<void> acknowledgeProcessedData(int upToIndex) async {
    if (!_isInitialized) return;

    try {
      final ackCmd = _encodeAcknowledgeProcessedData(upToIndex);
      await transport.writeCharacteristic(limitlessServiceUuid, limitlessTxCharUuid, ackCmd);
      debugPrint('Limitless: Acknowledged processed data up to index $upToIndex');
    } catch (e) {
      debugPrint('Limitless: Error sending acknowledgment: $e');
    }
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final batteryData = await transport.readCharacteristic(
        batteryServiceUuid,
        batteryLevelCharacteristicUuid,
      );
      if (batteryData.isNotEmpty) {
        return batteryData[0];
      }
    } catch (e) {
      debugPrint('Limitless: Error reading battery level: $e');
    }
    return -1;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    if (onBatteryLevelChange == null) {
      return null;
    }

    try {
      final stream = transport.getCharacteristicStream(
        batteryServiceUuid,
        batteryLevelCharacteristicUuid,
      );

      return stream.listen((value) {
        if (value.isNotEmpty) {
          onBatteryLevelChange(value[0]);
        }
      });
    } catch (e) {
      debugPrint('Limitless: Error setting up battery listener: $e');
      return null;
    }
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    return BleAudioCodec.opusFS320;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    if (!_isInitialized) {
      return null;
    }

    final wrapperController = StreamController<List<int>>();
    Timer? extractionTimer;
    StreamSubscription? audioSubscription;

    wrapperController.onCancel = () {
      extractionTimer?.cancel();
      audioSubscription?.cancel();
    };

    extractionTimer = Timer.periodic(const Duration(milliseconds: 500), (timer) {
      if (_rawDataBuffer.isEmpty) return;

      final result = _extractOpusFrames(_rawDataBuffer);
      final frames = result[0] as List<List<int>>;
      final remainingStartPos = result[1] as int;

      if (frames.isNotEmpty) {
        for (final frame in frames) {
          _audioController.add(frame);
        }
      }

      // Remove only the processed bytes, keep any partial frame for next extraction
      if (remainingStartPos > 0) {
        final remaining = _rawDataBuffer.sublist(remainingStartPos);
        _rawDataBuffer.clear();
        _rawDataBuffer.addAll(remaining);
      } else if (frames.isNotEmpty) {
        // If we extracted frames but didn't track position, clear buffer
        // This shouldn't happen with the new logic, but keep as fallback
        _rawDataBuffer.clear();
      }
      // If no frames extracted, keep buffer intact (might be waiting for more data)

      // Safety: prevent buffer from growing unbounded (max 64KB)
      if (_rawDataBuffer.length > 65536) {
        debugPrint('Limitless: Buffer overflow, clearing buffer');
        _rawDataBuffer.clear();
      }

      if (_highestReceivedIndex > _lastAcknowledgedIndex && frames.isNotEmpty) {
        _lastAcknowledgedIndex = _highestReceivedIndex;
        acknowledgeProcessedData(_highestReceivedIndex);
      }
    });

    audioSubscription = _audioController.stream.listen(
      (frame) => wrapperController.add(frame),
      onDone: () => wrapperController.close(),
    );

    return wrapperController.stream.listen(onAudioBytesReceived);
  }

  @override
  Future<List<int>> performGetButtonState() async => [];

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async =>
      null;

  @override
  Future performCameraStartPhotoController() async {}

  @override
  Future performCameraStopPhotoController() async {}

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async => false;

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async =>
      null;

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async =>
      null;

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

  Future<Map<String, String>> getDeviceInfo() async {
    return {
      'modelNumber': 'Limitless Pendant',
      'firmwareRevision': '1.0.0',
      'hardwareRevision': 'Unknown',
      'manufacturerName': 'Limitless',
    };
  }
}
