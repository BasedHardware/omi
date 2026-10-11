import 'dart:io';
import 'dart:typed_data';

import 'package:omi/services/wals/wal_frame_encoder.dart';

// Run with the pinned Dart SDK: dart run tool/benchmark_wal_frame_encoding.dart.
// Host CPU microbenchmark, not a phone energy measurement. The reference is
// the pre-change LocalWalSyncImpl._flush serializer from 3c672ba046.
List<int> legacy(List<List<int>> frames) {
  final data = <int>[];
  for (final frame in frames) {
    final bytes = ByteData(frame.length);
    for (var j = 0; j < frame.length; j++) {
      bytes.setUint8(j, frame[j]);
    }
    data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
    data.addAll(bytes.buffer.asUint8List());
  }
  return data;
}

void main() {
  final frames = List.generate(1000, (i) => List.generate(80, (j) => (i + j) & 255));
  final reference = legacy(frames);
  final encoded = encodeWalFrames(frames);
  if (reference.length != encoded.length) throw StateError('length differs');
  for (var i = 0; i < encoded.length; i++) {
    if (reference[i] != encoded[i]) throw StateError('byte $i differs');
  }
  var checksum = 0;
  int measure(List<int> Function(List<List<int>>) encode) {
    for (var i = 0; i < 100; i++) {
      checksum += encode(frames).last;
    }
    final clock = Stopwatch()..start();
    for (var i = 0; i < 1000; i++) {
      checksum += encode(frames).last;
    }
    return clock.elapsedMicroseconds;
  }

  for (var round = 0; round < 5; round++) {
    // Alternate order so JIT/GC warmup is not always assigned to one side.
    final int oldMicros;
    final int newMicros;
    if (round.isEven) {
      oldMicros = measure(legacy);
      newMicros = measure(encodeWalFrames);
    } else {
      newMicros = measure(encodeWalFrames);
      oldMicros = measure(legacy);
    }
    stdout.writeln('WAL_BENCHMARK round=$round chunks=1000 frames_per_chunk=1000 bytes_per_frame=80 '
        'legacy_us=$oldMicros encoded_us=$newMicros output_bytes=${encoded.length}');
  }
  stdout.writeln('checksum=$checksum byte_equivalence=PASS');
}
