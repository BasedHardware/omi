import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/local_recording_group.dart';

const watchA = '0123456789abcdef0123456789abcdef';
const watchB = '1123456789abcdef0123456789abcdef';

LocalRecording watchPart(String session, int index, DateTime start) {
  final seconds = start.millisecondsSinceEpoch ~/ 1000;
  final name = 'audio_omibatchwatch${session}s${index}_pcm16_16000_1_fs160_$seconds.bin';
  return LocalRecording(
    fileName: name,
    filePath: '/tmp/$name',
    timerStart: seconds,
    codec: BleAudioCodec.pcm16,
    frameSize: 160,
    sizeBytes: 1024,
    seconds: 60,
    state: LocalRecordingState.pending,
  );
}

void main() {
  test('666 recovery files remain one Watch session and retain every original part', () {
    final start = DateTime.utc(2026, 10, 20, 23, 50);
    final parts = List.generate(666, (i) => watchPart(watchA, i, start.add(Duration(minutes: i))));
    final groups = groupLocalRecordings(parts.reversed.toList());
    expect(groups, hasLength(1));
    expect(groups.single.startedAt.toUtc(), start);
    expect(groups.single.seconds, 666 * 60);
    expect(groups.single.recordings, orderedEquals(parts));
    expect(groups.single.isWatchRecovery, isTrue);
    expect(() => groups.single.recordings.clear(), throwsUnsupportedError);
  });

  test('out-of-order and missing segments retain one identity across scans and midnight', () {
    final start = DateTime.utc(2026, 10, 20, 23, 59);
    final first = watchPart(watchA, 0, start);
    final later = watchPart(watchA, 2, start.add(const Duration(minutes: 2)));
    final initial = groupLocalRecordings([later]).single;
    final complete = groupLocalRecordings([later, first]).single;
    expect(complete.id, initial.id);
    expect(complete.startedAt.toUtc(), start);
    expect(complete.recordings, [first, later]);
    expect(complete.seconds, 120, reason: 'missing audio must not be counted as saved');
  });

  test('separate Watch sessions and ordinary phone recordings never join', () {
    final start = DateTime.utc(2026, 10, 21);
    final watch = watchPart(watchA, 0, start);
    final other = watchPart(watchB, 0, start);
    final phone = LocalRecording(
      fileName: 'audio_omibatchphone_pcm16_16000_1_fs160_1792540800.bin',
      filePath: '/tmp/phone.bin',
      timerStart: watch.timerStart,
      codec: BleAudioCodec.pcm16,
      frameSize: 160,
      sizeBytes: 100,
      seconds: 40,
      state: LocalRecordingState.pending,
    );
    final groups = groupLocalRecordings([watch, other, phone]);
    expect(groups, hasLength(3));
    expect(groups.where((g) => !g.isWatchRecovery).single.recordings, [phone]);
  });

  test('malformed Watch markers do not group as a Watch session', () {
    expect(watchRecordingSessionId('audio_omibatchwatch${watchA}s0_opus_16000_1_fs160_1.bin'), isNull);
    expect(watchRecordingSessionId('audio_omibatchwatchshorts0_pcm16_16000_1_fs160_1.bin'), isNull);
    expect(watchRecordingSessionId('audio_omibatchwatch${watchA}s0_pcm16_16000_1_fs160_1.bin.extra'), isNull);
    expect(groupLocalRecordings([]), isEmpty);
  });
}
