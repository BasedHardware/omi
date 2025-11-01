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
