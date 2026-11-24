import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device/omi_device.dart';

void main() {
  test('whisper stop drains in-flight and queued batches before the buffered tail', () async {
    final events = <String>[];
    final batchLengths = <int>[];
    final batchStarts = <int>[];
    final firstBatch = Completer<String>();
    final secondBatch = Completer<String>();
    FutureOr<String> runner(Uint8List pcm) {
      batchLengths.add(pcm.length);
      batchStarts.add(pcm.first);
      if (batchLengths.length == 1) return firstBatch.future;
      if (batchLengths.length == 2) return secondBatch.future;
      return 'tail';
    }

    final transcriber = WhisperTranscriber(runner: runner, onTranscript: events.add, batchSeconds: 1);

    // One second of 16 kHz PCM16 fills a batch; the runner is still transcribing it when stop() is called.
    final secondPcm = Uint8List(32000);
    secondPcm[0] = 2;
    transcriber.appendPcm(Uint8List(32000));
    transcriber.appendPcm(secondPcm);
    transcriber.appendPcm(Uint8List.fromList([3, 0]));
    await Future<void>.delayed(Duration.zero);
    expect(batchLengths, [32000]);

    final stopping = transcriber.stop().then((_) => events.add('stopped'));
    transcriber.appendPcm(Uint8List(32000));
    firstBatch.complete('first');
    await Future<void>.delayed(Duration.zero);
    expect(batchLengths, [32000, 32000]);
    expect(events, ['first']);

    secondBatch.complete('second');
    await stopping;

    expect(batchLengths, [32000, 32000, 2]);
    expect(batchStarts, [0, 2, 3]);
    expect(events, ['first', 'second', 'tail', 'stopped']);
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

  test('repeated whisper stop calls share the buffered tail failure', () async {
    final tail = Completer<String>();
    final error = StateError('tail runner failed');
    final batches = <Uint8List>[];
    final transcriber = WhisperTranscriber(
      runner: (pcm) {
        batches.add(pcm);
        return tail.future;
      },
      onTranscript: (_) => fail('The failing tail must not produce a transcript'),
    );

    transcriber.appendPcm(Uint8List.fromList([1, 0]));
    final failures = Future.wait([
      expectLater(transcriber.stop(), throwsA(same(error))),
      expectLater(transcriber.stop(), throwsA(same(error))),
    ]);
    await Future<void>.delayed(Duration.zero);
    tail.completeError(error);
    await failures;

    await expectLater(transcriber.stop(), throwsA(same(error)));
    expect(batches, [
      [1, 0],
    ]);
  });

  test('whisper stop drains the tail after a background batch fails', () async {
    final firstStarted = Completer<void>();
    final backgroundErrors = <Object>[];
    final transcripts = <String>[];
    final error = StateError('background runner failed');
    late final Completer<String> firstBatch;
    late final WhisperTranscriber transcriber;
    runZonedGuarded(() {
      firstBatch = Completer<String>();
      transcriber = WhisperTranscriber(
        runner: (pcm) {
          if (pcm.length < 32000) return 'tail';
          firstStarted.complete();
          return firstBatch.future;
        },
        onTranscript: transcripts.add,
        batchSeconds: 1,
      );
      transcriber.appendPcm(Uint8List(32000));
    }, (error, _) => backgroundErrors.add(error));

    await firstStarted.future;
    transcriber.appendPcm(Uint8List.fromList([1, 0]));
    final stopping = transcriber.stop();
    firstBatch.completeError(error);
    await stopping;
    await Future<void>.delayed(Duration.zero);

    expect(backgroundErrors, [same(error)]);
    expect(transcripts, ['tail']);
  });
}
