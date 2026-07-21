import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device/omi_device.dart';

void main() {
  test('factory returns FlutterBluePlusOmiBle', () {
    final client = createOmiBleClient();
    expect(client, isA<FlutterBluePlusOmiBle>());
  });

  test('payload strip matches app decoder framing', () {
    final raw = [
      [1, 2, 3, 9, 8],
      [1, 2],
      [0, 0, 0, 7],
    ];
    final payloads = raw
        .map(stripPacketHeader)
        .where((p) => p.isNotEmpty)
        .toList();
    expect(payloads, [
      [9, 8],
      [7],
    ]);
  });
}
