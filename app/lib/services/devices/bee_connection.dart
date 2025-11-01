import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/custom_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

/// Bee device connection implementing the Bee protocol
/// Based on Python reference implementation in x/skill.py and x/skill_battery.py
class BeeDeviceConnection extends CustomDeviceConnection {
  // ═══════════════════════════════════════════════════════════════
  //                    Bee Protocol Constants
  // ═══════════════════════════════════════════════════════════════

  // Command codes
  static const int _cmdSetDeviceState = 0xC006; // Unmute/Mute
  static const int _cmdGetBattery = 0xC00F; // Get battery

  // Response codes
  static const int _respWrapper = 0x8000; // Response wrapper
  static const int _eventCharging = 0x8002; // Charging event

  // Audio buffering for ADTS frame detection
  final List<int> _audioBuffer = [];
  int _frameCount = 0;

  BeeDeviceConnection(super.device, super.transport);

  // ═══════════════════════════════════════════════════════════════
  //                    Configuration Overrides
  // ═══════════════════════════════════════════════════════════════

  @override
  String get serviceUuid => beeServiceUuid;

  @override
  String get controlCharacteristicUuid => beeControlCharUuid;

  @override
  String get audioCharacteristicUuid => beeAudioCharUuid;

  @override
  BleAudioCodec get audioCodec => BleAudioCodec.aac;

  @override
  int get commandUnmute => _cmdSetDeviceState;

  @override
  int get commandMute => _cmdSetDeviceState;

  @override
  int get commandGetBattery => _cmdGetBattery;

  // ═══════════════════════════════════════════════════════════════
  //                    Protocol Implementation
  // ═══════════════════════════════════════════════════════════════

  @override
  List<int> encodeCommand(int commandCode, List<int> data) {
    // Little-endian encoding: struct.pack('<H', command_code) + data
    return [
      commandCode & 0xFF,
      (commandCode >> 8) & 0xFF,
      ...data,
    ];
  }

  @override
  Map<String, dynamic> parseResponse(List<int> data) {
    if (data.length < 2) {
      return {'type': 'unknown', 'data': data};
    }

    // Parse response code (little-endian)
    final responseCode = data[0] | (data[1] << 8);
    final payload = data.length > 2 ? data.sublist(2) : <int>[];

    // Handle wrapped responses (0x8000 format)
    // Format: 0x8000 + <echoed_cmd (2 bytes)> + <actual_payload>
    if (responseCode == _respWrapper && payload.length >= 2) {
      final echoedCmd = payload[0] | (payload[1] << 8);
      final actualPayload = payload.length > 2 ? payload.sublist(2) : <int>[];

      return {
        'type': 'response',
        'code': echoedCmd,
        'payload': actualPayload,
      };
    }

    // Handle charging event
    if (responseCode == _eventCharging) {
      return {
        'type': 'event',
        'code': responseCode,
        'payload': payload,
      };
    }

    // Default response
    return {
      'type': 'response',
      'code': responseCode,
      'payload': payload,
    };
  }

  @override
  List<int>? stripAudioHeader(List<int> data) {
    // Strip first 2 bytes from audio packets
    if (data.length < 2) return null;
    return data.sublist(2);
  }

  @override
  Map<String, dynamic>? parseBatteryResponse(List<int> payload) {
    // Battery response format: [level, is_charging]
    if (payload.length < 2) return null;

    return {
      'level': payload[0], // 0-100
      'is_charging': payload[1] != 0, // 0=not charging, non-zero=charging
    };
  }

  // ═══════════════════════════════════════════════════════════════
  //                    Audio Processing Override
  // ═══════════════════════════════════════════════════════════════

  @override
  void processAudioData(List<int> payload) {
    // Add payload to buffer
    _audioBuffer.addAll(payload);

    // Process all complete ADTS frames in buffer
    while (_audioBuffer.isNotEmpty) {
      final frameSize = _detectAdtsFrame(_audioBuffer, 0);

      if (frameSize == null) {
        // No valid ADTS header found
        if (_audioBuffer.length > 7) {
          // Discard first byte and try again
          _audioBuffer.removeAt(0);
        } else {
          // Not enough data yet
          break;
        }
      } else if (_audioBuffer.length >= frameSize) {
        // Complete frame available
        final frame = _audioBuffer.sublist(0, frameSize);
        _audioBuffer.removeRange(0, frameSize);

        _frameCount++;

        // Send complete ADTS frame to stream
        // Note: We access the parent's stream through the public getter if available
        // or we need to call a method. Since _audioStream is private, we'll work around it.
        // Actually, we can call super.processAudioData with the frame
        super.processAudioData(frame);

        if (_frameCount % 10 == 0) {
          debugPrint('[BeeDevice] Sent $_frameCount complete AAC frames');
        }
      } else {
        // Not enough data for complete frame yet
        break;
      }
    }
  }

  /// Detect ADTS frame header and return frame size
  /// Returns null if no valid ADTS header found at offset
  int? _detectAdtsFrame(List<int> data, int offset) {
    if (data.length - offset < 7) {
      return null;
    }

    // Check for ADTS sync word (12 bits set to 1: 0xFFF)
    if (data[offset] != 0xFF || (data[offset + 1] & 0xF0) != 0xF0) {
      return null;
    }

    // Extract frame length (13 bits starting at bit 30)
    // Byte layout: ...LLLLLLLL LLLXXXXX
    final frameLength = ((data[offset + 3] & 0x03) << 11) | (data[offset + 4] << 3) | ((data[offset + 5] & 0xE0) >> 5);

    return frameLength;
  }

  // ═══════════════════════════════════════════════════════════════
  //                    Device Information
  // ═══════════════════════════════════════════════════════════════

  Future<Map<String, String>> getDeviceInfo() async {
    return {
      'modelNumber': 'Bee',
      'firmwareRevision': '1.0.0',
      'hardwareRevision': '1.0.0',
      'manufacturerName': 'Bee',
    };
  }
}
