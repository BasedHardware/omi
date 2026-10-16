import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/bee_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _NoIoTransport implements DeviceTransport {
  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected transport access: ${invocation.memberName}');
}

void main() {
  late BeeDeviceConnection connection;

  setUp(() {
    connection = BeeDeviceConnection(
      BtDevice(id: 'bee-test', name: 'Bee', type: DeviceType.bee, rssi: -40),
      _NoIoTransport(),
    );
  });

  List<int> voltagePayload(int millivolts, [int charging = 0]) =>
      [millivolts & 0xff, (millivolts >> 8) & 0xff, charging];

  test('captured C00F voltage reply is 76%, not 219% and charging', () {
    final packet = List<int>.unmodifiable([0x00, 0x80, 0x0f, 0xc0, 0xdb, 0x0f, 0x00]);
    final response = connection.parseResponse(packet);

    expect(response['type'], 'response');
    expect(response['code'], connection.batteryCommandCode);
    expect(connection.parseBatteryResponse(response['payload'] as List<int>), {'level': 76, 'is_charging': false});
    expect(packet, [0x00, 0x80, 0x0f, 0xc0, 0xdb, 0x0f, 0x00]);
  });

  test('legacy percentage replies preserve nonzero charging semantics', () {
    for (final level in [0, 1, 50, 100]) {
      for (final charging in [0, 1, 2, 255]) {
        expect(connection.parseBatteryResponse([level, charging]), {'level': level, 'is_charging': charging != 0});
      }
    }
  });

  test('voltage decoding is selected by format, not by low byte exceeding 100', () {
    // 4096 mV has a zero low byte, but is not an empty battery.
    expect(connection.parseBatteryResponse([0x00, 0x10, 0x00]), {'level': 80, 'is_charging': false});
  });

  test('voltage-format charging uses byte 2 and only state 1 means charging', () {
    for (final charging in [0, 1, 2, 255]) {
      expect(connection.parseBatteryResponse(voltagePayload(4059, charging)), {
        'level': 76,
        'is_charging': charging == 1,
      });
    }
  });

  test('voltage conversion follows the Bee Frontier calibration points', () {
    const points = {
      3300: 0,
      3500: 3,
      3605: 8,
      3710: 15,
      3783: 30,
      3848: 50,
      3932: 62,
      4075: 78,
      4200: 88,
      4300: 96,
      4350: 100,
    };
    for (final point in points.entries) {
      expect(connection.parseBatteryResponse(voltagePayload(point.key))?['level'], point.value,
          reason: '${point.key} mV');
    }
  });

  test('interpolates and rounds between calibration points', () {
    expect(connection.parseBatteryResponse(voltagePayload(3400))?['level'], 2);
    expect(connection.parseBatteryResponse(voltagePayload(4000))?['level'], 70);
  });

  test('clamps only calibrated voltage estimates at the curve endpoints', () {
    for (final millivolts in [2500, 3299]) {
      expect(connection.parseBatteryResponse(voltagePayload(millivolts))?['level'], 0);
    }
    for (final millivolts in [4351, 5000]) {
      expect(connection.parseBatteryResponse(voltagePayload(millivolts))?['level'], 100);
    }
  });

  test('rejects unsupported lengths and implausible voltages', () {
    for (final payload in <List<int>>[
      [],
      [0xdb],
      [0xdb, 0x0f, 0, 0],
      voltagePayload(0),
      voltagePayload(2499),
      voltagePayload(5001),
      voltagePayload(65535),
    ]) {
      expect(connection.parseBatteryResponse(payload), isNull, reason: '$payload');
    }
  });

  test('voltage estimates stay bounded and monotonic across the accepted range', () {
    var previous = 0;
    for (var millivolts = 2500; millivolts <= 5000; millivolts++) {
      final level = connection.parseBatteryResponse(voltagePayload(millivolts))!['level'] as int;
      expect(level, inInclusiveRange(previous, 100), reason: '$millivolts mV');
      previous = level;
    }
  });
}
