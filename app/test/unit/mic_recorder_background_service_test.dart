import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/services.dart';

/// The background isolate host, with readiness held back so a stop can arrive first.
class _SlowHost extends BackgroundService {
  final ready = Completer<void>();
  final calls = <String>[];

  @override
  Future<void> ensureRunning() => ready.future;

  @override
  void startRecorder({
    required Function(Uint8List) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
  }) {
    calls.add('start');
  }

  @override
  void stopRecorder() {
    calls.add('stop');
  }
}

void main() {
  test('a stop while the recorder is still starting cancels the start (#20775)', () async {
    final host = _SlowHost();
    final mic = MicRecorderBackgroundService(runner: host);

    final starting = mic.start(onByteReceived: (_) {});
    mic.stop();
    host.ready.complete();
    await starting;

    expect(host.calls, ['stop']);
  });

  test('a start with no stop still starts the recorder', () async {
    final host = _SlowHost()..ready.complete();
    final mic = MicRecorderBackgroundService(runner: host);

    await mic.start(onByteReceived: (_) {});
    mic.stop();
    await mic.start(onByteReceived: (_) {});

    expect(host.calls, ['start', 'stop', 'start']);
  });
}
