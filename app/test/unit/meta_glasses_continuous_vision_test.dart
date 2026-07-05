import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

/// Camera+Mic mode IS the vision mode (there is no separate continuous-vision
/// toggle). Background capture streams video frames continuously and forwards
/// one downscaled frame per user-selected capture interval.
void main() {
  group('Meta glasses vision = Camera+Mic continuous frame stream', () {
    final provider = _read('lib/providers/meta_wearables_provider.dart');

    test('no separate continuous-vision toggle', () {
      expect(provider, isNot(contains('continuousVisionEnabled')));
      expect(provider, isNot(contains('ContinuousVisionFrameGate')));
    });

    test('background frames are throttled to the capture interval', () {
      // The frame handler carries a generation token so frames from a torn-down
      // stream can't trigger stale captures.
      expect(provider, contains('void _onVideoFrame(VideoFrame frame, int listenerGeneration)'));
      expect(provider, contains('now.difference(last) < _photoInterval'));
      expect(provider, contains('Future<void> _captureFrame()'));
      expect(provider, contains('MetaWearablesDat.captureLatestFrame'));
    });
  });
}
