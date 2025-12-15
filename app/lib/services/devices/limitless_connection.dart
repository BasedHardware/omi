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
  final _flashPageController = StreamController<Map<String, dynamic>>.broadcast();
  final _buttonController = StreamController<List<int>>.broadcast();
  final _rawDataBuffer = <int>[];
  int? _firstFlashPageTimestampMs;

  // Fragment reassembly: index -> {seq -> payload}
  final Map<int, Map<int, List<int>>> _fragmentBuffer = {};

  // Completed flash pages
  final List<Map<String, dynamic>> _completedFlashPages = [];

  StreamSubscription? _rxSubscription;
  bool _isInitialized = false;
  bool _isBatchMode = false;

  int _highestReceivedIndex = -1;
  int _lastAcknowledgedIndex = -1;

  static const int _buttonNotPressed = 0;
  static const int _buttonShortPress = 1;
  static const int _buttonLongPress = 2;
  static const int _buttonDoublePress = 3;

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
    await _flashPageController.close();
    await _buttonController.close();
    _isBatchMode = false;
    await super.disconnect();
  }

  Future<void> _initialize() async {
    try {
      // Command 1: Time sync
      final timeSyncCmd = _encodeSetCurrentTime(DateTime.now().millisecondsSinceEpoch);
      await transport.writeCharacteristic(limitlessServiceUuid, limitlessTxCharUuid, timeSyncCmd);
      await Future.delayed(const Duration(seconds: 1));

      // Command 2: Enable data streaming
      final dataStreamCmd = _encodeEnableDataStream();
      await transport.writeCharacteristic(limitlessServiceUuid, limitlessTxCharUuid, dataStreamCmd);
      await Future.delayed(const Duration(seconds: 1));

      _isInitialized = true;
    } catch (e) {
      debugPrint('Limitless: Initialization failed: $e');
      rethrow;
    }
  }

  void _handleNotification(List<int> data) {
    if (data.isEmpty) return;

    _tryParseButtonStatus(data);
    _tryParseDeviceStatus(data);

    // Parse BLE packet to get fragmentation info
    final packet = _parseBlePacket(data);
    if (packet == null) {
      if (_isBatchMode) {
        debugPrint(
            'Limitless: Batch mode - packet parse failed, data=${data.length}b, first bytes: ${data.take(10).toList()}');
      }
      _rawDataBuffer.addAll(data);
      return;
    }

    final index = packet['index'] as int;
    final seq = packet['seq'] as int;
    final numFrags = packet['num_frags'] as int;
    final payload = packet['payload'] as List<int>;

    // Track highest received index for acknowledgment
    if (index > _highestReceivedIndex) {
      _highestReceivedIndex = index;
    }

    if (_isBatchMode) {
      _fragmentBuffer.putIfAbsent(index, () => {});
      _fragmentBuffer[index]![seq] = payload;

      if (_fragmentBuffer[index]!.length == numFrags) {
        final completePayload = <int>[];
        for (int i = 0; i < numFrags; i++) {
          final fragment = _fragmentBuffer[index]![i];
          if (fragment != null) {
            completePayload.addAll(fragment);
          }
        }

        _fragmentBuffer.remove(index);

        _handlePendantMessage(completePayload);
      }
    } else {
      _rawDataBuffer.addAll(data);
    }
  }

  void _handlePendantMessage(List<int> payload) {
    try {
      int pos = 0;
      List<int> foundFields = [];

      while (pos < payload.length) {
        final tag = payload[pos];
        final fieldNum = tag >> 3;
        final wireType = tag & 0x07;
        pos++;

        foundFields.add(fieldNum);

        if (wireType == 2) {
          // Length-delimited field
          final lengthResult = _decodeVarint(payload, pos);
          final length = lengthResult[0] as int;
          pos = lengthResult[1] as int;

          final fieldData = payload.sublist(pos, pos + length);
          pos += length;

          if (fieldNum == 2) {
            _handleStorageBuffer(fieldData);
          }
        } else if (wireType == 0) {
          final result = _decodeVarint(payload, pos);
          pos = result[1] as int;
        } else {
          // Unknown wire type, skip byte
          pos++;
        }
      }
    } catch (e) {
      debugPrint('Limitless: Error handling pendant message: $e');
    }
  }

  void _handleStorageBuffer(List<int> storageData) {
    try {
      int pos = 0;
      int? session;
      int? seq;
      int? index;
      List<int>? flashPageData;

      while (pos < storageData.length) {
        final tag = storageData[pos];
        final fieldNum = tag >> 3;
        final wireType = tag & 0x07;
        pos++;

        if (wireType == 0) {
          // Varint
          final result = _decodeVarint(storageData, pos);
          final value = result[0] as int;
          pos = result[1] as int;

          if (fieldNum == 2) {
            session = value;
          } else if (fieldNum == 4) {
            seq = value;
          } else if (fieldNum == 5) {
            index = value;
          }
        } else if (wireType == 2) {
          // Length-delimited
          final lengthResult = _decodeVarint(storageData, pos);
          final length = lengthResult[0] as int;
          pos = lengthResult[1] as int;

          if (fieldNum == 6) {
            flashPageData = storageData.sublist(pos, pos + length);
          }
          pos += length;
        } else {
          pos++;
        }
      }

      if (flashPageData != null && flashPageData.isNotEmpty) {
        final pageInfo = _parseFlashPageInfo(flashPageData);

        final opusFrames = _extractOpusFramesFromFlashPage(flashPageData);

        if (opusFrames.isNotEmpty) {
          final flashPage = {
            'opus_frames': opusFrames,
            'timestamp_ms': pageInfo['timestamp_ms'] ?? DateTime.now().millisecondsSinceEpoch,
            'session': session,
            'seq': seq,
            'index': index,
            'did_start_session': pageInfo['did_start_session'] ?? false,
            'did_stop_session': pageInfo['did_stop_session'] ?? false,
            'did_start_recording': pageInfo['did_start_recording'] ?? false,
            'did_stop_recording': pageInfo['did_stop_recording'] ?? false,
          };

          _completedFlashPages.add(flashPage);

          // Update first flash page timestamp if not set
          if (_firstFlashPageTimestampMs == null) {
            final timestamp = pageInfo['timestamp_ms'] as int?;
            if (timestamp != null && timestamp > 1577836800000) {
              _firstFlashPageTimestampMs = timestamp;
            }
          }

          _flashPageController.add(flashPage);
        }
      }
    } catch (e) {
      debugPrint('Limitless: Error handling storage buffer: $e');
    }
  }

  Map<String, dynamic> _parseFlashPageInfo(List<int> flashPageData) {
    Map<String, dynamic> result = {
      'timestamp_ms': 0,
      'did_start_session': false,
      'did_stop_session': false,
      'did_start_recording': false,
      'did_stop_recording': false,
    };

    try {
      int pos = 0;

      // Field 1 (0x08) = timestamp_ms
      if (pos < flashPageData.length && flashPageData[pos] == 0x08) {
        pos++;
        final timestampResult = _decodeVarint(flashPageData, pos);
        result['timestamp_ms'] = timestampResult[0] as int;
        pos = timestampResult[1] as int;
      }

      while (pos < flashPageData.length - 2) {
        // Audio wrapper (0x1a)
        if (flashPageData[pos] == 0x1a) {
          pos++;
          final chunkLengthResult = _decodeVarint(flashPageData, pos);
          final chunkLength = chunkLengthResult[0] as int;
          pos = chunkLengthResult[1] as int;

          final chunkEnd = pos + chunkLength;

          while (pos < chunkEnd - 1) {
            final marker = flashPageData[pos];

            // Storage status (0x62)
            if (marker == 0x62) {
              pos++;
              final statusLengthResult = _decodeVarint(flashPageData, pos);
              final statusLength = statusLengthResult[0] as int;
              pos = statusLengthResult[1] as int;

              final statusEnd = pos + statusLength;
              while (pos < statusEnd) {
                final statusMarker = flashPageData[pos];
                pos++;

                if (statusMarker == 0x08 && pos < statusEnd) {
                  result['did_start_session'] = flashPageData[pos] != 0;
                  pos++;
                } else if (statusMarker == 0x10 && pos < statusEnd) {
                  result['did_stop_session'] = flashPageData[pos] != 0;
                  pos++;
                }
              }
              continue;
            }

            // Audio data (0x12)
            if (marker == 0x12) {
              pos++;
              final audioLengthResult = _decodeVarint(flashPageData, pos);
              final audioLength = audioLengthResult[0] as int;
              pos = audioLengthResult[1] as int;

              final audioEnd = pos + audioLength;
              while (pos < audioEnd - 1) {
                final audioMarker = flashPageData[pos];
                pos++;

                if (audioMarker == 0x40 && pos < audioEnd) {
                  result['did_start_recording'] = flashPageData[pos] != 0;
                  pos++;
                } else if (audioMarker == 0x48 && pos < audioEnd) {
                  result['did_stop_recording'] = flashPageData[pos] != 0;
                  pos++;
                }
              }
              pos = audioEnd;
              continue;
            }

            pos++;
          }
          pos = chunkEnd;
        } else {
          pos++;
        }
      }
    } catch (e) {
      // Silently ignore parsing errors
    }

    return result;
  }

  List<List<int>> _extractOpusFramesFromFlashPage(List<int> flashPageData) {
    final frames = <List<int>>[];

    try {
      int pos = 0;

      // Skip timestamp (0x08) if present
      if (pos < flashPageData.length && flashPageData[pos] == 0x08) {
        pos++;
        final result = _decodeVarint(flashPageData, pos);
        pos = result[1] as int;
      }

      // Skip 0x10 if present
      if (pos < flashPageData.length && flashPageData[pos] == 0x10) {
        pos++;
        final result = _decodeVarint(flashPageData, pos);
        pos = result[1] as int;
      }

      // Process audio wrappers (0x1a)
      while (pos < flashPageData.length - 2) {
        if (flashPageData[pos] == 0x1a) {
          pos++;
          final wrapperLengthResult = _decodeVarint(flashPageData, pos);
          final wrapperLength = wrapperLengthResult[0] as int;
          pos = wrapperLengthResult[1] as int;

          final wrapperEnd = pos + wrapperLength;
          if (wrapperEnd > flashPageData.length) break;

          while (pos < wrapperEnd - 1) {
            final marker = flashPageData[pos];

            // Offset (0x08) - skip
            if (marker == 0x08) {
              pos++;
              final result = _decodeVarint(flashPageData, pos);
              pos = result[1] as int;
              continue;
            }

            // Audio data (0x12) containing Opus packets
            if (marker == 0x12) {
              pos++;
              final audioLengthResult = _decodeVarint(flashPageData, pos);
              final audioLength = audioLengthResult[0] as int;
              pos = audioLengthResult[1] as int;

              final audioEnd = pos + audioLength;
              if (audioEnd > flashPageData.length) {
                pos = wrapperEnd;
                break;
              }

              _extractOpusRecursive(flashPageData, pos, audioEnd, frames);
              pos = audioEnd;
              continue;
            }

            // Skip other wire types
            final wireType = marker & 0x07;
            pos++;
            if (wireType == 0) {
              final result = _decodeVarint(flashPageData, pos);
              pos = result[1] as int;
            } else if (wireType == 2) {
              final lengthResult = _decodeVarint(flashPageData, pos);
              pos = lengthResult[1] as int;
              pos += lengthResult[0] as int;
            }
          }

          pos = wrapperEnd;
        } else {
          pos++;
        }
      }
    } catch (e) {
      debugPrint('Limitless: Error extracting Opus frames from flash page: $e');
    }

    return frames;
  }

  void _extractOpusRecursive(List<int> data, int start, int end, List<List<int>> frames) {
    int pos = start;

    while (pos < end - 1) {
      final tag = data[pos];
      final wireType = tag & 0x07;
      pos++;

      if (wireType == 2) {
        // Length-delimited
        final lengthResult = _decodeVarint(data, pos);
        final length = lengthResult[0] as int;
        pos = lengthResult[1] as int;

        if (length > 0 && pos + length <= end) {
          final fieldData = data.sublist(pos, pos + length);

          if (length >= 10 && length <= 200 && fieldData.isNotEmpty && _isValidOpusToc(fieldData[0])) {
            frames.add(fieldData);
          } else if (length > 10) {
            _extractOpusRecursive(data, pos, pos + length, frames);
          }
        }
        pos += length;
      } else if (wireType == 0) {
        // Varint
        final result = _decodeVarint(data, pos);
        pos = result[1] as int;
      } else {
        // Unknown wire type
        break;
      }
    }
  }

  /// Observed pattern in BLE data:
  /// - 0x22 (marker)
  /// - Length byte(s) (varint)
  /// - Opus frame starting with TOC byte
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
            break;
          }
        } else {
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

  /// Parse BLE packet to extract index, sequence, number of fragments, and payload
  Map<String, dynamic>? _parseBlePacket(List<int> data) {
    try {
      int pos = 0;
      int? index;
      int seq = 0;
      int? numFrags;
      List<int>? payload;

      while (pos < data.length) {
        final tag = data[pos];
        final fieldNum = tag >> 3;
        final wireType = tag & 0x07;
        pos++;

        if (wireType == 0) {
          // Varint
          final result = _decodeVarint(data, pos);
          final value = result[0] as int;
          pos = result[1] as int;

          if (fieldNum == 1) {
            index = value;
          } else if (fieldNum == 2) {
            seq = value;
          } else if (fieldNum == 3) {
            numFrags = value;
          }
        } else if (wireType == 2) {
          // Length-delimited
          final lengthResult = _decodeVarint(data, pos);
          final length = lengthResult[0] as int;
          pos = lengthResult[1] as int;

          if (fieldNum == 4) {
            payload = data.sublist(pos, pos + length);
          }
          pos += length;
        } else {
          // Unknown wire type, skip
          break;
        }
      }

      if (index != null && numFrags != null && payload != null) {
        return {
          'index': index,
          'seq': seq,
          'num_frags': numFrags,
          'payload': payload,
        };
      }
    } catch (e) {
      debugPrint('Limitless: Error parsing BLE wrapper: $e');
    }
    return null;
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
    msg.addAll(_encodeField(1, 0, [0x00]));
    msg.addAll(_encodeField(2, 0, [enable ? 0x01 : 0x00]));
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

  // ============================================
  //          Storage Status Methods
  // ============================================

  /// Last parsed storage state
  Map<String, int>? _storageState;

  /// Completer for waiting on storage state response
  Completer<Map<String, int>?>? _storageStateCompleter;

  List<int> _encodeGetDeviceStatus() {
    final cmd = [..._encodeMessage(21, []), ..._encodeRequestData()];
    return _encodeBleWrapper(cmd);
  }

  /// Encode DownloadFlashPages command (0x08, length-delimited)
  /// 1: batchModeEnabled - sync stored offline recordings
  /// 2: realTimeModeEnabled - stream live audio
  List<int> _encodeDownloadFlashPages({bool batchMode = true, bool realTime = false}) {
    final msg = <int>[];
    msg.addAll(_encodeField(1, 0, [batchMode ? 0x01 : 0x00]));
    msg.addAll(_encodeField(2, 0, [realTime ? 0x01 : 0x00]));
    final cmd = [..._encodeMessage(8, msg), ..._encodeRequestData()];
    return _encodeBleWrapper(cmd);
  }

  /// Get storage status
  Future<Map<String, int>?> getStorageStatus() async {
    if (!_isInitialized) {
      debugPrint('Limitless: Device not initialized');
      return null;
    }

    try {
      _storageStateCompleter = Completer<Map<String, int>?>();

      // Send GetDeviceStatus command
      final statusCmd = _encodeGetDeviceStatus();
      await transport.writeCharacteristic(limitlessServiceUuid, limitlessTxCharUuid, statusCmd);

      // Wait for response with timeout
      final result = await _storageStateCompleter!.future.timeout(
        const Duration(seconds: 3),
        onTimeout: () => _storageState,
      );

      _storageStateCompleter = null;
      return result ?? _storageState;
    } catch (e) {
      debugPrint('Limitless: Error getting storage status: $e');
      _storageStateCompleter = null;
      return null;
    }
  }

  /// Get count of available flash pages
  Future<int> getFlashPageCount() async {
    final status = await getStorageStatus();
    if (status == null) return 0;

    final oldest = status['oldest_flash_page'] ?? 0;
    final newest = status['newest_flash_page'] ?? 0;

    if (newest >= oldest) {
      return newest - oldest + 1;
    }
    return 0;
  }

  /// Enable batch mode to download stored flash pages (offline recordings)
  Future<void> enableBatchMode() async {
    if (!_isInitialized) return;

    try {
      // Clear all buffers before switching modes to prevent cross-contamination
      _rawDataBuffer.clear();
      _fragmentBuffer.clear();
      _completedFlashPages.clear();
      _isBatchMode = true;
      final cmd = _encodeDownloadFlashPages(batchMode: true, realTime: false);
      await transport.writeCharacteristic(limitlessServiceUuid, limitlessTxCharUuid, cmd);
    } catch (e) {
      _isBatchMode = false;
      debugPrint('Limitless: Error enabling batch mode: $e');
    }
  }

  /// Disable batch mode and switch back to real-time streaming
  Future<void> disableBatchMode() async {
    if (!_isInitialized) return;

    try {
      // Clear all buffers before switching modes to prevent batch data from being processed as real-time
      _rawDataBuffer.clear();
      _fragmentBuffer.clear();
      _completedFlashPages.clear();
      _firstFlashPageTimestampMs = null;

      // Send command to switch back to real-time mode
      final cmd = _encodeDownloadFlashPages(batchMode: false, realTime: true);
      await transport.writeCharacteristic(limitlessServiceUuid, limitlessTxCharUuid, cmd);

      _isBatchMode = false;
    } catch (e) {
      _isBatchMode = false;
    }
  }

  /// Switch back to real-time mode
  Future<void> enableRealTimeMode() async {
    await disableBatchMode();
  }

  Stream<Map<String, dynamic>> getFlashPageStream() {
    return _flashPageController.stream;
  }

  bool get isBatchMode => _isBatchMode;

  List<List<int>> extractFramesFromBuffer() {
    if (_rawDataBuffer.isEmpty) return [];

    if (_isBatchMode && _firstFlashPageTimestampMs == null) {
      _tryParseFlashPageTimestamp();
    }

    final result = _extractOpusFrames(_rawDataBuffer);
    final frames = result[0] as List<List<int>>;
    final remainingStartPos = result[1] as int;

    if (remainingStartPos > 0) {
      final remaining = _rawDataBuffer.sublist(remainingStartPos);
      _rawDataBuffer.clear();
      _rawDataBuffer.addAll(remaining);
    } else if (frames.isNotEmpty) {
      _rawDataBuffer.clear();
    }

    return frames;
  }

  /// Try to parse flash page timestamp from the accumulated buffer
  void _tryParseFlashPageTimestamp() {
    final flashPage = parseStorageBuffer(_rawDataBuffer);
    if (flashPage != null && flashPage['timestamp_ms'] != null) {
      final timestamp = flashPage['timestamp_ms'] as int;
      if (timestamp > 1577836800000) {
        _firstFlashPageTimestampMs = timestamp;
      }
    }
  }

  void clearBuffer() {
    _rawDataBuffer.clear();
    _firstFlashPageTimestampMs = null;
    _fragmentBuffer.clear();
    _completedFlashPages.clear();
  }

  int? getFirstFlashPageTimestampMs() => _firstFlashPageTimestampMs;

  void resetFlashPageTimestamp() {
    _firstFlashPageTimestampMs = null;
  }

  /// Extract opus frames from buffer along with session marker info
  /// Returns map with: opus_frames, timestamp_ms, did_start_session, did_stop_session, etc.
  /// This combines frame extraction with session marker parsing
  Map<String, dynamic>? extractFramesWithSessionInfo() {
    if (_isBatchMode) {
      if (_completedFlashPages.isEmpty) return null;

      final allFrames = <List<int>>[];
      int? timestampMs;
      bool didStartSession = false;
      bool didStopSession = false;
      bool didStartRecording = false;
      bool didStopRecording = false;
      int? maxIndex;

      for (final page in _completedFlashPages) {
        final frames = page['opus_frames'] as List<List<int>>?;
        if (frames != null) {
          allFrames.addAll(frames);
        }

        // Use timestamp from first page
        if (timestampMs == null) {
          final ts = page['timestamp_ms'] as int?;
          if (ts != null && ts > 1577836800000) {
            timestampMs = ts;
          }
        }

        // Track the highest index for ACK
        final pageIndex = page['index'] as int?;
        if (pageIndex != null && (maxIndex == null || pageIndex > maxIndex)) {
          maxIndex = pageIndex;
        }

        // Aggregate session markers
        if (page['did_start_session'] == true) didStartSession = true;
        if (page['did_stop_session'] == true) didStopSession = true;
        if (page['did_start_recording'] == true) didStartRecording = true;
        if (page['did_stop_recording'] == true) didStopRecording = true;
      }

      // Clear processed flash pages
      _completedFlashPages.clear();

      if (allFrames.isEmpty) return null;

      return {
        'opus_frames': allFrames,
        'timestamp_ms': timestampMs ?? _firstFlashPageTimestampMs ?? DateTime.now().millisecondsSinceEpoch,
        'did_start_session': didStartSession,
        'did_stop_session': didStopSession,
        'did_start_recording': didStartRecording,
        'did_stop_recording': didStopRecording,
        'max_index': maxIndex,
      };
    }

    if (_rawDataBuffer.isEmpty) return null;

    final sessionInfo = parseStorageBuffer(_rawDataBuffer);

    final frames = extractFramesFromBuffer();

    if (frames.isEmpty) return null;

    // Get timestamp
    int? timestampMs = sessionInfo?['timestamp_ms'] as int?;
    if (timestampMs == null || timestampMs < 1577836800000) {
      timestampMs = _firstFlashPageTimestampMs ?? DateTime.now().millisecondsSinceEpoch;
    }

    final result = {
      'opus_frames': frames,
      'timestamp_ms': timestampMs,
      'did_start_session': sessionInfo?['did_start_session'] ?? false,
      'did_stop_session': sessionInfo?['did_stop_session'] ?? false,
      'did_start_recording': sessionInfo?['did_start_recording'] ?? false,
      'did_stop_recording': sessionInfo?['did_stop_recording'] ?? false,
    };

    return result;
  }

  List<List<int>> extractOpusFramesFromPage(List<int> flashPageData) {
    final frames = <List<int>>[];

    const audioDataMarkers = [0x0a, 0x12, 0x1a, 0x22, 0x2a, 0x32, 0x3a];

    try {
      int pos = 0;

      if (pos < flashPageData.length && flashPageData[pos] == 0x08) {
        pos++;
        final timestampResult = _decodeVarint(flashPageData, pos);
        pos = timestampResult[1] as int;
      }

      if (pos < flashPageData.length && flashPageData[pos] == 0x10) {
        pos++;
        final uptimeResult = _decodeVarint(flashPageData, pos);
        pos = uptimeResult[1] as int;
      }

      while (pos < flashPageData.length - 2) {
        if (flashPageData[pos] == 0x1a) {
          pos++;
          final chunkLengthResult = _decodeVarint(flashPageData, pos);
          final chunkLength = chunkLengthResult[0] as int;
          pos = chunkLengthResult[1] as int;

          final chunkEnd = pos + chunkLength;
          if (chunkEnd > flashPageData.length) break;

          while (pos < chunkEnd - 1) {
            if (flashPageData[pos] == 0x08) {
              pos++;
              final offsetResult = _decodeVarint(flashPageData, pos);
              pos = offsetResult[1] as int;
              continue;
            }

            if (flashPageData[pos] == 0x12) {
              pos++;
              final audioLengthResult = _decodeVarint(flashPageData, pos);
              final audioLength = audioLengthResult[0] as int;
              pos = audioLengthResult[1] as int;

              final audioEnd = pos + audioLength;
              if (audioEnd > flashPageData.length) {
                pos = chunkEnd;
                break;
              }

              while (pos < audioEnd - 1) {
                final marker = flashPageData[pos];

                if (audioDataMarkers.contains(marker)) {
                  pos++;
                  if (pos >= audioEnd) break;

                  final frameLengthResult = _decodeVarint(flashPageData, pos);
                  final frameLength = frameLengthResult[0] as int;
                  pos = frameLengthResult[1] as int;

                  if (frameLength > 0 && frameLength <= 200 && pos + frameLength <= flashPageData.length) {
                    final frame = flashPageData.sublist(pos, pos + frameLength);
                    if (frame.isNotEmpty && _isValidOpusToc(frame[0])) {
                      frames.add(frame);
                    }
                    pos += frameLength;
                  } else {
                    pos++;
                  }
                } else if ((marker & 0x07) == 0) {
                  pos++;
                  if (pos >= audioEnd) break;
                  final skipResult = _decodeVarint(flashPageData, pos);
                  pos = skipResult[1] as int;
                } else {
                  pos++;
                }
              }
              pos = audioEnd;
              continue;
            }

            final marker = flashPageData[pos];
            if ((marker & 0x07) == 0) {
              pos++;
              if (pos >= chunkEnd) break;
              final skipResult = _decodeVarint(flashPageData, pos);
              pos = skipResult[1] as int;
            } else if ((marker & 0x07) == 2) {
              pos++;
              if (pos >= chunkEnd) break;
              final skipLengthResult = _decodeVarint(flashPageData, pos);
              final skipLen = skipLengthResult[0] as int;
              pos = skipLengthResult[1] as int;
              pos += skipLen;
            } else {
              pos++;
            }
          }

          pos = chunkEnd;
        } else {
          pos++;
        }
      }
    } catch (e) {
      debugPrint('Limitless: Error extracting opus frames from page: $e');
    }

    return frames;
  }

  void _tryParseButtonStatus(List<int> data) {
    try {
      if (data.length < 10) return;

      int pos = 0;
      while (pos < data.length - 5) {
        if (data[pos] == 0x22) {
          pos++;
          if (pos >= data.length) return;

          final lengthResult = _decodeVarint(data, pos);
          final payloadLength = lengthResult[0] as int;
          pos = lengthResult[1] as int;

          if (payloadLength < 2 || payloadLength > data.length - pos) return;

          if (data[pos] != 0x42) return;

          int innerPos = pos + 1;
          if (innerPos >= data.length) return;

          final buttonLengthResult = _decodeVarint(data, innerPos);
          final buttonLength = buttonLengthResult[0] as int;
          innerPos = buttonLengthResult[1] as int;

          if (buttonLength < 2 || buttonLength > 50 || innerPos + buttonLength > data.length) return;

          final buttonEnd = innerPos + buttonLength;
          while (innerPos < buttonEnd - 1) {
            if (data[innerPos] == 0x08) {
              innerPos++;
              final eventResult = _decodeVarint(data, innerPos);
              final buttonEvent = eventResult[0] as int;

              if (buttonEvent < 0 || buttonEvent > 4) return;

              // Skip NOT_PRESSED events
              if (buttonEvent == _buttonNotPressed) return;

              // Skip LONG_PRESS - Limitless uses this to start/stop recording on device
              if (buttonEvent == _buttonLongPress) return;

              // Skip SHORT_PRESS -  what to do with this?
              if (buttonEvent == _buttonShortPress) return;

              // DOUBLE_PRESS
              if (buttonEvent != _buttonDoublePress) return;

              // Double press -> pause/resume/process conversation
              const int mappedState = 2;

              final buttonBytes = [
                mappedState & 0xFF,
                (mappedState >> 8) & 0xFF,
                (mappedState >> 16) & 0xFF,
                (mappedState >> 24) & 0xFF,
              ];
              _buttonController.add(buttonBytes);
              return;
            }
            innerPos++;
          }
          return;
        }
        pos++;
      }
    } catch (e) {
      // Silently ignore parsing errors
    }
  }

  void _tryParseDeviceStatus(List<int> data) {
    try {
      if (data.length < 20) return;

      int pos = 0;
      while (pos < data.length - 5) {
        if (data[pos] == 0x22) {
          pos++;
          if (pos >= data.length) return;

          final lengthResult = _decodeVarint(data, pos);
          final payloadLength = lengthResult[0] as int;
          pos = lengthResult[1] as int;

          if (payloadLength < 10 || payloadLength > data.length - pos) return;

          final payloadEnd = pos + payloadLength;
          int innerPos = pos;

          while (innerPos < payloadEnd - 5) {
            if (data[innerPos] == 0x2a) {
              innerPos++;
              if (innerPos >= data.length) return;

              final statusLengthResult = _decodeVarint(data, innerPos);
              final statusLength = statusLengthResult[0] as int;
              innerPos = statusLengthResult[1] as int;

              if (statusLength < 5 || statusLength > 500 || innerPos + statusLength > data.length) {
                return;
              }

              final storageState = _parseStorageStateFromDeviceStatus(data, innerPos, innerPos + statusLength);
              if (storageState != null && storageState.isNotEmpty) {
                _storageState = storageState;
                _storageStateCompleter?.complete(storageState);
              }
              return;
            }
            innerPos++;
          }
          return;
        }
        pos++;
      }
    } catch (e) {
      // Silently ignore parsing errors because not all packets are DeviceStatus messages
    }
  }

  Map<String, int>? _parseStorageStateFromDeviceStatus(List<int> data, int start, int end) {
    try {
      if (start < 0 || end > data.length || start >= end) return null;

      int pos = start;
      Map<String, int> state = {};

      while (pos < end - 1 && pos < data.length) {
        final fieldMarker = data[pos];

        // (0x2a, length-delimited)
        if (fieldMarker == 0x2a) {
          pos++;
          if (pos >= data.length) break;

          final lengthResult = _decodeVarint(data, pos);
          final storageLength = lengthResult[0] as int;
          pos = lengthResult[1] as int;

          if (storageLength < 0 || storageLength > 200 || pos + storageLength > data.length) {
            break;
          }

          final storageEnd = pos + storageLength;

          while (pos < storageEnd - 1 && pos < data.length) {
            final marker = data[pos];
            pos++;
            if (pos >= data.length) break;

            // Field markers: 0x08=f1, 0x10=f2, 0x18=f3, 0x20=f4, 0x28=f5
            if (marker == 0x08 || marker == 0x10 || marker == 0x18 || marker == 0x20 || marker == 0x28) {
              final valueResult = _decodeVarint(data, pos);
              final value = valueResult[0] as int;
              pos = valueResult[1] as int;

              switch (marker) {
                case 0x08:
                  state['oldest_flash_page'] = value;
                  break;
                case 0x10:
                  state['newest_flash_page'] = value;
                  break;
                case 0x18:
                  state['current_storage_session'] = value;
                  break;
                case 0x20:
                  state['free_capture_pages'] = value;
                  break;
                case 0x28:
                  state['total_capture_pages'] = value;
                  break;
              }
            }
          }

          return state.isNotEmpty ? state : null;
        }
        pos++;
      }
    } catch (e) {
      // Silently ignore parsing errors because not all packets are the required type
    }
    return null;
  }

  Map<String, dynamic>? parseStorageBuffer(List<int> data) {
    try {
      int pos = 0;

      while (pos < data.length - 1) {
        if (data[pos] == 0x22) {
          pos++;
          final lengthResult = _decodeVarint(data, pos);
          final payloadLength = lengthResult[0] as int;
          pos = lengthResult[1] as int;

          int innerPos = pos;
          final endPos = pos + payloadLength;

          while (innerPos < endPos - 1) {
            if (data[innerPos] == 0x12) {
              innerPos++;
              final storageLengthResult = _decodeVarint(data, innerPos);
              final storageLength = storageLengthResult[0] as int;
              innerPos = storageLengthResult[1] as int;

              final storageEnd = innerPos + storageLength;
              int storagePos = innerPos;

              Map<String, dynamic> result = {};

              while (storagePos < storageEnd - 1) {
                final marker = data[storagePos];

                // (0x32, length-delimited)
                if (marker == 0x32) {
                  storagePos++;
                  final flashPageLengthResult = _decodeVarint(data, storagePos);
                  final flashPageLength = flashPageLengthResult[0] as int;
                  storagePos = flashPageLengthResult[1] as int;

                  result['flash_page_data'] = data.sublist(storagePos, storagePos + flashPageLength);

                  final sessionInfo =
                      _parseFlashPageSessionMarkers(data.sublist(storagePos, storagePos + flashPageLength));
                  result.addAll(sessionInfo);

                  return result;
                }

                storagePos++;
              }
            }
            innerPos++;
          }
          break;
        }
        pos++;
      }
    } catch (e) {
      debugPrint('Limitless: Error parsing StorageBufferMsg: $e');
    }
    return null;
  }

  Map<String, dynamic> _parseFlashPageSessionMarkers(List<int> flashPageData) {
    Map<String, dynamic> result = {
      'did_start_session': false,
      'did_stop_session': false,
      'did_start_recording': false,
      'did_stop_recording': false,
      'timestamp_ms': 0,
    };

    try {
      int pos = 0;

      // (0x08, varint)
      if (pos < flashPageData.length && flashPageData[pos] == 0x08) {
        pos++;
        final timestampResult = _decodeVarint(flashPageData, pos);
        result['timestamp_ms'] = timestampResult[0] as int;
        pos = timestampResult[1] as int;
      }

      // (0x1a, length-delimited)
      while (pos < flashPageData.length - 2) {
        if (flashPageData[pos] == 0x1a) {
          pos++;
          final chunkLengthResult = _decodeVarint(flashPageData, pos);
          final chunkLength = chunkLengthResult[0] as int;
          pos = chunkLengthResult[1] as int;

          final chunkEnd = pos + chunkLength;

          // (0x62, length-delimited) and (0x12, length-delimited)
          while (pos < chunkEnd - 1) {
            final marker = flashPageData[pos];

            // (0x62, length-delimited)
            if (marker == 0x62) {
              pos++;
              final storageStatusResult = _decodeVarint(flashPageData, pos);
              final statusLength = storageStatusResult[0] as int;
              pos = storageStatusResult[1] as int;

              final statusEnd = pos + statusLength;
              while (pos < statusEnd) {
                final statusMarker = flashPageData[pos];
                pos++;

                // (0x08, varint)
                if (statusMarker == 0x08 && pos < statusEnd) {
                  result['did_start_session'] = flashPageData[pos] != 0;
                  pos++;
                }
                // (0x10, varint)
                else if (statusMarker == 0x10 && pos < statusEnd) {
                  result['did_stop_session'] = flashPageData[pos] != 0;
                  pos++;
                }
              }
              continue;
            }

            // (0x12, length-delimited)
            if (marker == 0x12) {
              pos++;
              final audioLengthResult = _decodeVarint(flashPageData, pos);
              final audioLength = audioLengthResult[0] as int;
              pos = audioLengthResult[1] as int;

              final audioEnd = pos + audioLength;
              while (pos < audioEnd - 1) {
                final audioMarker = flashPageData[pos];
                pos++;

                // (0x40, varint)
                if (audioMarker == 0x40 && pos < audioEnd) {
                  result['did_start_recording'] = flashPageData[pos] != 0;
                  pos++;
                }
                // (0x48, varint)
                else if (audioMarker == 0x48 && pos < audioEnd) {
                  result['did_stop_recording'] = flashPageData[pos] != 0;
                  pos++;
                }
              }
              continue;
            }

            pos++;
          }
        } else {
          pos++;
        }
      }
    } catch (e) {
      // Silently ignore parsing errors because not all packets are the required type
    }

    return result;
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
      if (_isBatchMode) {
        return;
      }

      if (_rawDataBuffer.isEmpty) return;

      final result = _extractOpusFrames(_rawDataBuffer);
      final frames = result[0] as List<List<int>>;
      final remainingStartPos = result[1] as int;

      if (frames.isNotEmpty) {
        for (final frame in frames) {
          _audioController.add(frame);
        }
      }

      if (remainingStartPos > 0) {
        final remaining = _rawDataBuffer.sublist(remainingStartPos);
        _rawDataBuffer.clear();
        _rawDataBuffer.addAll(remaining);
      } else if (frames.isNotEmpty) {
        // This shouldn't really happen but we don't know how the device behaves so we clear the buffer just in case.
        _rawDataBuffer.clear();
      }

      if (_rawDataBuffer.length > 65536) {
        debugPrint('Limitless: Buffer overflow, clearing buffer');
        _rawDataBuffer.clear();
      }

      // NOTE: Do NOT acknowledge based on packet index during real-time streaming!
      // TODO: Verify if acknowledgement is needed during real-time streaming.
      // if (_highestReceivedIndex > _lastAcknowledgedIndex && frames.isNotEmpty) {
      //   _lastAcknowledgedIndex = _highestReceivedIndex;
      //   acknowledgeProcessedData(_highestReceivedIndex);
      // }
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
  Future<StreamSubscription?> performGetBleButtonListener({
    required void Function(List<int>) onButtonReceived,
  }) async {
    return _buttonController.stream.listen((value) {
      if (value.isNotEmpty) {
        onButtonReceived(value);
      }
    });
  }

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
