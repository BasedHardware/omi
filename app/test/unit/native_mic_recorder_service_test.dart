import 'dart:typed_data';

import 'package:fake_async/fake_async.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/mic/native_mic_recorder_service.dart';

class FakePhoneMicHostApi extends PhoneMicHostApi {
  int startCalls = 0;
  int stopCalls = 0;
  PhoneMicCaptureMode? lastStartMode;
  PlatformException? startError;

  @override
  Future<void> start(PhoneMicCaptureMode mode) async {
    startCalls++;
    lastStartMode = mode;
    if (startError != null) throw startError!;
  }

  @override
  Future<void> stop() async {
    stopCalls++;
  }

  @override
  Future<bool> isRecording() async => false;

  @override
  Future<String> debugEncodeWavToBin(String wavPath, String marker) async => '';
}

class Callbacks {
  final bytes = <Uint8List>[];
  int recording = 0;
  int stops = 0;
  int initializing = 0;
  int stalls = 0;
  int batchStalls = 0;
  final interruptions = <bool>[];
  final errors = <String>[];
}

void main() {
  late FakePhoneMicHostApi host;
  late NativeMicRecorderService service;
  late Callbacks cb;

  setUp(() {
    host = FakePhoneMicHostApi();
    // registerFlutterApi: false — events are driven directly on the service,
    // which itself implements PhoneMicFlutterApi (no channel plumbing needed).
    service = NativeMicRecorderService(hostApi: host, registerFlutterApi: false);
    cb = Callbacks();
  });

  Future<void> startService() => service.start(
        onByteReceived: cb.bytes.add,
        onRecording: () => cb.recording++,
        onStop: () => cb.stops++,
        onInitializing: () => cb.initializing++,
        onStalled: () => cb.stalls++,
        onInterruption: cb.interruptions.add,
      );

  Future<void> startBatchService() => service.startBatch(
        onStop: () => cb.stops++,
        onInterruption: cb.interruptions.add,
        onBatchStalled: () => cb.batchStalls++,
        onError: (code, message) => cb.errors.add(code),
      );

  test('start calls host api and maps state events to callbacks', () async {
    await startService();
    expect(host.startCalls, 1);
    // This service always drives the native capture in stream mode.
    expect(host.lastStartMode, PhoneMicCaptureMode.stream);

    service.onStateChanged(PhoneMicCaptureState.starting);
    expect(cb.initializing, 1);

    service.onStateChanged(PhoneMicCaptureState.running);
    expect(cb.recording, 1);
    expect(cb.interruptions, isEmpty);

    service.onAudioFrame(Uint8List.fromList([1, 2, 3]));
    expect(cb.bytes, hasLength(1));

    service.stop();
  });

  test('interruption sequencing: began once, ended then recording', () async {
    await startService();
    service.onStateChanged(PhoneMicCaptureState.running);

    service.onStateChanged(PhoneMicCaptureState.interrupted);
    service.onStateChanged(PhoneMicCaptureState.interrupted); // dedup
    expect(cb.interruptions, [true]);

    service.onStateChanged(PhoneMicCaptureState.running);
    expect(cb.interruptions, [true, false]);
    expect(cb.recording, 2);

    service.stop();
  });

  test('host start failure rethrows and clears callbacks', () async {
    host.startError = PlatformException(code: 'permission_denied');
    await expectLater(
      startService(),
      throwsA(isA<PlatformException>().having((e) => e.code, 'code', 'permission_denied')),
    );
    // Late events after the failed start must be no-ops.
    service.onStateChanged(PhoneMicCaptureState.running);
    service.onAudioFrame(Uint8List.fromList([1]));
    expect(cb.recording, 0);
    expect(cb.bytes, isEmpty);
  });

  test('stop fires onStop exactly once and drops later events', () async {
    await startService();
    service.onStateChanged(PhoneMicCaptureState.running);

    service.stop();
    expect(host.stopCalls, 1);
    expect(cb.stops, 1);

    service.stop(); // idempotent
    service.onStateChanged(PhoneMicCaptureState.idle);
    service.onAudioFrame(Uint8List.fromList([1]));
    expect(cb.stops, 1);
    expect(cb.bytes, isEmpty);
  });

  test('native terminal stop (idle while active) fires onStop once', () async {
    await startService();
    service.onStateChanged(PhoneMicCaptureState.running);

    service.onStateChanged(PhoneMicCaptureState.idle);
    expect(cb.stops, 1);
    service.onStateChanged(PhoneMicCaptureState.idle);
    expect(cb.stops, 1);
  });

  test('stall watchdog fires after 3s of silence, reset by frames, suppressed while interrupted', () {
    fakeAsync((async) {
      // The watchdog compares wall-clock timestamps; fakeAsync only fakes
      // timers, so inject a clock advanced in lockstep with elapse().
      var now = DateTime(2026, 1, 1);
      service = NativeMicRecorderService(hostApi: host, registerFlutterApi: false, now: () => now);
      void elapse(Duration d) {
        now = now.add(d);
        async.elapse(d);
      }

      startService();
      async.flushMicrotasks();
      service.onStateChanged(PhoneMicCaptureState.running);

      // Frames keep the watchdog quiet.
      elapse(const Duration(seconds: 2));
      service.onAudioFrame(Uint8List.fromList([1]));
      elapse(const Duration(seconds: 2));
      expect(cb.stalls, 0);

      // Silence past the threshold trips it once.
      elapse(const Duration(seconds: 4));
      expect(cb.stalls, 1);
      elapse(const Duration(seconds: 10));
      expect(cb.stalls, 1);

      // A frame re-arms it.
      service.onAudioFrame(Uint8List.fromList([1]));
      elapse(const Duration(seconds: 4));
      expect(cb.stalls, 2);

      // Interrupted silence is expected — no stall.
      service.onAudioFrame(Uint8List.fromList([1]));
      service.onStateChanged(PhoneMicCaptureState.interrupted);
      elapse(const Duration(seconds: 30));
      expect(cb.stalls, 2);

      service.stop();
    });
  });

  test('watchdog is not armed during start (permission prompt can be slow)', () {
    fakeAsync((async) {
      var now = DateTime(2026, 1, 1);
      service = NativeMicRecorderService(hostApi: host, registerFlutterApi: false, now: () => now);
      void elapse(Duration d) {
        now = now.add(d);
        async.elapse(d);
      }

      startService();
      async.flushMicrotasks();
      // No running event yet — e.g. the permission dialog is up.
      elapse(const Duration(seconds: 30));
      expect(cb.stalls, 0);

      service.onStateChanged(PhoneMicCaptureState.running);
      elapse(const Duration(seconds: 4));
      expect(cb.stalls, 1);

      service.stop();
    });
  });

  test('startBatch drives native in batch mode and maps interruption', () async {
    await startBatchService();
    expect(host.startCalls, 1);
    expect(host.lastStartMode, PhoneMicCaptureMode.batch);

    // No onRecording/onByteReceived wiring in batch: running just arms the
    // watchdog, and frames never arrive.
    service.onStateChanged(PhoneMicCaptureState.running);
    expect(cb.recording, 0);

    service.onStateChanged(PhoneMicCaptureState.interrupted);
    service.onStateChanged(PhoneMicCaptureState.interrupted); // dedup
    expect(cb.interruptions, [true]);
    service.onStateChanged(PhoneMicCaptureState.running);
    expect(cb.interruptions, [true, false]);

    service.stop();
    expect(cb.stops, 1);
  });

  test('batch capture error is forwarded to the session onError', () async {
    await startBatchService();
    service.onStateChanged(PhoneMicCaptureState.running);
    service.onCaptureError('batch_storage_full', 'disk full');
    expect(cb.errors, ['batch_storage_full']);
    service.stop();
  });

  test('batch start failure rethrows and clears callbacks', () async {
    host.startError = PlatformException(code: 'opus_init_failed');
    await expectLater(
      startBatchService(),
      throwsA(isA<PlatformException>().having((e) => e.code, 'code', 'opus_init_failed')),
    );
    // Late events after the failed start must be no-ops.
    service.onStateChanged(PhoneMicCaptureState.running);
    service.onCaptureError('batch_storage_full', 'x');
    expect(cb.errors, isEmpty);
  });

  test('batch watchdog fires after 10s without progress, re-armed by progress', () {
    fakeAsync((async) {
      var now = DateTime(2026, 1, 1);
      service = NativeMicRecorderService(hostApi: host, registerFlutterApi: false, now: () => now);
      void elapse(Duration d) {
        now = now.add(d);
        async.elapse(d);
      }

      startBatchService();
      async.flushMicrotasks();
      service.onStateChanged(PhoneMicCaptureState.running);

      // Progress arrivals keep it quiet.
      elapse(const Duration(seconds: 6));
      service.onBatchProgress(6);
      elapse(const Duration(seconds: 6));
      expect(cb.batchStalls, 0);

      // Silence past the threshold trips it once.
      elapse(const Duration(seconds: 11));
      expect(cb.batchStalls, 1);
      elapse(const Duration(seconds: 20));
      expect(cb.batchStalls, 1);

      // A progress arrival re-arms it.
      service.onBatchProgress(7);
      elapse(const Duration(seconds: 11));
      expect(cb.batchStalls, 2);

      service.stop();
    });
  });

  test('batch watchdog is arrival-based, not suppressed during interruption', () {
    fakeAsync((async) {
      var now = DateTime(2026, 1, 1);
      service = NativeMicRecorderService(hostApi: host, registerFlutterApi: false, now: () => now);
      void elapse(Duration d) {
        now = now.add(d);
        async.elapse(d);
      }

      startBatchService();
      async.flushMicrotasks();
      service.onStateChanged(PhoneMicCaptureState.running);

      // Progress keeps arriving (frozen value) through an interruption — no stall.
      service.onStateChanged(PhoneMicCaptureState.interrupted);
      for (var i = 0; i < 5; i++) {
        elapse(const Duration(seconds: 3));
        service.onBatchProgress(0);
      }
      expect(cb.batchStalls, 0);

      // Progress stops while still interrupted — the stall still fires.
      elapse(const Duration(seconds: 11));
      expect(cb.batchStalls, 1);

      service.stop();
    });
  });

  test('stop cancels the batch watchdog', () {
    fakeAsync((async) {
      var now = DateTime(2026, 1, 1);
      service = NativeMicRecorderService(hostApi: host, registerFlutterApi: false, now: () => now);
      void elapse(Duration d) {
        now = now.add(d);
        async.elapse(d);
      }

      startBatchService();
      async.flushMicrotasks();
      service.onStateChanged(PhoneMicCaptureState.running);

      service.stop();
      elapse(const Duration(seconds: 30));
      expect(cb.batchStalls, 0);
      expect(cb.stops, 1);
    });
  });
}
