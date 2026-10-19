import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device/omi_device.dart';

void main() {
  test('whisper stop delivers a batch still being transcribed before the buffered tail', () async {
    final events = <String>[];
    final batchLengths = <int>[];
    final firstBatch = Completer<String>();
    FutureOr<String> runner(Uint8List pcm) {
      batchLengths.add(pcm.length);
      if (batchLengths.length == 1) return firstBatch.future;
      return 'tail';
    }

    final transcriber = WhisperTranscriber(runner: runner, onTranscript: events.add, batchSeconds: 1);

    // One second of 16 kHz PCM16 fills a batch; the runner is still transcribing it when stop() is called.
    transcriber.appendPcm(Uint8List(32000));
    await Future<void>.delayed(Duration.zero);
    transcriber.appendPcm(Uint8List.fromList([1, 0]));
    final stopping = transcriber.stop().then((_) => events.add('stopped'));
    firstBatch.complete('first');
    await stopping;

    expect(batchLengths, [32000, 2]);
    expect(events, ['first', 'tail', 'stopped']);
  });

  test('whisper stop at a batch boundary still delivers the batch being transcribed', () async {
    final events = <String>[];
    final batch = Completer<String>();
    final transcriber = WhisperTranscriber(runner: (_) => batch.future, onTranscript: events.add, batchSeconds: 1);

    transcriber.appendPcm(Uint8List(32000));
    await Future<void>.delayed(Duration.zero);
    final stopping = transcriber.stop().then((_) => events.add('stopped'));
    batch.complete('full batch');
    await stopping;

    expect(events, ['full batch', 'stopped']);
  });
}
