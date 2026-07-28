import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/mic/mic_arbiter.dart';
import 'package:omi/services/services.dart';

class FakeMic implements IMicRecorderService {
  int startCalls = 0;
  int startBatchCalls = 0;
  int stopCalls = 0;
  bool failNextStart = false;
  bool failNextStartBatch = false;
  Function()? capturedOnStop;

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
    Function(bool began)? onInterruption,
  }) async {
    startCalls++;
    if (failNextStart) {
      failNextStart = false;
      throw Exception('recorder failed to start');
    }
    capturedOnStop = onStop;
  }

  @override
  Future<void> startBatch({
    Function()? onStop,
    Function(bool began)? onInterruption,
    Function()? onBatchStalled,
    Function(String code, String message)? onError,
  }) async {
    startBatchCalls++;
    if (failNextStartBatch) {
      failNextStartBatch = false;
      throw Exception('batch recorder failed to start');
    }
    capturedOnStop = onStop;
  }

  @override
  void stop() {
    stopCalls++;
    capturedOnStop?.call();
    capturedOnStop = null;
  }
}

void main() {
  group('MicArbiter', () {
    test('same owner can re-acquire, different owner cannot', () {
      final arbiter = MicArbiter();
      expect(arbiter.tryAcquire('a'), isTrue);
      expect(arbiter.tryAcquire('a'), isTrue);
      expect(arbiter.tryAcquire('b'), isFalse);
      arbiter.release('a');
      expect(arbiter.tryAcquire('b'), isTrue);
    });

    test('release by non-owner is ignored', () {
      final arbiter = MicArbiter();
      arbiter.tryAcquire('a');
      arbiter.release('b');
      expect(arbiter.owner, 'a');
    });
  });

  group('ArbitratedMic', () {
    late MicArbiter arbiter;
    late FakeMic micA;
    late FakeMic micB;
    late ArbitratedMic a;
    late ArbitratedMic b;

    setUp(() {
      arbiter = MicArbiter();
      micA = FakeMic();
      micB = FakeMic();
      a = ArbitratedMic(inner: micA, arbiter: arbiter, owner: 'conversation');
      b = ArbitratedMic(inner: micB, arbiter: arbiter, owner: 'mic');
    });

    Future<void> startMic(ArbitratedMic mic) => mic.start(onByteReceived: (_) {});

    test('second stack contends while first holds the mic', () async {
      await startMic(a);
      expect(() => startMic(b), throwsStateError);
      expect(micB.startCalls, 0);
    });

    test('stop releases so the other stack can start', () async {
      await startMic(a);
      a.stop();
      await startMic(b);
      expect(micB.startCalls, 1);
    });

    test('start failure releases the arbiter and rethrows', () async {
      micA.failNextStart = true;
      await expectLater(startMic(a), throwsException);
      await startMic(b);
      expect(micB.startCalls, 1);
    });

    test('natural stop (inner onStop) releases without an explicit stop()', () async {
      var stopped = false;
      await a.start(onByteReceived: (_) {}, onStop: () => stopped = true);
      // Simulate the recorder retiring itself (e.g. watchdog kill).
      micA.capturedOnStop!.call();
      expect(stopped, isTrue);
      await startMic(b);
      expect(micB.startCalls, 1);
    });

    test('startBatch contends while the other stack holds the mic', () async {
      await startMic(b);
      expect(() => a.startBatch(), throwsStateError);
      expect(micA.startBatchCalls, 0);
    });

    test('startBatch failure releases the arbiter and rethrows', () async {
      micA.failNextStartBatch = true;
      await expectLater(a.startBatch(), throwsException);
      await startMic(b);
      expect(micB.startCalls, 1);
    });

    test('stop after startBatch releases so the other stack can start', () async {
      await a.startBatch();
      expect(micA.startBatchCalls, 1);
      a.stop();
      await startMic(b);
      expect(micB.startCalls, 1);
    });

    test('natural stop from batch onStop releases the arbiter', () async {
      await a.startBatch();
      // Native terminal stop wired through the wrapped onStop.
      micA.capturedOnStop!.call();
      await startMic(b);
      expect(micB.startCalls, 1);
    });
  });
}
