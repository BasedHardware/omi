// Opt-in host verification of the real native decoder + ONNX binding. Not in
// test/: native libraries must be available. See mobile-standard-batch.md.
import 'dart:ffi';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:omi/services/wals/mobile_batch_vad.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('real Opus -> Float32 Silero recurrent state, bounded cost', () async {
    // Match opus_flutter.load's dynamic native-library boundary; opus_dart
    // conditionally exports native/web bindings.
    final dynamic nativeLibrary = DynamicLibrary.open(Platform.environment['OMI_OPUS_LIBRARY'] ?? 'libopus.dylib');
    initOpus(nativeLibrary);
    final vad = await SileroMobileBatchVad.load();
    final elapsed = Stopwatch()..start();
    const seconds = 60;
    try {
      for (var i = 0; i < seconds * 100; i++) {
        // libopus-generated 10ms silent Opus frame. No microphone or network.
        final probability = await vad.probability([176, 255, 254]);
        expect(probability, inInclusiveRange(0, 1));
      }
      elapsed.stop();
      final msPerAudioSecond = elapsed.elapsedMicroseconds / 1000 / seconds;
      // A correctness/performance gate, not a phone battery claim.
      expect(msPerAudioSecond, lessThan(1000));
      // ignore: avoid_print
      print('mobile_vad_native audio_seconds=$seconds elapsed_ms_per_audio_second=$msPerAudioSecond');
    } finally {
      await vad.close();
    }
  });
}
