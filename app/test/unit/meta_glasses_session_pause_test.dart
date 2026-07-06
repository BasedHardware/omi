import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

/// The plan-02 "pause/resume between still-photo samples" design produced a
/// shuttered snapshot cadence and `SessionError(videoStreamingError)`. It was
/// superseded by a single continuous video-frame stream (runtime-stabilization
/// plan). These assertions lock in the continuous design so the shuttered
/// pause/resume loop cannot come back.
void main() {
  group('Meta glasses continuous stream (superseded pause/resume)', () {
    final provider = _read('lib/providers/meta_wearables_provider.dart');
    final service = _read('lib/services/devices/meta_wearables_service.dart');

    test('background capture uses one continuous never-paused session', () {
      expect(provider, contains('_service.videoFrames().listen'),
          reason: 'native-pushed frame stream is the background-capable trigger');
      expect(provider, contains('MetaWearablesDat.captureLatestFrame'),
          reason:
              'each throttled trigger encodes a viewable JPEG natively, not hand-encoded raw or GPU-texture rasterized');
      expect(provider, isNot(contains('Timer.periodic(_photoInterval')),
          reason: 'Dart timers suspend in the background');
    });

    test('no per-frame pause/resume or still-photo shutter path remains', () {
      expect(provider, isNot(contains('_pausePreviewBetweenFrames')));
      expect(provider, isNot(contains('_resumePreviewForFrame')));
      expect(provider, isNot(contains('MetaWearablesDat.capturePhoto(')));
      expect(service, isNot(contains('pausePreviewStream')));
      expect(service, isNot(contains('resumePreviewStream')));
    });

    test('frames are throttled to the user capture interval', () {
      expect(provider, contains('Duration get _photoInterval => captureInterval.duration;'));
      expect(provider, contains('now.difference(last) < _photoInterval'));
    });
  });
}
