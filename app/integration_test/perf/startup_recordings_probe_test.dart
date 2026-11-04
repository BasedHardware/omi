// Host probe for the cold duration-cache path. Unlike the seeded UI scenarios,
// this gives startup a real recording backlog. Wall times are diagnostic only;
// UI-zone callback time measures work competing with scroll/build callbacks.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/local_recordings_provider.dart';

void main() {
  test('cold recording duration scan probe', () async {
    final directory = await Directory.systemTemp.createTemp('omi-startup-recordings-');
    try {
      final file = File('${directory.path}/recording.bin');
      const frameCount = 1000000;
      const frameBytes = 44;
      final chunk = Uint8List(frameBytes * 10000);
      for (var offset = 0; offset < chunk.length; offset += frameBytes) {
        chunk[offset] = frameBytes - 4;
      }
      final handle = await file.open(mode: FileMode.write);
      for (var index = 0; index < frameCount ~/ 10000; index++) {
        await handle.writeFrom(chunk);
      }
      await handle.close();

      for (var run = 0; run < 3; run++) {
        var uiMicroseconds = 0;
        var callbacks = 0;
        final wall = Stopwatch()..start();
        final frames = await runZoned(
          () => countBatchRecordingFrames(file.path),
          zoneSpecification: ZoneSpecification(
            runUnary: <R, T>(self, parent, zone, callback, argument) {
              final timer = Stopwatch()..start();
              try {
                return parent.runUnary(zone, callback, argument);
              } finally {
                uiMicroseconds += timer.elapsedMicroseconds;
                callbacks++;
              }
            },
          ),
        );
        wall.stop();
        expect(frames, frameCount);
        // ignore: avoid_print
        print('STARTUP_RECORDINGS_PROBE=${jsonEncode({
              'run': run,
              'bytes': frameCount * frameBytes,
              'frames': frames,
              'wall_ms': wall.elapsedMicroseconds / 1000,
              'ui_callback_ms': uiMicroseconds / 1000,
              'ui_callbacks': callbacks,
            })}');
      }
    } finally {
      await directory.delete(recursive: true);
    }
  });
}
