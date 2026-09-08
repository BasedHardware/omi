import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/local_recordings_provider.dart';

/// A length-prefixed frame: `[4-byte LE length][payload]`.
Uint8List _frame(int len) {
  final b = BytesBuilder();
  b.add([len & 0xFF, (len >> 8) & 0xFF, (len >> 16) & 0xFF, (len >> 24) & 0xFF]);
  b.add(List<int>.filled(len, 0x41));
  return b.toBytes();
}

Future<int> _count(List<int> bytes) async {
  final dir = await Directory.systemTemp.createTemp('batchframes');
  try {
    final f = File('${dir.path}/audio.bin');
    await f.writeAsBytes(bytes);
    return await countBatchRecordingFrames(f.path);
  } finally {
    await dir.delete(recursive: true);
  }
}

void main() {
  group('countBatchRecordingFrames', () {
    test('counts complete frames', () async {
      final b = BytesBuilder();
      for (var i = 0; i < 3; i++) {
        b.add(_frame(5));
      }
      expect(await _count(b.toBytes()), 3);
    });

    test('ignores a truncated tail frame', () async {
      final b = BytesBuilder();
      b.add(_frame(5));
      b.add(_frame(5));
      // Header claims 10 payload bytes but only 3 are present (crash-recovered tail).
      b.add([10, 0, 0, 0, 0x41, 0x41, 0x41]);
      expect(await _count(b.toBytes()), 2);
    });

    test('stops at a zero-length frame', () async {
      final b = BytesBuilder();
      b.add(_frame(5));
      b.add([0, 0, 0, 0]); // len 0 -> stop
      b.add(_frame(5));
      expect(await _count(b.toBytes()), 1);
    });

    test('empty file is zero', () async {
      expect(await _count(<int>[]), 0);
    });

    test('handles frames spanning the 64KB chunk boundary', () async {
      final b = BytesBuilder();
      for (var i = 0; i < 2000; i++) {
        b.add(_frame(40)); // ~88 KB total, crosses the 64 KB read window
      }
      expect(await _count(b.toBytes()), 2000);
    });
  });
}
