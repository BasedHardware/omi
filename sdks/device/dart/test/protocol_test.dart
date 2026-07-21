import 'package:omi_device/omi_device.dart';
import 'package:test/test.dart';

void main() {
  test('stripPacketHeader', () {
    expect(stripPacketHeader([1, 2]), isEmpty);
    expect(stripPacketHeader([0, 0, 0, 9, 8]), [9, 8]);
    expect(audioDataUuid.isNotEmpty, isTrue);
  });
}
