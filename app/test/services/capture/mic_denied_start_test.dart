import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/capture/capture_start_errors.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';

import '../../support/capture/capture_replay_world.dart';

// C2 (audit 2026-11-19): the record button with the mic denied said "Something went wrong" on
// every tap. The start now fails with a typed reason the button turns into Open Settings.
void main() {
  test('a phone start with the microphone denied fails with MicPermissionDenied', () async {
    final directory = await Directory.systemTemp.createTemp('mic_denied_start_');
    final world = await CaptureReplayWorld.boot(tempDir: directory);
    try {
      world.allowMic = false;
      await expectLater(world.controller.streamRecording(), throwsA(isA<MicPermissionDenied>()));
      expect(world.controller.liveCaptureSource, isNull);

      // Allowed again, the same button starts; the denial does not stick.
      world.allowMic = true;
      await world.startLiveCapture();
      expect(world.controller.liveCaptureSource, 'phone');
    } finally {
      await world.dispose();
      directory.deleteSync(recursive: true);
    }
  });

  test('Finish keeps the answer and why there is none (no bare null for the page)', () async {
    final directory = await Directory.systemTemp.createTemp('finish_outcome_absence_');
    final world = await CaptureReplayWorld.boot(tempDir: directory);
    try {
      await world.startLiveCapture();
      world.emitNativeState(PhoneMicCaptureState.running);
      await world.settle();
      final outcome = await world.controller.finishCaptureWithOutcome();
      expect(world.processCalls, 1);
      expect(outcome.response?.conversation, isNull);
      expect(outcome.absence, isNotNull, reason: 'the page needs to know whether it failed or was empty');
      expect(outcome.absence, isA<ProcessAbsence>());
    } finally {
      await world.dispose();
      directory.deleteSync(recursive: true);
    }
  });
}
