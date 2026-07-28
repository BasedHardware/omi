import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/conversation_audio_assembler.dart';
import 'package:omi/services/wals/wal.dart';

void main() {
  late Directory directory;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('omi_conversation_assembler_');
  });

  tearDown(() async {
    if (await directory.exists()) {
      await directory.delete(recursive: true);
    }
  });

  test('reorders pendant ranges and inserts silence to preserve wall-clock time', () async {
    final firstFile = File('${directory.path}/first.bin');
    final secondFile = File('${directory.path}/second.bin');
    await firstFile.writeAsBytes(_frame([1, 2]), flush: true);
    await secondFile.writeAsBytes(_frame([3]), flush: true);

    final first = _wal(
      timerStart: 1000,
      sourceId: 'ring_10_11',
      filePath: firstFile.path,
      status: WalStatus.synced,
    );
    final second = _wal(
      timerStart: 1001,
      sourceId: 'ring_11_12',
      filePath: secondFile.path,
      status: WalStatus.miss,
    );
    final destination = File('${directory.path}/canonical.bin');

    final result = await assembleConversationAudio(
      parts: [
        ConversationAudioPart(wal: second, file: secondFile),
        ConversationAudioPart(wal: first, file: firstFile),
      ],
      destination: destination,
      silenceFrameFactory: (_) => [0],
    );

    expect(result.timerStart, 1000);
    expect(result.totalFrames, 101);
    expect(result.hadLiveGap, isTrue);
    expect(result.sourceWals, [first, second]);
    expect(_frames(await destination.readAsBytes()), [
      [1, 2],
      ...List.generate(99, (_) => [0]),
      [3],
    ]);
  });

  test('marks a missing pendant sequence as a repair instead of fragmenting the upload', () async {
    final firstFile = File('${directory.path}/first.bin');
    final secondFile = File('${directory.path}/second.bin');
    await firstFile.writeAsBytes(_frame([1]), flush: true);
    await secondFile.writeAsBytes(_frame([2]), flush: true);
    final destination = File('${directory.path}/canonical.bin');

    final result = await assembleConversationAudio(
      parts: [
        ConversationAudioPart(
          wal: _wal(
            timerStart: 1000,
            sourceId: 'ring_10_11',
            filePath: firstFile.path,
            status: WalStatus.synced,
          ),
          file: firstFile,
        ),
        ConversationAudioPart(
          wal: _wal(
            timerStart: 1001,
            sourceId: 'ring_12_13',
            filePath: secondFile.path,
            status: WalStatus.miss,
          ),
          file: secondFile,
        ),
      ],
      destination: destination,
      silenceFrameFactory: (_) => [0],
    );

    expect(result.hadLiveGap, isTrue);
    expect(await destination.exists(), isTrue);
    expect(await firstFile.exists(), isTrue);
    expect(await secondFile.exists(), isTrue);
  });

  test('refuses malformed source audio without publishing a partial file', () async {
    final source = File('${directory.path}/malformed.bin');
    await source.writeAsBytes([4, 0, 0, 0, 1], flush: true);
    final destination = File('${directory.path}/canonical.bin');

    await expectLater(
      assembleConversationAudio(
        parts: [
          ConversationAudioPart(
            wal: _wal(
              timerStart: 1000,
              sourceId: 'ring_10_11',
              filePath: source.path,
              status: WalStatus.miss,
            ),
            file: source,
          ),
        ],
        destination: destination,
        silenceFrameFactory: (_) => [0],
      ),
      throwsA(isA<StateError>()),
    );

    expect(await destination.exists(), isFalse);
    expect(await File('${destination.path}.partial').exists(), isFalse);
    expect(await source.exists(), isTrue);
  });
}

Wal _wal({
  required int timerStart,
  required String sourceId,
  required String filePath,
  required WalStatus status,
}) =>
    Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: 1,
      totalFrames: 1,
      status: status,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      filePath: filePath,
      device: 'cv1',
      sourceId: sourceId,
      uploadIntent: WalUploadIntent.liveContinuity,
    );

List<int> _frame(List<int> payload) {
  final prefix = ByteData(4)..setUint32(0, payload.length, Endian.little);
  return [...prefix.buffer.asUint8List(), ...payload];
}

List<List<int>> _frames(List<int> bytes) {
  final result = <List<int>>[];
  var offset = 0;
  while (offset < bytes.length) {
    final length = ByteData.sublistView(
      Uint8List.fromList(bytes),
      offset,
      offset + 4,
    ).getUint32(0, Endian.little);
    offset += 4;
    result.add(bytes.sublist(offset, offset + length));
    offset += length;
  }
  return result;
}
