import 'package:fake_async/fake_async.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/mic/native_mic_recorder_service.dart';

class FakePhoneMicHostApi extends PhoneMicHostApi {
  int startCalls = 0;
  int stopCalls = 0;
  PhoneMicCaptureMode? lastStartMode;
  int lastStartSessionId = 0;
  PlatformException? startError;

  @override
  Future<void> start(PhoneMicCaptureMode mode, int sessionId) async {
    startCalls++;
    lastStartMode = mode;
    lastStartSessionId = sessionId;
    if (startError != null) throw startError!;
  }

  @override
  Future<void> stop() async {
    stopCalls++;
  }

  @override
  Future<bool> isRecording() async => false;
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
    // The first session is minted with id 1.
    expect(host.lastStartSessionId, 1);
    final id = host.lastStartSessionId;

    service.onStateChanged(PhoneMicCaptureState.starting, id);
    expect(cb.initializing, 1);

    service.onStateChanged(PhoneMicCaptureState.running, id);
    expect(cb.recording, 1);
    expect(cb.interruptions, isEmpty);

    service.onAudioFrame(Uint8List.fromList([1, 2, 3]), id);
    expect(cb.bytes, hasLength(1));

    service.stop();
  });

  test('interruption sequencing: began once, ended then recording', () async {
    await startService();
    final id = host.lastStartSessionId;
    service.onStateChanged(PhoneMicCaptureState.starting, id);
    service.onStateChanged(PhoneMicCaptureState.running, id);

    service.onStateChanged(PhoneMicCaptureState.interrupted, id);
    service.onStateChanged(PhoneMicCaptureState.interrupted, id); // dedup
    expect(cb.interruptions, [true]);

    service.onStateChanged(PhoneMicCaptureState.running, id);
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
    final id = host.lastStartSessionId;
    // Late events after the failed start must be no-ops.
    service.onStateChanged(PhoneMicCaptureState.running, id);
    service.onAudioFrame(Uint8List.fromList([1]), id);
    expect(cb.recording, 0);
    expect(cb.bytes, isEmpty);
  });

  test('stop fires onStop exactly once and drops later events', () async {
    await startService();
    final id = host.lastStartSessionId;
    service.onStateChanged(PhoneMicCaptureState.starting, id);
    service.onStateChanged(PhoneMicCaptureState.running, id);

    service.stop();
    expect(host.stopCalls, 1);
    expect(cb.stops, 1);

    service.stop(); // local teardown is idempotent (native stop is not — see orphan-kill test)
    service.onStateChanged(PhoneMicCaptureState.idle, id);
    service.onAudioFrame(Uint8List.fromList([1]), id);
    expect(cb.stops, 1);
    expect(cb.bytes, isEmpty);
  });

  test('native terminal stop (idle while active) fires onStop once', () async {
    await startService();
    final id = host.lastStartSessionId;
    service.onStateChanged(PhoneMicCaptureState.starting, id);
    service.onStateChanged(PhoneMicCaptureState.running, id);

    service.onStateChanged(PhoneMicCaptureState.idle, id);
    expect(cb.stops, 1);
    service.onStateChanged(PhoneMicCaptureState.idle, id);
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
      final id = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, id);
      service.onStateChanged(PhoneMicCaptureState.running, id);

      // Frames keep the watchdog quiet.
      elapse(const Duration(seconds: 2));
      service.onAudioFrame(Uint8List.fromList([1]), id);
      elapse(const Duration(seconds: 2));
      expect(cb.stalls, 0);

      // Silence past the threshold trips it once.
      elapse(const Duration(seconds: 4));
      expect(cb.stalls, 1);
      elapse(const Duration(seconds: 10));
      expect(cb.stalls, 1);

      // A frame re-arms it.
      service.onAudioFrame(Uint8List.fromList([1]), id);
      elapse(const Duration(seconds: 4));
      expect(cb.stalls, 2);

      // Interrupted silence is expected — no stall.
      service.onAudioFrame(Uint8List.fromList([1]), id);
      service.onStateChanged(PhoneMicCaptureState.interrupted, id);
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
      final id = host.lastStartSessionId;
      // No running event yet — e.g. the permission dialog is up.
      service.onStateChanged(PhoneMicCaptureState.starting, id);
      elapse(const Duration(seconds: 30));
      expect(cb.stalls, 0);

      service.onStateChanged(PhoneMicCaptureState.running, id);
      elapse(const Duration(seconds: 4));
      expect(cb.stalls, 1);

      service.stop();
    });
  });

  test('startBatch drives native in batch mode and maps interruption', () async {
    await startBatchService();
    expect(host.startCalls, 1);
    expect(host.lastStartMode, PhoneMicCaptureMode.batch);
    final id = host.lastStartSessionId;

    // No onRecording/onByteReceived wiring in batch: running just arms the
    // watchdog, and frames never arrive.
    service.onStateChanged(PhoneMicCaptureState.starting, id);
    service.onStateChanged(PhoneMicCaptureState.running, id);
    expect(cb.recording, 0);

    service.onStateChanged(PhoneMicCaptureState.interrupted, id);
    service.onStateChanged(PhoneMicCaptureState.interrupted, id); // dedup
    expect(cb.interruptions, [true]);
    service.onStateChanged(PhoneMicCaptureState.running, id);
    expect(cb.interruptions, [true, false]);

    service.stop();
    expect(cb.stops, 1);
  });

  test('batch capture error is forwarded to the session onError', () async {
    await startBatchService();
    final id = host.lastStartSessionId;
    service.onStateChanged(PhoneMicCaptureState.starting, id);
    service.onStateChanged(PhoneMicCaptureState.running, id);
    service.onCaptureError('batch_storage_full', 'disk full', id);
    expect(cb.errors, ['batch_storage_full']);
    service.stop();
  });

  test('batch start failure rethrows and clears callbacks', () async {
    host.startError = PlatformException(code: 'opus_init_failed');
    await expectLater(
      startBatchService(),
      throwsA(isA<PlatformException>().having((e) => e.code, 'code', 'opus_init_failed')),
    );
    final id = host.lastStartSessionId;
    // Late events after the failed start must be no-ops.
    service.onStateChanged(PhoneMicCaptureState.running, id);
    service.onCaptureError('batch_storage_full', 'x', id);
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
      final id = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, id);
      service.onStateChanged(PhoneMicCaptureState.running, id);

      // Progress arrivals keep it quiet.
      elapse(const Duration(seconds: 6));
      service.onBatchProgress(6, id);
      elapse(const Duration(seconds: 6));
      expect(cb.batchStalls, 0);

      // Silence past the threshold trips it once.
      elapse(const Duration(seconds: 11));
      expect(cb.batchStalls, 1);
      elapse(const Duration(seconds: 20));
      expect(cb.batchStalls, 1);

      // A progress arrival re-arms it.
      service.onBatchProgress(7, id);
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
      final id = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, id);
      service.onStateChanged(PhoneMicCaptureState.running, id);

      // Progress keeps arriving (frozen value) through an interruption — no stall.
      service.onStateChanged(PhoneMicCaptureState.interrupted, id);
      for (var i = 0; i < 5; i++) {
        elapse(const Duration(seconds: 3));
        service.onBatchProgress(0, id);
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
      final id = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, id);
      service.onStateChanged(PhoneMicCaptureState.running, id);

      service.stop();
      elapse(const Duration(seconds: 30));
      expect(cb.batchStalls, 0);
      expect(cb.stops, 1);
    });
  });

  // The fix: events carry the id of the session they belong to, so the ONLY test
  // for staleness is a mismatched id. A restart can leave the previous session's
  // terminal `idle` in flight on the FIFO channel; it carries the OLD id and is
  // dropped, so it cannot clobber the freshly armed session.
  group('events from a previous session (old id) are dropped', () {
    test('stream: late idle after restart does not clobber the new session', () async {
      // Session A: live, then stopped from Dart.
      await startService();
      final idA = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, idA);
      service.onStateChanged(PhoneMicCaptureState.running, idA);
      service.stop();
      expect(cb.stops, 1);

      // Session B: fresh callbacks armed by a new start() (new id).
      final b = Callbacks();
      await service.start(
        onByteReceived: b.bytes.add,
        onRecording: () => b.recording++,
        onStop: () => b.stops++,
        onInitializing: () => b.initializing++,
        onStalled: () => b.stalls++,
        onInterruption: b.interruptions.add,
      );
      final idB = host.lastStartSessionId;
      expect(idB, isNot(idA));

      // A's terminal idle (idA) arrives after B armed — must be dropped by id.
      service.onStateChanged(PhoneMicCaptureState.idle, idA);
      expect(b.stops, 0, reason: 'stale idle must not fire the new session onStop');

      // B proceeds normally: callbacks were never cleared.
      service.onStateChanged(PhoneMicCaptureState.starting, idB);
      service.onStateChanged(PhoneMicCaptureState.running, idB);
      expect(b.recording, 1);
      service.onAudioFrame(Uint8List.fromList([1, 2, 3]), idB);
      expect(b.bytes, hasLength(1));

      service.stop();
    });

    test('batch: late idle after restart does not clobber the new batch session', () async {
      await startBatchService();
      final idA = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, idA);
      service.onStateChanged(PhoneMicCaptureState.running, idA);
      service.stop();
      expect(cb.stops, 1);

      final b = Callbacks();
      await service.startBatch(
        onStop: () => b.stops++,
        onInterruption: b.interruptions.add,
        onBatchStalled: () => b.batchStalls++,
        onError: (code, message) => b.errors.add(code),
      );
      final idB = host.lastStartSessionId;
      expect(idB, isNot(idA));

      // A's terminal idle (idA) arrives after B armed — must be dropped by id.
      service.onStateChanged(PhoneMicCaptureState.idle, idA);
      expect(b.stops, 0, reason: 'stale idle must not fire the new batch session onStop');

      // B proceeds normally; progress keeps arriving without a stall report.
      service.onStateChanged(PhoneMicCaptureState.starting, idB);
      service.onStateChanged(PhoneMicCaptureState.running, idB);
      expect(() => service.onBatchProgress(1, idB), returnsNormally);
      expect(b.stops, 0);

      service.stop();
    });

    test('genuine terminal idle still fires onStop and later frames are ignored', () async {
      await startService();
      final id = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, id);
      service.onStateChanged(PhoneMicCaptureState.running, id);

      service.onStateChanged(PhoneMicCaptureState.idle, id);
      expect(cb.stops, 1);

      // Frame after the terminal idle is a no-op.
      service.onAudioFrame(Uint8List.fromList([1]), id);
      expect(cb.bytes, isEmpty);

      // A repeated idle does not fire again.
      service.onStateChanged(PhoneMicCaptureState.idle, id);
      expect(cb.stops, 1);
    });

    test('stale non-idle events (old id) are dropped while the new session runs', () async {
      await startService();
      final idA = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, idA);
      service.onStateChanged(PhoneMicCaptureState.running, idA);
      service.stop();

      final b = Callbacks();
      await service.start(
        onByteReceived: b.bytes.add,
        onRecording: () => b.recording++,
        onStop: () => b.stops++,
        onInitializing: () => b.initializing++,
        onStalled: () => b.stalls++,
        onInterruption: b.interruptions.add,
      );
      final idB = host.lastStartSessionId;

      // A stale `interrupted` (idA) must not flap B's UI.
      service.onStateChanged(PhoneMicCaptureState.interrupted, idA);
      expect(b.interruptions, isEmpty);

      // B's own interruption (idB) is honored.
      service.onStateChanged(PhoneMicCaptureState.starting, idB);
      service.onStateChanged(PhoneMicCaptureState.running, idB);
      service.onStateChanged(PhoneMicCaptureState.interrupted, idB);
      expect(b.interruptions, [true]);

      service.stop();
    });
  });

  // Regression coverage for the de-sync fix.
  group('session-identity de-sync recovery', () {
    test('piggyback recovery: running under a new id fires onRecording without a fresh starting', () async {
      // Session A: live.
      await startService();
      final idA = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, idA);
      service.onStateChanged(PhoneMicCaptureState.running, idA);
      expect(cb.recording, 1);

      // De-sync: a new start() lands with NO intervening idle (the socket-reconnect
      // restart / stale-idle churn). Native adopts the new id onto the still-live
      // session and re-emits its state — so only `running(idB)` arrives, never a
      // fresh `starting`.
      final b = Callbacks();
      await service.start(
        onByteReceived: b.bytes.add,
        onRecording: () => b.recording++,
        onStop: () => b.stops++,
        onInitializing: () => b.initializing++,
        onStalled: () => b.stalls++,
        onInterruption: b.interruptions.add,
      );
      final idB = host.lastStartSessionId;
      expect(idB, isNot(idA));

      service.onStateChanged(PhoneMicCaptureState.running, idB);
      expect(b.recording, 1, reason: 'the wedge this fixes: onRecording fires without a fresh starting');

      service.stop();
    });

    test('orphan kill: stop() always forwards to native; local teardown runs once', () async {
      await startService();
      final id = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, id);
      service.onStateChanged(PhoneMicCaptureState.running, id);

      service.stop();
      service.stop();
      // Unconditional native stop is what kills an orphaned native session.
      expect(host.stopCalls, 2);
      // But callbacks/onStop only fire on the first (active) teardown.
      expect(cb.stops, 1);
    });

    test('a frame carrying an old id never reaches onByteReceived', () async {
      await startService();
      final id = host.lastStartSessionId;
      service.onStateChanged(PhoneMicCaptureState.starting, id);
      service.onStateChanged(PhoneMicCaptureState.running, id);

      // A frame from a superseded session (old id) is dropped.
      service.onAudioFrame(Uint8List.fromList([9]), id - 1);
      expect(cb.bytes, isEmpty);

      // The current id still delivers.
      service.onAudioFrame(Uint8List.fromList([1, 2, 3]), id);
      expect(cb.bytes, hasLength(1));

      service.stop();
    });
  });
}
