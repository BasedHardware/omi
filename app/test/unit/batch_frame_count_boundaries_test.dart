import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/local_recordings_provider.dart';

void main() {
  late Directory directory;
  late File file;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('batch-count-boundaries-');
    file = File('${directory.path}/recording.bin');
  });

  tearDown(() async => directory.delete(recursive: true));

  test('a header spanning the read boundary still counts its full payload', () async {
    final bytes = Uint8List(65536 + 9);
    // First frame ends three bytes before the 64 KB boundary, splitting the
    // next header across reads. Then one complete 8-byte frame follows.
    ByteData.sublistView(bytes).setUint32(0, 65529, Endian.little);
    ByteData.sublistView(bytes).setUint32(65533, 8, Endian.little);
    await file.writeAsBytes(bytes);
    expect(await countBatchRecordingFrames(file.path), 2);
  });

  test('a partial header and an unsigned oversized payload are not counted', () async {
    await file.writeAsBytes([1, 0, 0, 0, 42, 1, 0]);
    expect(await countBatchRecordingFrames(file.path), 1);
    await file.writeAsBytes([1, 0, 0, 0, 42, 255, 255, 255, 255, 42]);
    expect(await countBatchRecordingFrames(file.path), 1);
  });

  test('worker read failures propagate to the duration estimate fallback', () async {
    expect(countBatchRecordingFrames(file.path), throwsA(isA<FileSystemException>()));
  });
}
