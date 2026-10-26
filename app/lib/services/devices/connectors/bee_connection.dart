import 'dart:async';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/custom_connection.dart';
import 'package:omi/services/devices/models.dart';

const int beeCmdGetFirmwareVersion = 0xC005;

class BeeDeviceConnection extends CustomDeviceConnection {
  final _audioBuffer = <int>[];
  String? _cachedFirmwareVersion;

  BeeDeviceConnection(super.device, super.transport);

  @override
  String get serviceUuid => beeServiceUuid;

  @override
  String get controlCharacteristicUuid => "05e1f93c-d8d0-5ed8-dd88-379e4c1a3e3e";

  @override
  String get audioCharacteristicUuid => beeAudioCharacteristicUuid;

  @override
  int get unmuteCommandCode => 0xC006;

  @override
  int get muteCommandCode => 0xC006;

  @override
  int get batteryCommandCode => 0xC00F;

  @override
  List<int> get unmuteCommandData => [0x01];

  @override
  List<int> get muteCommandData => [0x00];

  @override
  BleAudioCodec get audioCodec => BleAudioCodec.aac;

  @override
  Map<String, dynamic> parseResponse(List<int> data) {
    if (data.length < 2) return {'type': 'unknown', 'data': data};

    final responseCode = data[0] | (data[1] << 8);
    final payload = data.length > 2 ? data.sublist(2) : <int>[];

    if (responseCode == 0x8000 && payload.length >= 2) {
      final echoedCmd = payload[0] | (payload[1] << 8);
      final actualPayload = payload.length > 2 ? payload.sublist(2) : <int>[];
      return {'type': 'response', 'code': echoedCmd, 'payload': actualPayload};
    }

    if (payload.isEmpty) {
      return {'type': 'echo', 'code': responseCode, 'payload': payload};
    }

    return {'type': 'response', 'code': responseCode, 'payload': payload};
  }

  @override
  List<int>? processAudioPacket(List<int> data) {
    if (data.length < 2) return null;
    _audioBuffer.addAll(data.sublist(2));

    while (_audioBuffer.length >= 7) {
      if (_audioBuffer[0] != 0xFF || (_audioBuffer[1] & 0xF0) != 0xF0) {
        _audioBuffer.removeAt(0);
        continue;
      }

      final frameLength = ((_audioBuffer[3] & 0x03) << 11) | (_audioBuffer[4] << 3) | ((_audioBuffer[5] & 0xE0) >> 5);

      if (_audioBuffer.length >= frameLength) {
        final frame = _audioBuffer.sublist(0, frameLength);
        _audioBuffer.removeRange(0, frameLength);
        return frame;
      }
      break;
    }
    return null;
  }

  static const List<List<int>> _dischargeStates = [
    [4200, 100],
    [4100, 85],
    [4000, 65],
    [3900, 50],
    [3800, 35],
    [3700, 15],
    [3600, 5],
    [3500, 1],
    [3400, 0],
  ];

  static const List<List<int>> _chargingStates = [
    [4250, 100],
    [4180, 85],
    [4080, 65],
    [3980, 50],
    [3880, 35],
    [3780, 15],
    [3680, 5],
    [3580, 1],
    [3480, 0],
  ];

  /// Interpolates battery percentage from millivolts using the Bee LiPo calibration curve.
  static int millivoltsToPercentage(int millivolts, bool isCharging) {
    final states = isCharging ? _chargingStates : _dischargeStates;
    if (millivolts >= states.first[0]) {
      return states.first[1];
    }
    if (millivolts <= states.last[0]) {
      return states.last[1];
    }

    for (int i = 0; i < states.length - 1; i++) {
      final high = states[i];
      final low = states[i + 1];
      if (millivolts <= high[0] && millivolts >= low[0]) {
        final vRange = high[0] - low[0];
        if (vRange == 0) return high[1];
        final pRange = high[1] - low[1];
        final vDiff = high[0] - millivolts;
        final pct = high[1] - ((vDiff * pRange) / vRange).round();
        return pct.clamp(0, 100);
      }
    }
    return 0;
  }

  @override
  Map<String, dynamic>? parseBatteryResponse(List<int> payload) {
    if (payload.length < 2) return null;

    if (payload.length == 2) {
      // Legacy 2-byte format: [percentage, charging]
      return {
        'level': payload[0].clamp(0, 100),
        'is_charging': payload[1] != 0,
      };
    }

    // 3-byte voltage format: [mv_low, mv_high, charging_state]
    final millivolts = payload[0] | (payload[1] << 8);

    // Reject implausible voltage readings (< 3.0V or > 4.5V)
    if (millivolts < 3000 || millivolts > 4500) {
      return null;
    }

    final isCharging = payload[2] != 0;
    final level = millivoltsToPercentage(millivolts, isCharging);

    return {
      'level': level,
      'is_charging': isCharging,
    };
  }

  @override
  Future<void> connect({Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
    await _queryFirmwareVersion();
    if (_cachedFirmwareVersion != null) {
      device = device.copyWith(firmwareRevision: _cachedFirmwareVersion);
    }
  }

  Future<void> _queryFirmwareVersion() async {
    try {
      final response = await sendFirmwareCommand();
      if (response != null && response.length >= 3) {
        final patch = response[0];
        final minor = response[1];
        final major = response[2];
        _cachedFirmwareVersion = '$major.$minor.$patch';
      }
    } catch (_) {
      // Ignore errors during firmware query
    }
  }

  Future<List<int>?> sendFirmwareCommand() async {
    final completer = Completer<List<int>>();
    late final StreamSubscription sub;

    sub = transport.getCharacteristicStream(serviceUuid, controlCharacteristicUuid).listen((data) {
      final response = parseResponse(data);
      if (response['type'] == 'response' && response['code'] == beeCmdGetFirmwareVersion) {
        if (!completer.isCompleted) {
          completer.complete(response['payload'] as List<int>);
        }
      }
    });

    try {
      final command = encodeCommand(beeCmdGetFirmwareVersion, []);
      await transport.writeCharacteristic(serviceUuid, controlCharacteristicUuid, command);
      return await completer.future.timeout(const Duration(seconds: 5));
    } on TimeoutException {
      return null;
    } finally {
      await sub.cancel();
    }
  }

  Future<Map<String, String>> getDeviceInfo() async {
    return {
      'modelNumber': 'Bee',
      'firmwareRevision': _cachedFirmwareVersion ?? '0.6.0',
      'hardwareRevision': '1.0.0',
      'manufacturerName': 'Bee',
    };
  }
}
