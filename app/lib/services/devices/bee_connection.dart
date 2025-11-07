import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/custom_connection.dart';
import 'package:omi/services/devices/models.dart';

class BeeDeviceConnection extends CustomDeviceConnection {
  final _audioBuffer = <int>[];

  BeeDeviceConnection(super.device, super.transport);

  @override
  String get serviceUuid => beeServiceUuid;

  @override
  String get controlCharacteristicUuid => "05e1f93c-d8d0-5ed8-dd88-379e4c1a3e3e";

  @override
  String get audioCharacteristicUuid => "b189a505-a86c-11ee-a5fb-8f2089a49e7e";

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

  @override
  Map<String, dynamic>? parseBatteryResponse(List<int> payload) {
    if (payload.length < 2) return null;
    return {'level': payload[0], 'is_charging': payload[1] != 0};
  }

  Future<Map<String, String>> getDeviceInfo() async {
    return {
      'modelNumber': 'Bee',
      'firmwareRevision': '1.0.0',
      'hardwareRevision': '1.0.0',
      'manufacturerName': 'Bee',
    };
  }
}
