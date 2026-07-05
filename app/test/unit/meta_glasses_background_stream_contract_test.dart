import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  group('Meta glasses background stream contract', () {
    test('background visual capture samples silent stream frames, not hardware still photos', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      // Native-pushed frame stream trigger (background-capable) + SDK-encoded
      // frame pull. No shutter, no still-photo API, no suspending Dart timer.
      expect(provider, contains('_service.videoFrames().listen'));
      expect(provider, contains('MetaWearablesDat.captureLatestFrame'));
      expect(provider, isNot(contains('MetaWearablesDat.capturePhoto(')));
      expect(provider, isNot(contains('_pausePreviewBetweenFrames')));
      expect(provider, isNot(contains('Timer.periodic(_photoInterval')));
    });

    test('glasses gesture bridge owns iOS Now Playing state while listening', () {
      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      expect(appDelegate, contains('MPNowPlayingInfoCenter.default().nowPlayingInfo'));
      expect(appDelegate, contains('MPNowPlayingInfoCenter.default().playbackState = .playing'));
      expect(appDelegate, contains('MPNowPlayingInfoCenter.default().playbackState = .stopped'));
    });
  });
}
