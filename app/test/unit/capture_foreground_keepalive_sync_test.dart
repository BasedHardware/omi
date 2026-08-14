import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/capture/capture_foreground_keepalive_sync.dart';

void main() {
  late CaptureForegroundKeepAliveSync sync;
  late List<String> events;

  Future<void> apply({
    required bool Function() desiredHold,
    bool Function()? bluetoothSessionOwner,
    required Future<void> Function() start,
    required Future<void> Function() stop,
    Future<bool> Function()? deactivate,
  }) {
    return sync.apply(
      desiredHold: desiredHold,
      bluetoothSessionOwner: bluetoothSessionOwner ?? () => true,
      start: start,
      stop: stop,
      deactivateBluetoothAudioSession: deactivate ??
          () async {
            events.add('deactivate');
            return true;
          },
    );
  }

  setUp(() {
    sync = CaptureForegroundKeepAliveSync();
    events = <String>[];
  });

  test('stop during in-flight start still tears down FGS', () async {
    var hold = true;
    final startGate = Completer<void>();
    final started = Completer<void>();

    final first = apply(
      desiredHold: () => hold,
      start: () async {
        events.add('start');
        started.complete();
        await startGate.future;
      },
      stop: () async {
        events.add('stop');
      },
    );

    await started.future;
    hold = false;
    final second = apply(
      desiredHold: () => hold,
      start: () async {
        events.add('start-again');
      },
      stop: () async {
        events.add('stop');
      },
    );
    startGate.complete();
    await first;
    await second;

    expect(sync.held, isFalse);
    expect(events, ['start', 'stop', 'deactivate']);
  });

  test('does not leave FGS held when start throws', () async {
    await apply(
      desiredHold: () => true,
      start: () async {
        throw StateError('start failed');
      },
      stop: () async {
        events.add('stop');
      },
    );

    expect(sync.held, isFalse);
    expect(events, isEmpty);
  });

  test('retries Bluetooth audio-session deactivate after a failure', () async {
    var deactivateOk = false;
    Future<bool> deactivate() async {
      events.add(deactivateOk ? 'deactivate-ok' : 'deactivate-fail');
      return deactivateOk;
    }

    await apply(
      desiredHold: () => true,
      start: () async {
        events.add('start');
      },
      stop: () async {},
      deactivate: deactivate,
    );
    expect(sync.held, isTrue);
    expect(sync.bluetoothAudioSessionHeld, isTrue);

    await apply(
      desiredHold: () => false,
      start: () async {},
      stop: () async {
        events.add('stop');
      },
      deactivate: deactivate,
    );
    expect(sync.held, isFalse);
    expect(sync.bluetoothAudioSessionHeld, isTrue);

    deactivateOk = true;
    await apply(
      desiredHold: () => false,
      start: () async {},
      stop: () async {
        events.add('stop-again');
      },
      deactivate: deactivate,
    );
    expect(sync.bluetoothAudioSessionHeld, isFalse);
    expect(events, ['start', 'stop', 'deactivate-fail', 'deactivate-ok']);
  });

  test('does not deactivate AVAudioSession for a non-Bluetooth capture owner', () async {
    await apply(
      desiredHold: () => true,
      bluetoothSessionOwner: () => false,
      start: () async {
        events.add('start');
      },
      stop: () async {},
    );
    await apply(
      desiredHold: () => false,
      bluetoothSessionOwner: () => false,
      start: () async {},
      stop: () async {
        events.add('stop');
      },
    );

    expect(sync.held, isFalse);
    expect(sync.bluetoothAudioSessionHeld, isFalse);
    expect(events, ['start', 'stop']);
  });
}
