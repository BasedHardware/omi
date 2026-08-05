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
      captureEndSeconds: 1000.25,
    );
    final second = _wal(
      timerStart: 1001,
      sourceId: 'ring_11_12',
      filePath: secondFile.path,
      status: WalStatus.miss,
      captureEndSeconds: 1001.75,
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
    expect(result.captureEndSeconds, 1001.75);
    expect(result.hadLiveGap, isTrue);
    expect(result.sourceWals, [first, second]);
    expect(_frames(await destination.readAsBytes()), [
      [1, 2],
      ...List.generate(99, (_) => [0]),
      [3],
    ]);
  });

  test('never turns two contiguous one-second ranges into a 17-minute recording', () async {
    final firstFile = File('${directory.path}/first.bin');
    final secondFile = File('${directory.path}/second.bin');
    await firstFile.writeAsBytes(_frame([1]), flush: true);
    await secondFile.writeAsBytes(_frame([2]), flush: true);
    final destination = File('${directory.path}/canonical.bin');

    await expectLater(
      assembleConversationAudio(
        parts: [
          ConversationAudioPart(
            wal: _wal(
              timerStart: 1000,
              sourceId: 'ring_10_11',
              filePath: firstFile.path,
              status: WalStatus.synced,
              captureEndSeconds: 1001,
            ),
            file: firstFile,
          ),
          ConversationAudioPart(
            wal: _wal(
              timerStart: 2020,
              sourceId: 'ring_11_12',
              filePath: secondFile.path,
              status: WalStatus.miss,
              captureEndSeconds: 2021,
            ),
            file: secondFile,
          ),
        ],
        destination: destination,
        silenceFrameFactory: (_) => [0],
        conversationBoundarySeconds: 120,
      ),
      throwsA(
        isA<StateError>().having(
          (error) => error.message,
          'message',
          contains('conversation boundary'),
        ),
      ),
    );
    expect(await destination.exists(), isFalse);
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

  test('removes a replay overlap when the original ranges preserve the complete sequence', () async {
    final firstFile = File('${directory.path}/first.bin');
    final replayFile = File('${directory.path}/replay.bin');
    final secondFile = File('${directory.path}/second.bin');
    await firstFile.writeAsBytes(_frame([1]), flush: true);
    await replayFile.writeAsBytes(_frame([9]), flush: true);
    await secondFile.writeAsBytes(_frame([2]), flush: true);
    final first = _wal(
      timerStart: 1000,
      sourceId: 'ring_10_20',
      filePath: firstFile.path,
      status: WalStatus.synced,
    );
    final replay = _wal(
      timerStart: 1000,
      sourceId: 'ring_15_25',
      filePath: replayFile.path,
      status: WalStatus.miss,
    );
    final second = _wal(
      timerStart: 1000,
      sourceId: 'ring_20_30',
      filePath: secondFile.path,
      status: WalStatus.synced,
    );
    final destination = File('${directory.path}/canonical.bin');

    final result = await assembleConversationAudio(
      parts: [
        ConversationAudioPart(wal: replay, file: replayFile),
        ConversationAudioPart(wal: second, file: secondFile),
        ConversationAudioPart(wal: first, file: firstFile),
      ],
      destination: destination,
      silenceFrameFactory: (_) => [0],
    );

    expect(_frames(await destination.readAsBytes()), [
      [1],
      [2],
    ]);
    expect(result.totalFrames, 2);
    expect(result.hadLiveGap, isTrue);
    expect(result.sourceWals, [first, replay, second]);
  });

  test('finds a lossless exact tiling instead of greedily removing its required range', () async {
    final firstFile = File('${directory.path}/first.bin');
    final firstGapFile = File('${directory.path}/first_gap.bin');
    final secondGapFile = File('${directory.path}/second_gap.bin');
    final secondFile = File('${directory.path}/second.bin');
    await firstFile.writeAsBytes(_frame([1]), flush: true);
    await firstGapFile.writeAsBytes(_frame([9]), flush: true);
    await secondGapFile.writeAsBytes(_frame([8]), flush: true);
    await secondFile.writeAsBytes(_frame([2]), flush: true);
    final first = _wal(
      timerStart: 1000,
      sourceId: 'ring_10_20',
      filePath: firstFile.path,
      status: WalStatus.synced,
    );
    final firstGap = _wal(
      timerStart: 1000,
      sourceId: 'ring_10_15',
      filePath: firstGapFile.path,
      status: WalStatus.miss,
    );
    final secondGap = _wal(
      timerStart: 1000,
      sourceId: 'ring_15_21',
      filePath: secondGapFile.path,
      status: WalStatus.miss,
    );
    final second = _wal(
      timerStart: 1000,
      sourceId: 'ring_20_30',
      filePath: secondFile.path,
      status: WalStatus.synced,
    );
    final destination = File('${directory.path}/canonical.bin');

    final result = await assembleConversationAudio(
      parts: [
        ConversationAudioPart(wal: secondGap, file: secondGapFile),
        ConversationAudioPart(wal: second, file: secondFile),
        ConversationAudioPart(wal: first, file: firstFile),
        ConversationAudioPart(wal: firstGap, file: firstGapFile),
      ],
      destination: destination,
      silenceFrameFactory: (_) => [0],
    );

    expect(_frames(await destination.readAsBytes()), [
      [1],
      [2],
    ]);
    expect(result.totalFrames, 2);
    expect(result.hadLiveGap, isTrue);
    expect(result.sourceWals, [firstGap, first, secondGap, second]);
  });

  test('prefers fewer exact parts before preferring synced sources', () async {
    final wholeFile = File('${directory.path}/whole.bin');
    final firstFile = File('${directory.path}/first.bin');
    final secondFile = File('${directory.path}/second.bin');
    await wholeFile.writeAsBytes(_frame([1]), flush: true);
    await firstFile.writeAsBytes(_frame([2]), flush: true);
    await secondFile.writeAsBytes(_frame([3]), flush: true);
    final destination = File('${directory.path}/canonical.bin');

    await assembleConversationAudio(
      parts: [
        ConversationAudioPart(
          wal: _wal(
            timerStart: 1000,
            sourceId: 'ring_10_30',
            filePath: wholeFile.path,
            status: WalStatus.miss,
          ),
          file: wholeFile,
        ),
        ConversationAudioPart(
          wal: _wal(
            timerStart: 1000,
            sourceId: 'ring_10_20',
            filePath: firstFile.path,
            status: WalStatus.synced,
          ),
          file: firstFile,
        ),
        ConversationAudioPart(
          wal: _wal(
            timerStart: 1000,
            sourceId: 'ring_20_30',
            filePath: secondFile.path,
            status: WalStatus.synced,
          ),
          file: secondFile,
        ),
      ],
      destination: destination,
      silenceFrameFactory: (_) => [0],
    );

    expect(_frames(await destination.readAsBytes()), [
      [1],
    ]);
  });

  test('prefers synced sources between equal-size exact tilings', () async {
    final syncedFirstFile = File('${directory.path}/synced_first.bin');
    final syncedSecondFile = File('${directory.path}/synced_second.bin');
    final missedFirstFile = File('${directory.path}/missed_first.bin');
    final missedSecondFile = File('${directory.path}/missed_second.bin');
    await syncedFirstFile.writeAsBytes(_frame([1]), flush: true);
    await syncedSecondFile.writeAsBytes(_frame([2]), flush: true);
    await missedFirstFile.writeAsBytes(_frame([9]), flush: true);
    await missedSecondFile.writeAsBytes(_frame([8]), flush: true);
    final destination = File('${directory.path}/canonical.bin');

    await assembleConversationAudio(
      parts: [
        ConversationAudioPart(
          wal: _wal(
            timerStart: 1000,
            sourceId: 'ring_10_20',
            filePath: syncedFirstFile.path,
            status: WalStatus.synced,
          ),
          file: syncedFirstFile,
        ),
        ConversationAudioPart(
          wal: _wal(
            timerStart: 1000,
            sourceId: 'ring_20_30',
            filePath: syncedSecondFile.path,
            status: WalStatus.synced,
          ),
          file: syncedSecondFile,
        ),
        ConversationAudioPart(
          wal: _wal(
            timerStart: 1000,
            sourceId: 'ring_10_15',
            filePath: missedFirstFile.path,
            status: WalStatus.miss,
          ),
          file: missedFirstFile,
        ),
        ConversationAudioPart(
          wal: _wal(
            timerStart: 1000,
            sourceId: 'ring_15_30',
            filePath: missedSecondFile.path,
            status: WalStatus.miss,
          ),
          file: missedSecondFile,
        ),
      ],
      destination: destination,
      silenceFrameFactory: (_) => [0],
    );

    expect(_frames(await destination.readAsBytes()), [
      [1],
      [2],
    ]);
  });

  test('breaks equal-cost tiling ties by the earliest sequence part', () async {
    Future<ConversationAudioPart> part(
      String name,
      String sourceId,
      int payload,
    ) async {
      final file = File('${directory.path}/$name.bin');
      await file.writeAsBytes(_frame([payload]), flush: true);
      return ConversationAudioPart(
        wal: _wal(
          timerStart: 1000,
          sourceId: sourceId,
          filePath: file.path,
          status: WalStatus.synced,
        ),
        file: file,
      );
    }

    final earlierPath = [
      await part('earlier_1', 'ring_10_20', 1),
      await part('earlier_2', 'ring_20_40', 2),
      await part('earlier_3', 'ring_40_60', 3),
    ];
    final laterPath = [
      await part('later_1', 'ring_10_30', 9),
      await part('later_2', 'ring_30_35', 8),
      await part('later_3', 'ring_35_60', 7),
    ];
    final destination = File('${directory.path}/canonical.bin');

    await assembleConversationAudio(
      parts: [...laterPath, ...earlierPath],
      destination: destination,
      silenceFrameFactory: (_) => [0],
    );

    expect(_frames(await destination.readAsBytes()), [
      [1],
      [2],
      [3],
    ]);
  });

  test('tiles ten thousand fragments without retaining every path prefix', () async {
    const fragmentCount = 10000;
    final source = File('${directory.path}/shared.bin');
    final encodedFrame = _frame([7]);
    await source.writeAsBytes(encodedFrame, flush: true);
    final destination = File('${directory.path}/canonical.bin');
    final parts = List.generate(
      fragmentCount,
      (index) => ConversationAudioPart(
        wal: _wal(
          timerStart: 1000,
          sourceId: 'ring_${index + 10}_${index + 11}',
          filePath: source.path,
          status: WalStatus.synced,
        ),
        file: source,
      ),
    );

    final result = await assembleConversationAudio(
      parts: parts,
      destination: destination,
      silenceFrameFactory: (_) => [0],
    );

    expect(result.totalFrames, fragmentCount);
    expect(result.sourceWals, hasLength(fragmentCount));
    expect(await destination.length(), encodedFrame.length * fragmentCount);
  }, timeout: const Timeout(Duration(seconds: 30)));

  test('refuses an overlap that cannot be removed without losing a sequence', () async {
    final firstFile = File('${directory.path}/first.bin');
    final secondFile = File('${directory.path}/second.bin');
    await firstFile.writeAsBytes(_frame([1]), flush: true);
    await secondFile.writeAsBytes(_frame([2]), flush: true);
    final destination = File('${directory.path}/canonical.bin');

    await expectLater(
      assembleConversationAudio(
        parts: [
          ConversationAudioPart(
            wal: _wal(
              timerStart: 1000,
              sourceId: 'ring_10_20',
              filePath: firstFile.path,
              status: WalStatus.miss,
            ),
            file: firstFile,
          ),
          ConversationAudioPart(
            wal: _wal(
              timerStart: 1000,
              sourceId: 'ring_15_25',
              filePath: secondFile.path,
              status: WalStatus.miss,
            ),
            file: secondFile,
          ),
        ],
        destination: destination,
        silenceFrameFactory: (_) => [0],
      ),
      throwsA(
        isA<StateError>().having(
          (error) => error.message,
          'message',
          contains('irreducible overlapping pendant sequence'),
        ),
      ),
    );

    expect(await destination.exists(), isFalse);
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
  double? captureEndSeconds,
}) =>
    Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: 1,
      captureEndSeconds: captureEndSeconds,
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
