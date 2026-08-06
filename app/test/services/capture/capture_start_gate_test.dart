import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/capture/capture_start_gate.dart';

void main() {
  test('reuses a healthy exact-device capture instead of resetting it', () {
    expect(
      canReuseActiveDeviceCapture(
        activeDeviceId: 'device-a',
        requestedDeviceId: 'device-a',
        recordingActive: true,
        audioPathActive: true,
      ),
      isTrue,
    );
    expect(
      canReuseActiveDeviceCapture(
        activeDeviceId: 'device-a',
        requestedDeviceId: 'device-b',
        recordingActive: true,
        audioPathActive: true,
      ),
      isFalse,
    );
    expect(
      canReuseActiveDeviceCapture(
        activeDeviceId: 'device-a',
        requestedDeviceId: 'device-a',
        recordingActive: true,
        audioPathActive: false,
      ),
      isFalse,
    );
  });

  test('concurrent device-ready callbacks share one socket and tail start', () async {
    final gate = CaptureStartGate();
    final release = Completer<void>();
    var starts = 0;

    Future<void> start() async {
      starts++;
      await release.future;
    }

    final first = gate.run(start);
    final second = gate.run(start);
    expect(starts, 1);

    release.complete();
    await Future.wait([first, second]);
    expect(starts, 1);

    await gate.run(() async => starts++);
    expect(starts, 2);
  });
}
