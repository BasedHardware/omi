import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/wal_frame_encoder.dart';

void main() {
  test('WAL golden preserves empty frames, byte order, payloads and boundaries', () {
    expect(
        encodeWalFrames([
          [],
          [1, 2, 255],
          [0]
        ]),
        [0, 0, 0, 0, 3, 0, 0, 0, 1, 2, 255, 1, 0, 0, 0, 0]);
    expect(encodeWalFrames([]), isEmpty);
    final large = Uint8List.fromList(List.generate(513, (i) => i & 255));
    final encoded = encodeWalFrames([
      large,
      [7, 8]
    ]);
    expect(encoded.sublist(0, 4), [1, 2, 0, 0]);
    expect(encoded.sublist(4, 517), large);
    expect(encoded.sublist(517), [2, 0, 0, 0, 7, 8]);
    large.fillRange(0, large.length, 0);
    expect(encoded[5], 1, reason: 'the completed WAL owns its bytes');
  });

  test('a ten-second pendant chunk round trips through the existing length-prefixed reader', () {
    final frames = List.generate(1000, (i) => List.generate(80, (j) => (i + j) & 255));
    final encoded = encodeWalFrames(frames);
    final lengths = ByteData.sublistView(encoded);
    var offset = 0;
    final decoded = <List<int>>[];
    while (offset < encoded.length) {
      final length = lengths.getUint32(offset, Endian.little);
      offset += 4;
      decoded.add(encoded.sublist(offset, offset + length));
      offset += length;
    }
    expect(decoded, frames);
    expect(encoded.length, 84000);
  });
}
