import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import '../../support/capture/capture_replay_world.dart';

void main() {
  test('onboarding Finish uses the existing coordinator Process Now and returns its empty result', () async {
    final directory = await Directory.systemTemp.createTemp('first_capture_finish_');
    final world = await CaptureReplayWorld.boot(tempDir: directory);
    try {
      await world.startLiveCapture();
      world.emitNativeState(PhoneMicCaptureState.running);
      await world.settle();
      expect(world.controller.liveCaptureSource, 'phone');
      final result = await world.controller.finishCaptureWithResult();
      expect(world.processCalls, 1);
      expect(result, isNull);
      expect(world.controller.liveCaptureSource, isNull);
    } finally {
      await world.dispose();
      directory.deleteSync(recursive: true);
    }
  });
}
