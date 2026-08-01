import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device/omi_device.dart';

void main() {
  test('stripPacketHeader', () {
    expect(stripPacketHeader([1, 2]), isEmpty);
    expect(stripPacketHeader([0, 0, 0, 9, 8]), [9, 8]);
  });

  test('app UUID parity', () {
    expect(omiServiceUuid, '19b10000-e8f2-537e-4f6c-d104768a1214');
    expect(audioDataUuid, audioDataStreamCharacteristicUuid);
    expect(audioCodecUuid, '19b10002-e8f2-537e-4f6c-d104768a1214');
    expect(batteryServiceUuid, '0000180f-0000-1000-8000-00805f9b34fb');
  });
}
